import sys
import os
import sqlite3
from datetime import datetime

# Configurar paths
sys.path.append('.')
os.chdir('C:\\Users\\Santiago\\Desktop\\OmniGuard_V3')

def test_fase1():
    print("=== Iniciando pruebas de Fase 1 ===")
    
    # 1. Verificar config.py
    print("\n1. Verificando config.py...")
    from config import Config
    assert Config.DB_PATH.endswith('omniguard.db'), "Ruta de DB incorrecta"
    assert Config.SECRET_KEY == 'omniguard-secret-key-2026', "Clave secreta incorrecta"
    assert Config.PORT == 5000, "Puerto incorrecto"
    print("[OK] Configuracion cargada correctamente")
    
    # 2. Verificar inicialización de DB
    print("\n2. Verificando inicialización de base de datos...")
    from models import init_db, get_db_connection
    init_db()
    assert os.path.exists(Config.DB_PATH), "El archivo de base de datos no se creó"
    print("[OK] Base de datos creada en DB/omniguard.db")
    
    # 3. Verificar tablas
    print("\n3. Verificando tablas de la base de datos...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tablas = [t[0] for t in cursor.fetchall()]
    tablas_requeridas = ['usuarios', 'solicitudes', 'registros_entrada_salida']
    for tabla in tablas_requeridas:
        assert tabla in tablas, f"Tabla {tabla} no encontrada"
    print(f"[OK] Tablas encontradas: {', '.join(tablas_requeridas)}")
    conn.close()
    
    # 4. Probar CRUD básico
    print("\n4. Probando operaciones CRUD básicas...")
    from models import (
        crear_solicitud, obtener_solicitudes_pendientes,
        aceptar_solicitud, obtener_usuarios_aceptados,
        registrar_entrada_salida, obtener_registros
    )
    
    # Crear solicitud
    user_id = crear_solicitud(
        "Usuario Prueba Fase 1",
        "999",
        "residente",
        "/static/fotos/test_fase1.jpg",
        None
    )
    print(f"[OK] Solicitud creada con ID: {user_id}")
    
    # Obtener pendientes
    pendientes = obtener_solicitudes_pendientes()
    assert len(pendientes) > 0, "No se encontraron solicitudes pendientes"
    print(f"[OK] Solicitudes pendientes: {len(pendientes)}")
    
    # Aceptar solicitud
    aceptar_solicitud(pendientes[0]['id'])
    aceptados = obtener_usuarios_aceptados()
    assert len(aceptados) > 0, "No se encontraron usuarios aceptados"
    print(f"[OK] Usuarios aceptados: {len(aceptados)}")
    
    # Registrar entrada/salida
    test_user = aceptados[0]
    registrar_entrada_salida(
        test_user['id'],
        test_user['tipo'],
        test_user['numero_casa'],
        'entrada',
        0.95
    )
    registros = obtener_registros(limite=10)
    assert len(registros) > 0, "No se encontraron registros"
    print(f"[OK] Registros de acceso: {len(registros)}")
    
    # 5. Verificar estructura de tablas
    print("\n5. Verificando estructura de tablas...")
    conn = sqlite3.connect(Config.DB_PATH)
    cursor = conn.cursor()
    
    # Verificar tabla usuarios
    cursor.execute("PRAGMA table_info(usuarios)")
    cols_usuarios = [c[1] for c in cursor.fetchall()]
    for col in ['id', 'nombre_completo', 'numero_casa', 'tipo', 'foto_path', 'fecha_registro', 'fecha_aceptacion', 'fecha_expiracion', 'estado', 'embedding']:
        assert col in cols_usuarios, f"Columna {col} no encontrada en usuarios"
    
    # Verificar tabla solicitudes
    cursor.execute("PRAGMA table_info(solicitudes)")
    cols_solicitudes = [c[1] for c in cursor.fetchall()]
    for col in ['id', 'usuario_id', 'nombre_completo', 'numero_casa', 'tipo', 'foto_path', 'estado', 'fecha_solicitud', 'revisado_por']:
        assert col in cols_solicitudes, f"Columna {col} no encontrada en solicitudes"
    
    # Verificar tabla registros_entrada_salida
    cursor.execute("PRAGMA table_info(registros_entrada_salida)")
    cols_registros = [c[1] for c in cursor.fetchall()]
    for col in ['id', 'usuario_id', 'tipo_usuario', 'numero_casa', 'fecha_hora', 'tipo_accion', 'confianza']:
        assert col in cols_registros, f"Columna {col} no encontrada en registros_entrada_salida"
    
    conn.close()
    print("[OK] Estructura de tablas verificada correctamente")
    
    print("\n=== Todas las pruebas de Fase 1 pasaron exitosamente ===")
    return True

if __name__ == '__main__':
    try:
        test_fase1()
    except Exception as e:
        print(f"\n[ERROR] Error en pruebas de Fase 1: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
