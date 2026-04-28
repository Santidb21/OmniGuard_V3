import os
import shutil
import sqlite3
from datetime import datetime
from config import Config
from models import get_db_connection

def verificar_cambio_mes():
    try:
        mes_actual = datetime.now().strftime("%B_%Y")
        return mes_actual
    except Exception as e:
        print(f"[ERROR] Verificando cambio de mes: {e}")
        return None

def exportar_registros_mensuales():
    try:
        os.makedirs(Config.REGISTROS_PATH, exist_ok=True)
        
        mes_nombre = datetime.now().strftime("%B_%Y")
        archivo_mes = os.path.join(Config.REGISTROS_PATH, f"{mes_nombre}.db")
        
        if os.path.exists(archivo_mes):
            print(f"[INFO] Registros de {mes_nombre} ya exportados")
            return True
        
        conn_origen = get_db_connection()
        cursor_origen = conn_origen.cursor()
        
        cursor_origen.execute("SELECT * FROM registros_entrada_salida")
        registros = cursor_origen.fetchall()
        
        if not registros:
            print("[INFO] No hay registros para exportar")
            conn_origen.close()
            return True
        
        conn_destino = sqlite3.connect(archivo_mes)
        cursor_destino = conn_destino.cursor()
        
        cursor_destino.execute('''
            CREATE TABLE IF NOT EXISTS registros_entrada_salida (
                id INTEGER PRIMARY KEY,
                usuario_id TEXT NOT NULL,
                tipo_usuario TEXT NOT NULL,
                numero_casa TEXT NOT NULL,
                fecha_hora TEXT NOT NULL,
                tipo_accion TEXT NOT NULL,
                confianza REAL
            )
        ''')
        
        for registro in registros:
            cursor_destino.execute('''
                INSERT INTO registros_entrada_salida 
                (id, usuario_id, tipo_usuario, numero_casa, fecha_hora, tipo_accion, confianza)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (registro['id'], registro['usuario_id'], registro['tipo_usuario'], 
                  registro['numero_casa'], registro['fecha_hora'], 
                  registro['tipo_accion'], registro['confianza']))
        
        conn_destino.commit()
        conn_destino.close()
        conn_origen.close()
        
        print(f"[INFO] Registros exportados a {archivo_mes}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Exportando registros mensuales: {e}")
        return False

def limpiar_registros_viejos():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM registros_entrada_salida WHERE id NOT IN (SELECT MAX(id) FROM registros_entrada_salida GROUP BY usuario_id, date(fecha_hora))")
        
        conn.commit()
        conn.close()
        print("[INFO] Registros antiguos limpiados")
    except Exception as e:
        print(f"[ERROR] Limpiando registros: {e}")

def obtener_registros_mes(mes, anio):
    try:
        archivo = os.path.join(Config.REGISTROS_PATH, f"{mes}_{anio}.db")
        
        if not os.path.exists(archivo):
            return []
        
        conn = sqlite3.connect(archivo)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registros_entrada_salida ORDER BY fecha_hora DESC")
        registros = cursor.fetchall()
        conn.close()
        
        return registros
    except Exception as e:
        print(f"[ERROR] Obteniendo registros del mes: {e}")
        return []

def listar_archivos_mensuales():
    try:
        if not os.path.exists(Config.REGISTROS_PATH):
            return []
        
        archivos = []
        for f in os.listdir(Config.REGISTROS_PATH):
            if f.endswith('.db'):
                archivos.append(f)
        
        return sorted(archivos)
    except Exception as e:
        print(f"[ERROR] Listando archivos mensuales: {e}")
        return []