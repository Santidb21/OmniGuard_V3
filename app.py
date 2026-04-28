import os
import sys
import time
import warnings
import sqlite3
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

CAMARAS_ACTIVAS = {
    'entrada': False,
    'salida': False
}

detector_inicializado = False

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
    camaras = []
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            camaras.append(i)
            cap.release()
    CONFIG_CAMARAS['detectadas'] = camaras
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

def extraer_embedding_imagen(image_path):
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cara = cv2.resize(gris, (150, 150))
        embedding = np.mean(cara, axis=0).flatten()
        embedding = embedding / (np.linalg.norm(embedding) + 1e-6)
        return embedding.astype(np.float32).tobytes()
    except Exception as e:
        print("[ERROR] Extrayendo embedding: {}".format(e))
        return None

def generar_frames_video(tipo_camara):
    detector = obtener_detector()
    frame_count = 0

    while CAMARAS_ACTIVAS.get(tipo_camara, False):
        if CAPTURAS.get(tipo_camara) is None:
            time.sleep(0.5)
            continue

        try:
            ret, frame = CAPTURAS[tipo_camara].read()
        except Exception as e:
            print("[ERROR] Leyendo frame de camara {}: {}".format(tipo_camara, e))
            break

        if not ret:
            time.sleep(0.1)
            continue

        try:
            frame_count += 1

            if frame_count % 10 == 0:
                usuario_id, confianza = detector.reconocer_usuario(frame)
                if usuario_id:
                    detector.procesar_deteccion(usuario_id, confianza)
                    usuario = obtener_usuario_por_id(usuario_id)
                    if usuario:
                        x, y, w, h = (50, 50, 100, 100)
                        cv2.rectangle(frame, (50, 50), (150, 150), (201, 169, 98), 2)
                        cv2.putText(frame, "{} ({:.0f}%)".format(usuario['nombre_completo'], confianza * 100),
                                    (50, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (201, 169, 98), 2)

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
        if CAPTURAS.get(tipo_camara):
            CAPTURAS[tipo_camara].release()
        
        CAPTURAS[tipo_camara] = cv2.VideoCapture(indice)
        
        if CAPTURAS[tipo_camara].isOpened():
            CONFIG_CAMARAS[tipo_camara] = indice
            CAMARAS_ACTIVAS[tipo_camara] = True
            detector = obtener_detector()
            if detector:
                detector.actualizar_cache()
            print("[INFO] Camara {} iniciada en indice {}".format(tipo_camara, indice))
            return True
        else:
            print("[ERROR] No se pudo abrir camara {}".format(tipo_camara))
            return False
    except Exception as e:
        print("[ERROR] Iniciando camara: {}".format(e))
        return False

def detener_camara(tipo_camara):
    try:
        CAMARAS_ACTIVAS[tipo_camara] = False
        if CAPTURAS.get(tipo_camara):
            CAPTURAS[tipo_camara].release()
            CAPTURAS[tipo_camara] = None
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
    if tipo in ['entrada', 'salida']:
        return Response(generar_frames_video(tipo), mimetype='multipart/x-mixed-replace; boundary=frame')
    return "Tipo de camara invalido", 400

@app.route('/api/camaras/detectar', methods=['GET'])
@login_requerido
def api_detectar_camaras():
    camaras = detectar_camaras()
    return jsonify({
        'camaras': [{'indice': i, 'nombre': 'Camara {}'.format(i)} for i in camaras],
        'config': CONFIG_CAMARAS
    })

@app.route('/api/camaras/configurar', methods=['POST'])
@login_requerido
def api_configurar_camaras():
    data = request.get_json()
    entrada = data.get('entrada')
    salida = data.get('salida')
    
    resultados = {'entrada': False, 'salida': False}
    
    if entrada is not None:
        resultados['entrada'] = iniciar_camara('entrada', entrada)
    
    if salida is not None:
        resultados['salida'] = iniciar_camara('salida', salida)
    
    return jsonify({'success': True, 'resultados': resultados})

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
    return jsonify({
        'entrada': {'activa': CAMARAS_ACTIVAS.get('entrada', False), 'indice': CONFIG_CAMARAS.get('entrada')},
        'salida': {'activa': CAMARAS_ACTIVAS.get('salida', False), 'indice': CONFIG_CAMARAS.get('salida')},
        'detectadas': CONFIG_CAMARAS.get('detectadas', [])
    })

@app.route('/api/registro', methods=['POST'])
def api_registro():
    try:
        nombre_completo = request.form.get('nombre_completo', '').strip()
        numero_casa = request.form.get('numero_casa', '').strip()
        tipo = request.form.get('tipo', '').strip()
        foto = request.files.get('foto')
        
        if not nombre_completo or len(nombre_completo) < 3:
            return jsonify({'success': False, 'message': 'Nombre invalido'})
        
        if not numero_casa or not numero_casa.isdigit() or int(numero_casa) < 1 or int(numero_casa) > 999:
            return jsonify({'success': False, 'message': 'Numero de casa invalido'})
        
        if tipo not in ['residente', 'visitante']:
            return jsonify({'success': False, 'message': 'Tipo de usuario invalido'})
        
        if not foto or foto.filename == '':
            return jsonify({'success': False, 'message': 'Foto requerida'})
        
        if not allowed_file(foto.filename):
            return jsonify({'success': False, 'message': 'Formato de imagen no permitido'})
        
        filename = secure_filename(foto.filename) if foto.filename else "foto.jpg"
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_archivo = "{}_{}".format(timestamp, filename)
        filepath = os.path.join(Config.FOTOS_PATH, nombre_archivo)
        foto.save(filepath)
        
        embedding = extraer_embedding_imagen(filepath)
        user_id = crear_solicitud(nombre_completo, numero_casa, tipo, "/static/fotos/{}".format(nombre_archivo), embedding)
        
        return jsonify({
            'success': True,
            'message': 'Solicitud enviada correctamente. Su ID es: {}. Espere aprobacion.'.format(user_id),
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
    
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
