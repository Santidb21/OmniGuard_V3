import os
import sys
import time
import warnings
import sqlite3
import threading
import cv2
import numpy as np
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename
from flask_cors import CORS

from config import Config
from models import (
    init_db, crear_solicitud, obtener_solicitudes_pendientes,
    aceptar_solicitud, denegar_solicitud, obtener_usuarios_aceptados,
    obtener_usuarios_activos, dar_de_baja_usuario, eliminar_visitantes_expirados,
    registrar_entrada_salida, obtener_registros, obtener_usuario_por_id,
    obtener_embedding, get_db_connection, guardar_embedding
)
from reconocimiento.registros import exportar_registros_mensuales
from reconocimiento.detector import obtener_detector, iniciar_deteccion

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
app.secret_key = Config.SECRET_KEY

CONFIG_CAMARAS = {
    'entrada': 0,
    'salida': 1,
    'detectadas': []
}

CAPTURAS = {
    'entrada': None,
    'salida': None
}

CAPTURA_LOCKS = {
    'entrada': None,
    'salida': None
}

CAMERA_BACKENDS = {
    'entrada': None,
    'salida': None
}

CAMERAS_INFO = {}

CAMARAS_ACTIVAS = {
    'entrada': False,
    'salida': False
}

detector_inicializado = False

BACKENDS_CAMARA = [
    ('AUTO', cv2.CAP_ANY),
    ('DSHOW', cv2.CAP_DSHOW),
    ('MSMF', cv2.CAP_MSMF)
]

def configurar_captura(cap):
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 15)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def leer_frame_valido(cap, intentos=8):
    for _ in range(intentos):
        ret, frame = cap.read()
        if ret and frame is not None and frame.size > 0:
            return True, frame
        time.sleep(0.08)
    return False, None

def nombre_backend(cap, fallback):
    try:
        return cap.getBackendName()
    except Exception:
        return fallback

def abrir_captura(indice):
    indice = int(indice)
    for etiqueta, backend in BACKENDS_CAMARA:
        cap = cv2.VideoCapture(indice, backend)
        if not cap.isOpened():
            cap.release()
            continue

        configurar_captura(cap)
        ok, frame = leer_frame_valido(cap)
        if ok:
            return cap, nombre_backend(cap, etiqueta), frame

        cap.release()

    return None, None, None

def inicializar_sistema():
    global detector_inicializado
    detectar_camaras()
    ok = iniciar_deteccion()
    detector_inicializado = ok
    if ok:
        print("[INFO] Detector facial inicializado")
    else:
        print("[WARN] Detector facial no disponible")

def detectar_camaras():
    global CAMERAS_INFO
    camaras = []
    camaras_info = {}
    indices_activos = set()

    for tipo in ['entrada', 'salida']:
        if CAMARAS_ACTIVAS.get(tipo) and CONFIG_CAMARAS.get(tipo) is not None:
            indice = int(CONFIG_CAMARAS[tipo])
            indices_activos.add(indice)
            info = {
                'indice': indice,
                'nombre': 'Camara {} ({})'.format(indice, tipo),
                'backend': CAMERA_BACKENDS.get(tipo) or 'activa',
                'activa': True,
                'asignada': tipo
            }
            camaras.append(info)
            camaras_info[indice] = info

    for i in range(4):
        if i in indices_activos:
            continue

        cap, backend, frame = abrir_captura(i)
        if cap is None:
            continue

        alto, ancho = frame.shape[:2]
        cap.release()

        info = {
            'indice': i,
            'nombre': 'Camara {}'.format(i),
            'backend': backend,
            'activa': False,
            'asignada': None,
            'resolucion': '{}x{}'.format(ancho, alto)
        }
        camaras.append(info)
        camaras_info[i] = info

    camaras.sort(key=lambda c: c['indice'])
    CONFIG_CAMARAS['detectadas'] = [c['indice'] for c in camaras]
    CAMERAS_INFO = camaras_info
    return camaras

