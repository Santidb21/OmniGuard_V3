import sqlite3
import os
from datetime import datetime, timedelta, timezone
from config import Config

CDMX_TZ = timezone(timedelta(hours=-6), "America/Mexico_City")


def ahora_cdmx():
    return datetime.now(CDMX_TZ)


def fecha_hora_cdmx():
    return ahora_cdmx().strftime('%Y-%m-%d %H:%M:%S')


def get_db_connection():
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nombre_completo TEXT NOT NULL,
            numero_casa TEXT NOT NULL,
            tipo TEXT NOT NULL,
            foto_path TEXT,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_aceptacion DATETIME,
            fecha_expiracion DATETIME,
            estado TEXT DEFAULT 'pendiente',
            embedding BLOB
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitudes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT,
            nombre_completo TEXT NOT NULL,
            numero_casa TEXT NOT NULL,
            tipo TEXT NOT NULL,
            foto_path TEXT,
            estado TEXT DEFAULT 'pendiente',
            fecha_solicitud DATETIME DEFAULT CURRENT_TIMESTAMP,
            revisado_por TEXT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros_entrada_salida (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id TEXT NOT NULL,
            tipo_usuario TEXT NOT NULL,
            numero_casa TEXT NOT NULL,
            fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
            tipo_accion TEXT NOT NULL,
            confianza REAL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuraciones (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ultimo_registro (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            usuario_id TEXT,
            tipo_accion TEXT,
            fecha_hora DATETIME
        )
    ''')
    
    cursor.execute('INSERT OR IGNORE INTO ultimo_registro (id) VALUES (1)')
    
    try:
        cursor.execute('ALTER TABLE usuarios ADD COLUMN fecha_aceptacion DATETIME')
    except:
        pass
    
    try:
        cursor.execute('ALTER TABLE usuarios ADD COLUMN fecha_expiracion DATETIME')
    except:
        pass
    
    conn.commit()
    conn.close()

def generar_id(tipo_usuario):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if tipo_usuario == 'residente':
        cursor.execute("SELECT id FROM usuarios WHERE tipo='residente' AND estado='aceptado' ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            last_id = int(result[0])
            new_id = last_id + 1 if last_id < 99 else 1
        else:
            new_id = 1
        user_id = f"{new_id:02d}"
    else:
        cursor.execute("SELECT id FROM usuarios WHERE tipo='visitante' AND estado='aceptado' ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        if result:
            last_id = int(result[0])
            new_id = last_id + 1 if last_id < 999 else 1
        else:
            new_id = 1
        user_id = f"{new_id:03d}"
    
    conn.close()
    return user_id

def crear_solicitud(nombre_completo, numero_casa, tipo, foto_path, embedding=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    user_id = generar_id(tipo)
    
    cursor.execute('''
        INSERT INTO usuarios (id, nombre_completo, numero_casa, tipo, foto_path, estado, embedding)
        VALUES (?, ?, ?, ?, ?, 'pendiente', ?)
    ''', (user_id, nombre_completo, numero_casa, tipo, foto_path, embedding))
    
    cursor.execute('''
        INSERT INTO solicitudes (usuario_id, nombre_completo, numero_casa, tipo, foto_path, estado)
        VALUES (?, ?, ?, ?, ?, 'pendiente')
    ''', (user_id, nombre_completo, numero_casa, tipo, foto_path))
    
    conn.commit()
    conn.close()
    return user_id

def obtener_solicitudes_pendientes():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM solicitudes WHERE estado='pendiente' ORDER BY fecha_solicitud DESC")
    solicitudes = cursor.fetchall()
    conn.close()
    return solicitudes

def aceptar_solicitud(solicitud_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM solicitudes WHERE id = ?", (solicitud_id,))
    solicitud = cursor.fetchone()
    
    if solicitud:
        fecha_actual = fecha_hora_cdmx()
        
        fecha_expiracion = None
        if solicitud['tipo'] == 'visitante':
            fecha_expiracion = (ahora_cdmx() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            UPDATE usuarios 
            SET estado='aceptado', fecha_aceptacion=?, fecha_expiracion=? 
            WHERE id = ?
        ''', (fecha_actual, fecha_expiracion, solicitud['usuario_id']))
        
        cursor.execute('''
            UPDATE solicitudes SET estado='aceptado', revisado_por='guardia' WHERE id = ?
        ''', (solicitud_id,))
        
        conn.commit()
    
    conn.close()

def denegar_solicitud(solicitud_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT usuario_id FROM solicitudes WHERE id = ?", (solicitud_id,))
    result = cursor.fetchone()
    
    if result:
        cursor.execute("UPDATE usuarios SET estado='denegado' WHERE id = ?", (result['usuario_id'],))
        cursor.execute("UPDATE solicitudes SET estado='denegado', revisado_por='guardia' WHERE id = ?", (solicitud_id,))
        conn.commit()
    
    conn.close()

def obtener_usuarios_aceptados():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE estado='aceptado'")
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

def obtener_usuarios_activos():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM usuarios 
        WHERE estado='aceptado' 
        ORDER BY tipo DESC, nombre_completo ASC
    """)
    usuarios = cursor.fetchall()
    conn.close()
    return usuarios

def dar_de_baja_usuario(usuario_id, eliminar=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if eliminar:
        cursor.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    else:
        cursor.execute("UPDATE usuarios SET estado='baja' WHERE id = ?", (usuario_id,))
    
    conn.commit()
    conn.close()

def eliminar_visitantes_expirados():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    fecha_actual = fecha_hora_cdmx()
    
    cursor.execute("""
        SELECT id, nombre_completo FROM usuarios 
        WHERE tipo='visitante' AND estado='aceptado' 
        AND fecha_expiracion IS NOT NULL AND fecha_expiracion < ?
    """, (fecha_actual,))
    
    eliminados = cursor.fetchall()
    
    for usuario in eliminados:
        print(f"[INFO] Eliminando visitante expirado: {usuario['nombre_completo']} (ID: {usuario['id']})")
    
    cursor.execute("""
        DELETE FROM usuarios 
        WHERE tipo='visitante' AND estado='aceptado' 
        AND fecha_expiracion IS NOT NULL AND fecha_expiracion < ?
    """, (fecha_actual,))
    
    conn.commit()
    conn.close()
    
    return len(eliminados)

def registrar_entrada_salida(usuario_id, tipo_usuario, numero_casa, tipo_accion, confianza):
    if tipo_accion not in ("entrada", "salida"):
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    fecha_actual = fecha_hora_cdmx()

    cursor.execute("""
        SELECT tipo_accion FROM registros_entrada_salida
        WHERE usuario_id = ?
        ORDER BY fecha_hora DESC, id DESC
        LIMIT 1
    """, (usuario_id,))
    ultimo = cursor.fetchone()
    if ultimo and ultimo["tipo_accion"] == tipo_accion:
        conn.close()
        return False
    
    cursor.execute('''
        INSERT INTO registros_entrada_salida
            (usuario_id, tipo_usuario, numero_casa, fecha_hora, tipo_accion, confianza)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (usuario_id, tipo_usuario, numero_casa, fecha_actual, tipo_accion, confianza))
    
    cursor.execute('''
        UPDATE ultimo_registro SET usuario_id=?, tipo_accion=?, fecha_hora=? WHERE id=1
    ''', (usuario_id, tipo_accion, fecha_actual))
    
    conn.commit()
    conn.close()
    return True

def obtener_ultimo_registro():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ultimo_registro WHERE id=1")
    resultado = cursor.fetchone()
    conn.close()
    return resultado

def obtener_ultimo_registro_usuario(usuario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM registros_entrada_salida
        WHERE usuario_id = ?
        ORDER BY fecha_hora DESC, id DESC
        LIMIT 1
    """, (usuario_id,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado

def obtener_registros(limite=100):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registros_entrada_salida ORDER BY fecha_hora DESC LIMIT ?", (limite,))
    registros = cursor.fetchall()
    conn.close()
    return registros

def obtener_usuario_por_id(usuario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    usuario = cursor.fetchone()
    conn.close()
    return usuario

def obtener_embedding(usuario_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT embedding FROM usuarios WHERE id = ?", (usuario_id,))
    result = cursor.fetchone()
    conn.close()
    return result['embedding'] if result else None

def guardar_embedding(usuario_id, embedding_bytes):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET embedding = ? WHERE id = ?", (embedding_bytes, usuario_id))
    conn.commit()
    conn.close()
