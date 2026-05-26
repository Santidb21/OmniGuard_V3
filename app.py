import os
import sys
import time
import warnings

import threading
import cv2
import numpy as np
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

from config import Config
from models import (
    init_db, crear_solicitud, obtener_solicitudes_pendientes,
    aceptar_solicitud, denegar_solicitud, obtener_usuarios_aceptados,
    obtener_usuarios_activos, dar_de_baja_usuario, eliminar_visitantes_expirados,
    registrar_entrada_salida, obtener_registros, obtener_usuario_por_id,
    obtener_embedding, get_db_connection, guardar_embedding,
    crear_cuenta_sistema, obtener_cuenta_por_usuario, obtener_cuenta_sistema,
    obtener_cuentas_sistema, actualizar_cuenta_sistema, eliminar_cuenta_sistema,
    registrar_acceso_cuenta, crear_caseta, obtener_casetas, obtener_caseta,
    actualizar_caseta, eliminar_caseta, obtener_casetas_de_cuenta,
    asignar_casetas_cuenta
)
from reconocimiento.registros import exportar_registros_mensuales
from reconocimiento.detector import obtener_detector, iniciar_deteccion
from reconocimiento.sincronizador import iniciar_sincronizador

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
app.secret_key = Config.SECRET_KEY

CONFIG_CAMARAS = {
    'entrada': 0,
    'salida': None,
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

CASETA_ACTIVA_ID = None

detector_inicializado = False

_db_inicializada = False

ROLES_SISTEMA = {
    'administrador': 'Administrador',
    'vigilante': 'Vigilante',
    'consultor': 'Consultor'
}

if os.name == 'nt':
    BACKENDS_CAMARA = [
        ('DSHOW', cv2.CAP_DSHOW),
        ('MSMF', cv2.CAP_MSMF)
    ]
else:
    BACKENDS_CAMARA = [
        ('V4L2', cv2.CAP_V4L2),
        ('AUTO', cv2.CAP_ANY)
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
    iniciar_sincronizador()

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
                'nombre': 'Cámara {} ({})'.format(indice, tipo),
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
            'nombre': 'Cámara {}'.format(i),
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

def rol_actual():
    return session.get('rol')

def usuario_actual():
    cuenta_id = session.get('cuenta_id')
    if not cuenta_id:
        return None
    return obtener_cuenta_sistema(cuenta_id)

def roles_requeridos(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario' not in session:
                return redirect(url_for('login'))
            if rol_actual() not in roles:
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'message': 'No autorizado'}), 403
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def asegurar_cuenta_admin():
    if obtener_cuenta_por_usuario(Config.ADMIN_USERNAME):
        return
    crear_cuenta_sistema(
        Config.ADMIN_USERNAME,
        generate_password_hash(Config.ADMIN_PASSWORD),
        'Administrador OmniGuard',
        'administrador'
    )

@app.before_request
def verificar_directorios():
    global _db_inicializada
    os.makedirs(Config.FOTOS_PATH, exist_ok=True)
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    os.makedirs(Config.REGISTROS_PATH, exist_ok=True)
    os.makedirs(Config.LOGS_PATH, exist_ok=True)
    if not _db_inicializada:
        init_db()
        asegurar_cuenta_admin()
        _db_inicializada = True
    verificar_mes_nuevo()
    verificar_visitantes_expirados()

def verificar_mes_nuevo():
    try:
        conn = get_db_connection()
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

def serializar_caseta(caseta):
    return {
        'id': caseta['id'],
        'nombre': caseta['nombre'],
        'direccion': caseta['direccion'],
        'colonia': caseta['colonia'],
        'cp': caseta['cp'],
        'ciudad': caseta['ciudad'],
        'estado': caseta['estado'],
        'telefono': caseta['telefono'],
        'email': caseta['email'],
        'contacto_colonia': caseta['contacto_colonia'],
        'telefonos_emergencia': caseta['telefonos_emergencia'],
        'estado_registro': caseta['estado_registro'],
        'fecha_creacion': caseta['fecha_creacion']
    }

def extraer_campos_caseta(data):
    return {
        'nombre': (data.get('nombre') or '').strip(),
        'direccion': (data.get('direccion') or '').strip(),
        'colonia': (data.get('colonia') or '').strip(),
        'cp': (data.get('cp') or '').strip(),
        'ciudad': (data.get('ciudad') or '').strip(),
        'estado': (data.get('estado') or '').strip(),
        'telefono': (data.get('telefono') or '').strip(),
        'email': (data.get('email') or '').strip(),
        'contacto_colonia': (data.get('contacto_colonia') or '').strip(),
        'telefonos_emergencia': (data.get('telefonos_emergencia') or '').strip()
    }

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

def actualizar_entrenamiento_usuario(usuario_id, rutas_guardadas):
    embedding_blob, muestras_nuevas = extraer_embeddings_imagenes(rutas_guardadas)
    if embedding_blob is None:
        for ruta in rutas_guardadas:
            if os.path.exists(ruta):
                os.remove(ruta)
        return None

    detector = obtener_detector()
    muestras_actuales = detector.deserializar_embeddings(obtener_embedding(usuario_id)) if detector else []
    muestras_nuevas_lista = detector.deserializar_embeddings(embedding_blob) if detector else []
    serializado = detector.serializar_embeddings(muestras_actuales + muestras_nuevas_lista)
    guardar_embedding(usuario_id, serializado)
    detector.actualizar_cache()

    return {
        'muestras_nuevas': muestras_nuevas,
        'muestras_total': len(muestras_actuales) + len(muestras_nuevas_lista)
    }

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
        if not CAMARAS_ACTIVAS.get(tipo_camara, False):
            break

        if CAPTURAS.get(tipo_camara) is None:
            time.sleep(0.5)
            continue

        try:
            ret, frame = leer_frame_camara(tipo_camara)
        except Exception as e:
            print("[ERROR] Leyendo frame de cámara {}: {}".format(tipo_camara, e))
            break

        if not ret:
            time.sleep(0.1)
            continue

        try:
            frame_count += 1

            ahora = time.time()
            if CAMARAS_ACTIVAS.get(tipo_camara, False) and ahora - ultimo_analisis >= 0.35:
                ultimo_analisis = ahora
                resultado = detector.analizar_frame(frame, tipo_camara)
                if resultado.get('rostro') is not None:
                    resultado['ts'] = ahora
                    ultimo_resultado = resultado

                    usuario_id = resultado.get('usuario_id')
                    confianza = resultado.get('confianza', 0.0)
                    if usuario_id and CAMARAS_ACTIVAS.get(tipo_camara, False):
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

    print("[INFO] Stream de cámara {} terminado".format(tipo_camara))

def iniciar_camara(tipo_camara, indice):
    try:
        indice = int(indice)
        otro_tipo = 'salida' if tipo_camara == 'entrada' else 'entrada'
        if CAMARAS_ACTIVAS.get(otro_tipo) and CONFIG_CAMARAS.get(otro_tipo) == indice:
            print("[WARN] Cámara {} ya está usando el índice {}".format(otro_tipo, indice))
            return {
                'ok': False,
                'indice': indice,
                'message': 'La cámara {} ya está asignada a {}'.format(indice, otro_tipo)
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
            print("[INFO] Cámara {} iniciada en índice {} con backend {}".format(tipo_camara, indice, backend))
            return {
                'ok': True,
                'indice': indice,
                'backend': backend,
                'resolucion': '{}x{}'.format(ancho, alto),
                'message': 'Cámara {} iniciada'.format(tipo_camara)
            }

        CAMARAS_ACTIVAS[tipo_camara] = False
        CAPTURAS[tipo_camara] = None
        CAPTURA_LOCKS[tipo_camara] = None
        CAMERA_BACKENDS[tipo_camara] = None
        print("[ERROR] No se pudo abrir cámara {}".format(tipo_camara))
        return {
            'ok': False,
            'indice': indice,
            'message': 'No se pudo abrir la cámara {}. Puede estar ocupada o sin permisos.'.format(indice)
        }
    except Exception as e:
        print("[ERROR] Iniciando cámara: {}".format(e))
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
        print("[INFO] Cámara {} detenida".format(tipo_camara))
        return True
    except Exception as e:
        print("[ERROR] Deteniendo cámara: {}".format(e))
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/registro')
def registro():
    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        cuenta = obtener_cuenta_por_usuario(username)
        if cuenta and cuenta['estado'] == 'activo' and check_password_hash(cuenta['password_hash'], password):
            session.clear()
            session['usuario'] = cuenta['usuario']
            session['cuenta_id'] = cuenta['id']
            session['nombre_completo'] = cuenta['nombre_completo']
            session['rol'] = cuenta['rol']
            registrar_acceso_cuenta(cuenta['id'])
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Usuario o contraseña incorrectos')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_requerido
def dashboard():
    cuenta = usuario_actual()
    return render_template('dashboard.html', cuenta=cuenta, roles=ROLES_SISTEMA)

@app.route('/perfil')
@login_requerido
def perfil():
    cuenta = usuario_actual()
    return render_template('perfil.html', cuenta=cuenta, roles=ROLES_SISTEMA)

@app.route('/camaras')
@roles_requeridos('administrador', 'vigilante')
def camaras():
    return redirect(url_for('panel_guardia'))

@app.route('/administracion/usuarios')
@roles_requeridos('administrador')
def administracion_usuarios():
    return render_template('admin_usuarios.html', roles=ROLES_SISTEMA)

@app.route('/administracion/casetas')
@roles_requeridos('administrador')
def administracion_casetas():
    return render_template('admin_casetas.html')

@app.route('/bitacora')
@roles_requeridos('administrador', 'vigilante', 'consultor')
def bitacora():
    return render_template('bitacora.html')

@app.route('/guardia')
@roles_requeridos('administrador', 'vigilante')
def panel_guardia():
    return render_template('guardia.html')

@app.route('/video_feed/<tipo>')
@roles_requeridos('administrador', 'vigilante')
def video_feed(tipo):
    if tipo in ['entrada', 'salida'] and CAMARAS_ACTIVAS.get(tipo) and CAPTURAS.get(tipo) is not None:
        return Response(generar_frames_video(tipo), mimetype='multipart/x-mixed-replace; boundary=frame')
    if tipo in ['entrada', 'salida']:
        return "Cámara no activa", 409
    return "Tipo de cámara inválido", 400

@app.route('/api/camaras/detectar', methods=['GET'])
@roles_requeridos('administrador', 'vigilante')
def api_detectar_camaras():
    camaras = detectar_camaras()
    return jsonify({
        'camaras': camaras,
        'config': CONFIG_CAMARAS,
        'estado': estado_camaras()
    })

@app.route('/api/camaras/configurar', methods=['POST'])
@roles_requeridos('administrador', 'vigilante')
def api_configurar_camaras():
    data = request.get_json() or {}
    global CASETA_ACTIVA_ID
    caseta_id = data.get('caseta_id')
    if caseta_id in ('', None):
        CASETA_ACTIVA_ID = None
        Config.CASETA_ACTIVA_ID = None
    else:
        caseta_id = int(caseta_id)
        if rol_actual() != 'administrador':
            permitidas = [c['id'] for c in obtener_casetas_de_cuenta(session.get('cuenta_id'))]
            if caseta_id not in permitidas:
                return jsonify({'success': False, 'message': 'No tienes asignada esa caseta'}), 403
        CASETA_ACTIVA_ID = caseta_id
        Config.CASETA_ACTIVA_ID = caseta_id
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
@roles_requeridos('administrador', 'vigilante')
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
@roles_requeridos('administrador', 'vigilante')
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
        'detectadas': CONFIG_CAMARAS.get('detectadas', []),
        'caseta_id': CASETA_ACTIVA_ID
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
            return jsonify({'success': False, 'message': 'Nombre inválido'})
        
        if not numero_casa or not numero_casa.isdigit() or int(numero_casa) < 1 or int(numero_casa) > 999:
            return jsonify({'success': False, 'message': 'Número de casa inválido'})
        
        if tipo not in ['residente', 'visitante']:
            return jsonify({'success': False, 'message': 'Tipo de usuario inválido'})
        
        if not fotos:
            return jsonify({'success': False, 'message': 'Foto requerida'})

        if len(fotos) > 5:
            return jsonify({'success': False, 'message': 'Suba máximo 5 fotos de entrenamiento'})

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
@roles_requeridos('administrador', 'vigilante')
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
@roles_requeridos('administrador', 'vigilante')
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
@roles_requeridos('administrador', 'vigilante')
def api_denegar_solicitud(solicitud_id):
    try:
        denegar_solicitud(solicitud_id)
        return jsonify({'success': True, 'message': 'Solicitud denegada'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/registros', methods=['GET'])
@roles_requeridos('administrador', 'vigilante', 'consultor')
def api_registros():
    tipo_filtro = request.args.get('tipo', '')
    accion_filtro = request.args.get('accion', '')
    casa_filtro = request.args.get('casa', '')
    
    caseta_filtro = request.args.get('caseta_id', '')
    casetas_permitidas = None
    if rol_actual() != 'administrador':
        casetas_permitidas = [c['id'] for c in obtener_casetas_de_cuenta(session.get('cuenta_id'))]
    if caseta_filtro:
        caseta_id = int(caseta_filtro)
        if casetas_permitidas is not None and caseta_id not in casetas_permitidas:
            return jsonify({'registros': []})
        casetas_permitidas = [caseta_id]

    registros = obtener_registros(limite=200, caseta_ids=casetas_permitidas)
    
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
            'confianza': r['confianza'],
            'caseta_id': r['caseta_id'] if 'caseta_id' in r.keys() else None,
            'caseta_nombre': r['caseta_nombre'] if 'caseta_nombre' in r.keys() else None
        })
    
    return jsonify({'registros': resultados})

@app.route('/api/mis-casetas', methods=['GET'])
@roles_requeridos('administrador', 'vigilante', 'consultor')
def api_mis_casetas():
    if rol_actual() == 'administrador':
        casetas = obtener_casetas(incluir_inactivas=False)
    else:
        casetas = obtener_casetas_de_cuenta(session.get('cuenta_id'))
    return jsonify({'casetas': [serializar_caseta(c) for c in casetas]})

@app.route('/api/usuarios', methods=['GET'])
@roles_requeridos('administrador', 'vigilante')
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
@roles_requeridos('administrador', 'vigilante')
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

@app.route('/api/cuentas', methods=['GET'])
@roles_requeridos('administrador')
def api_cuentas():
    cuentas = obtener_cuentas_sistema()
    return jsonify({
        'cuentas': [
            {
                'id': c['id'],
                'usuario': c['usuario'],
                'nombre_completo': c['nombre_completo'],
                'rol': c['rol'],
                'estado': c['estado'],
                'fecha_creacion': c['fecha_creacion'],
                'ultimo_acceso': c['ultimo_acceso'],
                'casetas': [caseta['id'] for caseta in obtener_casetas_de_cuenta(c['id'])]
            }
            for c in cuentas
        ]
    })

@app.route('/api/cuentas', methods=['POST'])
@roles_requeridos('administrador')
def api_cuenta_crear():
    data = request.get_json() or {}
    usuario = (data.get('usuario') or '').strip()
    password = data.get('password') or ''
    nombre = (data.get('nombre_completo') or '').strip()
    rol = data.get('rol')
    caseta_ids = data.get('casetas') or []

    if not usuario or not password or not nombre:
        return jsonify({'success': False, 'message': 'Usuario, nombre y contraseña son obligatorios'}), 400
    if rol not in ROLES_SISTEMA:
        return jsonify({'success': False, 'message': 'Rol inválido'}), 400
    if obtener_cuenta_por_usuario(usuario):
        return jsonify({'success': False, 'message': 'El usuario ya existe'}), 409

    cuenta_id = crear_cuenta_sistema(usuario, generate_password_hash(password), nombre, rol)
    asignar_casetas_cuenta(cuenta_id, caseta_ids)
    return jsonify({'success': True, 'id': cuenta_id, 'message': 'Cuenta creada'})

@app.route('/api/cuentas/<int:cuenta_id>', methods=['PUT'])
@roles_requeridos('administrador')
def api_cuenta_actualizar(cuenta_id):
    data = request.get_json() or {}
    cuenta = obtener_cuenta_sistema(cuenta_id)
    if not cuenta:
        return jsonify({'success': False, 'message': 'Cuenta no encontrada'}), 404

    usuario = (data.get('usuario') or '').strip()
    nombre = (data.get('nombre_completo') or '').strip()
    rol = data.get('rol')
    estado = data.get('estado', 'activo')
    password = data.get('password') or ''
    caseta_ids = data.get('casetas') or []

    if not usuario or not nombre:
        return jsonify({'success': False, 'message': 'Usuario y nombre son obligatorios'}), 400
    if rol not in ROLES_SISTEMA:
        return jsonify({'success': False, 'message': 'Rol inválido'}), 400
    if estado not in ('activo', 'inactivo'):
        return jsonify({'success': False, 'message': 'Estado inválido'}), 400

    existente = obtener_cuenta_por_usuario(usuario)
    if existente and existente['id'] != cuenta_id:
        return jsonify({'success': False, 'message': 'El usuario ya existe'}), 409

    password_hash = generate_password_hash(password) if password else None
    actualizar_cuenta_sistema(cuenta_id, usuario, nombre, rol, estado, password_hash)
    asignar_casetas_cuenta(cuenta_id, caseta_ids)
    return jsonify({'success': True, 'message': 'Cuenta actualizada'})

@app.route('/api/cuentas/<int:cuenta_id>', methods=['DELETE'])
@roles_requeridos('administrador')
def api_cuenta_eliminar(cuenta_id):
    if session.get('cuenta_id') == cuenta_id:
        return jsonify({'success': False, 'message': 'No puedes eliminar tu propia cuenta activa'}), 400
    cuenta = obtener_cuenta_sistema(cuenta_id)
    if not cuenta:
        return jsonify({'success': False, 'message': 'Cuenta no encontrada'}), 404
    eliminar_cuenta_sistema(cuenta_id)
    return jsonify({'success': True, 'message': 'Cuenta eliminada'})

@app.route('/api/casetas', methods=['GET'])
@roles_requeridos('administrador')
def api_casetas():
    return jsonify({'casetas': [serializar_caseta(c) for c in obtener_casetas()]})

@app.route('/api/casetas', methods=['POST'])
@roles_requeridos('administrador')
def api_caseta_crear():
    data = request.get_json() or {}
    campos = extraer_campos_caseta(data)
    faltantes = [k for k in ['nombre', 'direccion', 'colonia', 'cp', 'ciudad', 'estado'] if not campos[k]]
    if faltantes:
        return jsonify({'success': False, 'message': 'Campos obligatorios: {}'.format(', '.join(faltantes))}), 400
    caseta_id = crear_caseta(**campos)
    return jsonify({'success': True, 'id': caseta_id, 'message': 'Caseta creada'})

@app.route('/api/casetas/<int:caseta_id>', methods=['PUT'])
@roles_requeridos('administrador')
def api_caseta_actualizar(caseta_id):
    if not obtener_caseta(caseta_id):
        return jsonify({'success': False, 'message': 'Caseta no encontrada'}), 404
    data = request.get_json() or {}
    campos = extraer_campos_caseta(data)
    estado_registro = data.get('estado_registro', 'activa')
    if estado_registro not in ('activa', 'inactiva'):
        return jsonify({'success': False, 'message': 'Estado de caseta inválido'}), 400
    faltantes = [k for k in ['nombre', 'direccion', 'colonia', 'cp', 'ciudad', 'estado'] if not campos[k]]
    if faltantes:
        return jsonify({'success': False, 'message': 'Campos obligatorios: {}'.format(', '.join(faltantes))}), 400
    actualizar_caseta(caseta_id, estado_registro=estado_registro, **campos)
    return jsonify({'success': True, 'message': 'Caseta actualizada'})

@app.route('/api/casetas/<int:caseta_id>', methods=['DELETE'])
@roles_requeridos('administrador')
def api_caseta_eliminar(caseta_id):
    if not obtener_caseta(caseta_id):
        return jsonify({'success': False, 'message': 'Caseta no encontrada'}), 404
    eliminar_caseta(caseta_id)
    return jsonify({'success': True, 'message': 'Caseta eliminada'})

@app.route('/api/usuarios/<usuario_id>/borrar', methods=['POST'])
@roles_requeridos('administrador')
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
@roles_requeridos('administrador')
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
            return jsonify({'success': False, 'message': 'Suba máximo 5 fotos'})

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

        resultado = actualizar_entrenamiento_usuario(usuario_id, rutas_guardadas)
        if resultado is None:
            return jsonify({'success': False, 'message': 'No se detecto un rostro claro en las fotos'})

        return jsonify({
            'success': True,
            'message': 'Entrenamiento actualizado',
            'muestras_nuevas': resultado['muestras_nuevas'],
            'muestras_total': resultado['muestras_total']
        })
    except Exception as e:
        print("[ERROR] Entrenando usuario: {}".format(e))
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/usuarios/<usuario_id>/entrenar/camara', methods=['POST'])
@roles_requeridos('administrador')
def api_usuario_entrenar_camara(usuario_id):
    try:
        usuario = obtener_usuario_por_id(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'message': 'Usuario no encontrado'})

        data = request.get_json(silent=True) or {}
        tipo_camara = data.get('tipo') if data.get('tipo') in ['entrada', 'salida'] else None
        tipos_candidatos = [tipo_camara] if tipo_camara else []
        tipos_candidatos.extend([tipo for tipo in ['entrada', 'salida'] if tipo not in tipos_candidatos])

        frame = None
        tipo_usado = None
        for tipo in tipos_candidatos:
            if CAMARAS_ACTIVAS.get(tipo) and CAPTURAS.get(tipo) is not None:
                ok, frame_leido = leer_frame_camara(tipo)
                if ok and frame_leido is not None and frame_leido.size > 0:
                    frame = frame_leido
                    tipo_usado = tipo
                    break

        if frame is None:
            return jsonify({'success': False, 'message': 'No hay cámara activa para tomar la foto'})

        os.makedirs(Config.FOTOS_PATH, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_archivo = "{}_train_{}_camara_{}.jpg".format(timestamp, usuario_id, tipo_usado)
        filepath = os.path.join(Config.FOTOS_PATH, nombre_archivo)
        if not cv2.imwrite(filepath, frame):
            return jsonify({'success': False, 'message': 'No se pudo guardar la foto de la cámara'})

        resultado = actualizar_entrenamiento_usuario(usuario_id, [filepath])
        if resultado is None:
            return jsonify({'success': False, 'message': 'No se detecto un rostro claro en la foto tomada'})

        return jsonify({
            'success': True,
            'message': 'Foto tomada y entrenamiento actualizado',
            'camara': tipo_usado,
            'muestras_nuevas': resultado['muestras_nuevas'],
            'muestras_total': resultado['muestras_total']
        })
    except Exception as e:
        print("[ERROR] Entrenando usuario desde cámara: {}".format(e))
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test', methods=['GET'])
def api_test():
    return jsonify({
        'status': 'ok',
        'message': 'OmniGuard API funcionando',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/static/fotos/<filename>')
@login_requerido
def servir_foto(filename):
    return send_from_directory(Config.FOTOS_PATH, filename)

if __name__ == '__main__':
    inicializar_sistema()
    
    print("=" * 50)
    print("  OMNIGUARD RESIDENTIAL AI")
    print("  Sistema de Seguridad Inteligente")
    print("=" * 50)
    print("  Cámaras detectadas: {}".format(CONFIG_CAMARAS['detectadas']))
    print("\n" + "=" * 50)
    print("  Servidor: http://localhost:{}".format(Config.PORT))
    print("  Registro: http://localhost:{}/registro".format(Config.PORT))
    print("  Panel Guardia: http://localhost:{}/login".format(Config.PORT))
    print("   Usuario: {}".format(Config.ADMIN_USERNAME))
    print("   Contraseña: {}".format(Config.ADMIN_PASSWORD))
    print("\n" + "=" * 50)
    
    app.run(host=Config.HOST, port=Config.PORT, debug=False, use_reloader=False)