def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def verificar_directorios():
    os.makedirs(Config.FOTOS_PATH, exist_ok=True)
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    os.makedirs(Config.REGISTROS_PATH, exist_ok=True)
    os.makedirs(Config.LOGS_PATH, exist_ok=True)
    init_db()
    verificar_mes_nuevo()
    verificar_visitantes_expirados()

def verificar_mes_nuevo():
    try:
        db_path = Config.DB_PATH
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS control_mes (
                id INTEGER PRIMARY KEY,
                mes_actual TEXT,
                anio_actual INTEGER
            )
        ''')
        cursor.execute("SELECT mes_actual, anio_actual FROM control_mes WHERE id = 1")
        resultado = cursor.fetchone()
        
        mes_actual = datetime.now().strftime("%B")
        anio_actual = datetime.now().year
        
        if resultado is None:
            cursor.execute("INSERT INTO control_mes (id, mes_actual, anio_actual) VALUES (1, ?, ?)", 
                          (mes_actual, anio_actual))
            conn.commit()
        elif resultado[0] != mes_actual or resultado[1] != anio_actual:
            exportar_registros_mensuales()
            cursor.execute("UPDATE control_mes SET mes_actual = ?, anio_actual = ? WHERE id = 1", 
                          (mes_actual, anio_actual))
            conn.commit()
        conn.close()
    except Exception as e:
        print("[ERROR] Verificando mes nuevo: {}".format(e))

def verificar_visitantes_expirados():
    try:
        eliminados = eliminar_visitantes_expirados()
        if eliminados > 0:
            print("[INFO] Se eliminaron {} visitantes expirados".format(eliminados))
    except Exception as e:
        print("[ERROR] Verificando visitantes: {}".format(e))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def extraer_embeddings_imagenes(image_paths):
    try:
        detector = obtener_detector()
        if not detector.inicializado:
            iniciar_deteccion()

        embeddings = []
        for image_path in image_paths:
            embeddings.extend(detector.extraer_embeddings_de_archivo(image_path))

        return detector.serializar_embeddings(embeddings), len(embeddings)
    except Exception as e:
        print("[ERROR] Extrayendo embedding: {}".format(e))
        return None, 0

def leer_frame_camara(tipo_camara):
    cap = CAPTURAS.get(tipo_camara)
    if cap is None:
        return False, None
    lock = CAPTURA_LOCKS.get(tipo_camara)
    if lock is None:
        return cap.read()
    with lock:
        return cap.read()

def generar_frames_video(tipo_camara):
    detector = obtener_detector()
    frame_count = 0
    ultimo_analisis = 0
    ultimo_resultado = None

    while CAMARAS_ACTIVAS.get(tipo_camara, False):
        if CAPTURAS.get(tipo_camara) is None:
            time.sleep(0.5)
            continue

        try:
            ret, frame = leer_frame_camara(tipo_camara)
        except Exception as e:
            print("[ERROR] Leyendo frame de camara {}: {}".format(tipo_camara, e))
            break

        if not ret:
            time.sleep(0.1)
            continue

        try:
            frame_count += 1

            ahora = time.time()
            if ahora - ultimo_analisis >= 0.35:
                ultimo_analisis = ahora
                resultado = detector.analizar_frame(frame)
                if resultado.get('rostro') is not None:
                    resultado['ts'] = ahora
                    ultimo_resultado = resultado

                    usuario_id = resultado.get('usuario_id')
                    confianza = resultado.get('confianza', 0.0)
                    if usuario_id:
                        detector.procesar_deteccion(usuario_id, confianza, tipo_camara)

            if ultimo_resultado and ahora - ultimo_resultado.get('ts', 0) <= 1.2:
                x1, y1, x2, y2 = ultimo_resultado['rostro']
                usuario_id = ultimo_resultado.get('usuario_id')
                confianza = ultimo_resultado.get('confianza', 0.0)
                if usuario_id:
                    usuario = obtener_usuario_por_id(usuario_id)
                    etiqueta = "{} ({:.0f}%)".format(usuario['nombre_completo'], confianza * 100) if usuario else "Usuario {}".format(usuario_id)
                    color = (80, 220, 120)
                else:
                    etiqueta = "Rostro detectado"
                    color = (40, 180, 255)

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.rectangle(frame, (x1, max(0, y1 - 26)), (min(frame.shape[1], x1 + 260), y1), color, -1)
                cv2.putText(frame, etiqueta, (x1 + 6, max(18, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)

            cv2.putText(frame, "{} | {}".format(tipo_camara.upper(), datetime.now().strftime('%H:%M:%S')),
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, "OMNIGUARD", (10, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (201, 169, 98), 1)

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print("[ERROR] Generando frame: {}".format(e))
            break

    print("[INFO] Stream de camara {} terminado".format(tipo_camara))

def iniciar_camara(tipo_camara, indice):
    try:
        indice = int(indice)
        otro_tipo = 'salida' if tipo_camara == 'entrada' else 'entrada'
        if CAMARAS_ACTIVAS.get(otro_tipo) and CONFIG_CAMARAS.get(otro_tipo) == indice:
            print("[WARN] Camara {} ya esta usando el indice {}".format(otro_tipo, indice))
            return {
                'ok': False,
                'indice': indice,
                'message': 'La camara {} ya esta asignada a {}'.format(indice, otro_tipo)
            }

        if CAPTURAS.get(tipo_camara):
            CAPTURAS[tipo_camara].release()
            CAPTURAS[tipo_camara] = None
        
        captura, backend, frame = abrir_captura(indice)

        if captura is not None:
            CAPTURAS[tipo_camara] = captura
            CAPTURA_LOCKS[tipo_camara] = CAPTURA_LOCKS.get(tipo_camara) or threading.Lock()
            CAMERA_BACKENDS[tipo_camara] = backend
            CONFIG_CAMARAS[tipo_camara] = indice
            CAMARAS_ACTIVAS[tipo_camara] = True
            detector = obtener_detector()
            if detector:
                detector.actualizar_cache()
            alto, ancho = frame.shape[:2]
            print("[INFO] Camara {} iniciada en indice {} con backend {}".format(tipo_camara, indice, backend))
            return {
                'ok': True,
                'indice': indice,
                'backend': backend,
                'resolucion': '{}x{}'.format(ancho, alto),
                'message': 'Camara {} iniciada'.format(tipo_camara)
            }

        CAMARAS_ACTIVAS[tipo_camara] = False
        CAPTURAS[tipo_camara] = None
        CAPTURA_LOCKS[tipo_camara] = None
        CAMERA_BACKENDS[tipo_camara] = None
        print("[ERROR] No se pudo abrir camara {}".format(tipo_camara))
        return {
            'ok': False,
            'indice': indice,
            'message': 'No se pudo abrir la camara {}. Puede estar ocupada o sin permisos.'.format(indice)
        }
    except Exception as e:
        print("[ERROR] Iniciando camara: {}".format(e))
        return {
            'ok': False,
            'indice': indice if 'indice' in locals() else None,
            'message': str(e)
        }

def detener_camara(tipo_camara):
    try:
        CAMARAS_ACTIVAS[tipo_camara] = False
        if CAPTURAS.get(tipo_camara):
            CAPTURAS[tipo_camara].release()
            CAPTURAS[tipo_camara] = None
        CAPTURA_LOCKS[tipo_camara] = None
        CAMERA_BACKENDS[tipo_camara] = None
        print("[INFO] Camara {} detenida".format(tipo_camara))
        return True
    except Exception as e:
        print("[ERROR] Deteniendo camara: {}".format(e))
        return False

@app.route('/')
def index():
    return redirect(url_for('registro'))

@app.route('/registro')
def registro():
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session['usuario'] = username
            return redirect(url_for('panel_guardia'))
        else:
            return render_template('login.html', error='Usuario o contrasena incorrectos')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/guardia')
@login_requerido
def panel_guardia():
    return render_template('guardia.html')

@app.route('/video_feed/<tipo>')
@login_requerido
def video_feed(tipo):
    if tipo in ['entrada', 'salida'] and CAMARAS_ACTIVAS.get(tipo) and CAPTURAS.get(tipo) is not None:
        return Response(generar_frames_video(tipo), mimetype='multipart/x-mixed-replace; boundary=frame')
    if tipo in ['entrada', 'salida']:
        return "Camara no activa", 409
    return "Tipo de camara invalido", 400

@app.route('/api/camaras/detectar', methods=['GET'])
@login_requerido
def api_detectar_camaras():
    camaras = detectar_camaras()
    return jsonify({
        'camaras': camaras,
        'config': CONFIG_CAMARAS,
        'estado': estado_camaras()
    })

@app.route('/api/camaras/configurar', methods=['POST'])
@login_requerido
def api_configurar_camaras():
    data = request.get_json() or {}
    entrada = data.get('entrada')
    salida = data.get('salida')
    
    resultados = {
        'entrada': {'ok': False, 'message': 'Sin asignar'},
        'salida': {'ok': False, 'message': 'Sin asignar'}
    }
    
    if entrada is not None:
        resultados['entrada'] = iniciar_camara('entrada', entrada)
    else:
        detener_camara('entrada')
    
    if salida is not None:
        if entrada is not None and salida == entrada:
            resultados['salida'] = {
                'ok': False,
                'indice': salida,
                'message': 'Entrada y salida no pueden usar el mismo dispositivo al mismo tiempo'
            }
        else:
            resultados['salida'] = iniciar_camara('salida', salida)
    else:
        detener_camara('salida')
    
    detectar_camaras()
    return jsonify({
        'success': resultados['entrada']['ok'] or resultados['salida']['ok'],
        'resultados': resultados,
        'estado': estado_camaras()
    })

@app.route('/api/camaras/detener', methods=['POST'])
@login_requerido
def api_detener_camaras():
    data = request.get_json()
    tipo = data.get('tipo', 'todas')
    
    if tipo == 'todas':
        detener_camara('entrada')
        detener_camara('salida')
    elif tipo in ['entrada', 'salida']:
        detener_camara(tipo)
    
    return jsonify({'success': True})

@app.route('/api/camaras/estado', methods=['GET'])
@login_requerido
def api_estado_camaras():
    return jsonify(estado_camaras())

def estado_camaras():
    return {
        'entrada': {
            'activa': CAMARAS_ACTIVAS.get('entrada', False),
            'indice': CONFIG_CAMARAS.get('entrada'),
            'backend': CAMERA_BACKENDS.get('entrada')
        },
        'salida': {
            'activa': CAMARAS_ACTIVAS.get('salida', False),
            'indice': CONFIG_CAMARAS.get('salida'),
            'backend': CAMERA_BACKENDS.get('salida')
        },
        'detectadas': CONFIG_CAMARAS.get('detectadas', [])
    }

@app.route('/api/registro', methods=['POST'])
def api_registro():
    try:
        nombre_completo = request.form.get('nombre_completo', '').strip()
        numero_casa = request.form.get('numero_casa', '').strip()
        tipo = request.form.get('tipo', '').strip()
        fotos = request.files.getlist('fotos')
        if not fotos:
            fotos = request.files.getlist('foto')
        fotos = [foto for foto in fotos if foto and foto.filename]
        
        if not nombre_completo or len(nombre_completo) < 3:
            return jsonify({'success': False, 'message': 'Nombre invalido'})
        
        if not numero_casa or not numero_casa.isdigit() or int(numero_casa) < 1 or int(numero_casa) > 999:
            return jsonify({'success': False, 'message': 'Numero de casa invalido'})
        
        if tipo not in ['residente', 'visitante']:
            return jsonify({'success': False, 'message': 'Tipo de usuario invalido'})
        
        if not fotos:
            return jsonify({'success': False, 'message': 'Foto requerida'})

        if len(fotos) > 5:
            return jsonify({'success': False, 'message': 'Suba maximo 5 fotos de entrenamiento'})

        rutas_guardadas = []
        nombres_guardados = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for idx, foto in enumerate(fotos, start=1):
            if not allowed_file(foto.filename):
                for ruta in rutas_guardadas:
                    if os.path.exists(ruta):
                        os.remove(ruta)
                return jsonify({'success': False, 'message': 'Formato de imagen no permitido'})

            filename = secure_filename(foto.filename) if foto.filename else "foto.jpg"
            nombre_archivo = "{}_{}_{}".format(timestamp, idx, filename)
            filepath = os.path.join(Config.FOTOS_PATH, nombre_archivo)
            foto.save(filepath)
            rutas_guardadas.append(filepath)
            nombres_guardados.append(nombre_archivo)

        embedding, muestras_validas = extraer_embeddings_imagenes(rutas_guardadas)
        if embedding is None:
            for ruta in rutas_guardadas:
                if os.path.exists(ruta):
                    os.remove(ruta)
            return jsonify({'success': False, 'message': 'No se detecto un rostro claro en las fotos'})

        user_id = crear_solicitud(
            nombre_completo,
            numero_casa,
            tipo,
            "/static/fotos/{}".format(nombres_guardados[0]),
            embedding
        )
        
        return jsonify({
            'success': True,
            'message': 'Solicitud enviada correctamente. Su ID es: {}. Muestras faciales validas: {}. Espere aprobacion.'.format(user_id, muestras_validas),
            'user_id': user_id
        })
    except Exception as e:
        print("[ERROR] Registro API: {}".format(e))
        return jsonify({'success': False, 'message': 'Error del servidor'})

@app.route('/api/solicitudes', methods=['GET'])
@login_requerido
def api_solicitudes():
    solicitudes = obtener_solicitudes_pendientes()
    return jsonify({
        'solicitudes': [
            {
                'id': s['id'],
                'usuario_id': s['usuario_id'],
                'nombre_completo': s['nombre_completo'],
                'numero_casa': s['numero_casa'],
                'tipo': s['tipo'],
                'foto_path': s['foto_path'],
                'fecha_solicitud': s['fecha_solicitud']
            }
            for s in solicitudes
        ]
    })

@app.route('/api/solicitudes/<int:solicitud_id>/aceptar', methods=['POST'])
@login_requerido
def api_aceptar_solicitud(solicitud_id):
    try:
        aceptar_solicitud(solicitud_id)
        detector = obtener_detector()
        if detector:
            detector.actualizar_cache()
        return jsonify({'success': True, 'message': 'Solicitud aceptada'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/solicitudes/<int:solicitud_id>/denegar', methods=['POST'])
@login_requerido
def api_denegar_solicitud(solicitud_id):
    try:
        denegar_solicitud(solicitud_id)
        return jsonify({'success': True, 'message': 'Solicitud denegada'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/registros', methods=['GET'])
@login_requerido
def api_registros():
    tipo_filtro = request.args.get('tipo', '')
    accion_filtro = request.args.get('accion', '')
    casa_filtro = request.args.get('casa', '')
    
    registros = obtener_registros(limite=200)
    
    resultados = []
    for r in registros:
        if tipo_filtro and r['tipo_usuario'] != tipo_filtro:
            continue
        if accion_filtro and r['tipo_accion'] != accion_filtro:
            continue
        if casa_filtro and r['numero_casa'] != casa_filtro:
            continue
        
        resultados.append({
            'id': r['id'],
            'usuario_id': r['usuario_id'],
            'tipo_usuario': r['tipo_usuario'],
            'numero_casa': r['numero_casa'],
            'fecha_hora': r['fecha_hora'],
            'tipo_accion': r['tipo_accion'],
            'confianza': r['confianza']
        })
    
    return jsonify({'registros': resultados})

@app.route('/api/usuarios', methods=['GET'])
@login_requerido
def api_usuarios():
    usuarios = obtener_usuarios_aceptados()
    return jsonify({
        'usuarios': [
            {
                'id': u['id'],
                'nombre_completo': u['nombre_completo'],
                'numero_casa': u['numero_casa'],
                'tipo': u['tipo'],
                'foto_path': u['foto_path']
            }
            for u in usuarios
        ]
    })

@app.route('/api/usuarios/activos', methods=['GET'])
@login_requerido
def api_usuarios_activos():
    usuarios = obtener_usuarios_activos()
    return jsonify({
        'usuarios': [
            {
                'id': u['id'],
                'nombre_completo': u['nombre_completo'],
                'numero_casa': u['numero_casa'],
                'tipo': u['tipo'],
                'foto_path': u['foto_path']
            }
            for u in usuarios
        ]
    })

@app.route('/api/usuarios/<usuario_id>/borrar', methods=['POST'])
@login_requerido
def api_usuario_borrar(usuario_id):
    try:
        usuario = obtener_usuario_por_id(usuario_id)
        if usuario and usuario['foto_path']:
            foto_archivo = os.path.basename(usuario['foto_path'])
            ruta_foto = os.path.join(Config.FOTOS_PATH, foto_archivo)
            if os.path.exists(ruta_foto):
                os.remove(ruta_foto)
                print("[INFO] Foto eliminada: {}".format(foto_archivo))
        
        dar_de_baja_usuario(usuario_id, eliminar=True)
        return jsonify({'success': True, 'message': 'Usuario eliminado'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/usuarios/<usuario_id>/entrenar', methods=['POST'])
@login_requerido
def api_usuario_entrenar(usuario_id):
    try:
        usuario = obtener_usuario_por_id(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'message': 'Usuario no encontrado'})

        fotos = request.files.getlist('fotos')
        if not fotos:
            fotos = request.files.getlist('foto')
        fotos = [foto for foto in fotos if foto and foto.filename]

        if not fotos:
            return jsonify({'success': False, 'message': 'Fotos requeridas'})
        if len(fotos) > 5:
            return jsonify({'success': False, 'message': 'Suba maximo 5 fotos'})

        rutas_guardadas = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for idx, foto in enumerate(fotos, start=1):
            if not allowed_file(foto.filename):
                return jsonify({'success': False, 'message': 'Formato de imagen no permitido'})

            filename = secure_filename(foto.filename) if foto.filename else "foto.jpg"
            nombre_archivo = "{}_train_{}_{}_{}".format(timestamp, usuario_id, idx, filename)
            filepath = os.path.join(Config.FOTOS_PATH, nombre_archivo)
            foto.save(filepath)
            rutas_guardadas.append(filepath)

        embedding_blob, muestras_nuevas = extraer_embeddings_imagenes(rutas_guardadas)
        if embedding_blob is None:
            for ruta in rutas_guardadas:
                if os.path.exists(ruta):
                    os.remove(ruta)
            return jsonify({'success': False, 'message': 'No se detecto un rostro claro en las fotos'})

        detector = obtener_detector()
        muestras_actuales = detector.deserializar_embeddings(obtener_embedding(usuario_id)) if detector else []
        muestras_nuevas_lista = detector.deserializar_embeddings(embedding_blob) if detector else []
        serializado = detector.serializar_embeddings(muestras_actuales + muestras_nuevas_lista)
        guardar_embedding(usuario_id, serializado)
        detector.actualizar_cache()

        return jsonify({
            'success': True,
            'message': 'Entrenamiento actualizado',
            'muestras_nuevas': muestras_nuevas,
            'muestras_total': len(muestras_actuales) + len(muestras_nuevas_lista)
        })
    except Exception as e:
        print("[ERROR] Entrenando usuario: {}".format(e))
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test', methods=['GET'])
def api_test():
    return jsonify({
        'status': 'ok',
        'message': 'OmniGuard API funcionando',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/static/fotos/<filename>')
def servir_foto(filename):
    return send_from_directory(Config.FOTOS_PATH, filename)

if __name__ == '__main__':
    inicializar_sistema()
    
    print("=" * 50)
    print("  OMNIGUARD RESIDENTIAL AI")
    print("  Sistema de Seguridad Inteligente")
    print("=" * 50)
    print("  Camaras detectadas: {}".format(CONFIG_CAMARAS['detectadas']))
    print("\n" + "=" * 50)
    print("  Servidor: http://localhost:{}".format(Config.PORT))
    print("  Registro: http://localhost:{}/registro".format(Config.PORT))
    print("  Panel Guardia: http://localhost:{}/login".format(Config.PORT))
    print("   Usuario: {}".format(Config.ADMIN_USERNAME))
    print("   Contrasena: {}".format(Config.ADMIN_PASSWORD))
    print("\n" + "=" * 50)
    
    app.run(host=Config.HOST, port=Config.PORT, debug=False, use_reloader=False)
