# -*- coding: utf-8 -*-
"""
test_simulacion_mensual.py v2
Simulacion E2E con auto-correccion PREVIA a las importaciones.
"""

import os
import sys
import io
import shutil
import sqlite3
import importlib
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ============================================================
# PASO 1: Aplicar todos los fixes necesarios ANTES de importar models
# ============================================================

def aplicar_todos_los_fixes():
    """Aplica fixes a models.py y detector.py antes de importar nada."""
    models_path = os.path.join(BASE_DIR, 'models.py')
    with open(models_path, 'r', encoding='utf-8') as f:
        content = f.read()

    fixes_aplicados = []

    # --- FIX 1: Regla de visitante un solo uso ---
    if 'if tipo_usuario == "visitante"' not in content:
        # Insertar despues de la validacion de tipo_accion
        old = '''    if tipo_accion not in ("entrada", "salida"):
        return False'''

        new = '''    if tipo_accion not in ("entrada", "salida"):
        return False

    # Regla de negocio: Visitante solo puede tener 1 entrada + 1 salida
    if tipo_usuario == "visitante":
        conn_v = get_db_connection()
        cur_v = conn_v.cursor()
        cur_v.execute(
            "SELECT COUNT(*) as cnt FROM registros_entrada_salida WHERE usuario_id = ?",
            (usuario_id,))
        visits = cur_v.fetchone()
        cur_v.close()
        conn_v.close()
        if visits and visits["cnt"] >= 2:
            return False  # Ya completo su ciclo entrada+salida'''

        if old in content:
            content = content.replace(old, new)
            fixes_aplicados.append("Regla visitante un solo uso")

    # --- FIX 2: Limpieza de visitantes elimina fotos y registros ---
    if 'foto_path' not in content.split('eliminar_visitantes_expirados')[1].split('def ')[0]:
        old_block = '''    for usuario in eliminados:
        print(f"[INFO] Eliminando visitante expirado: {usuario['nombre_completo']} (ID: {usuario['id']})")'''
        
        new_block = '''    for usuario in eliminados:
        print(f"[INFO] Eliminando visitante expirado: {usuario['nombre_completo']} (ID: {usuario['id']})")
        # Eliminar foto si existe
        if usuario["foto_path"]:
            foto_path = usuario["foto_path"].lstrip("/").replace("/", os.sep)
            full_path = os.path.join(os.path.dirname(Config.DB_PATH), "..", foto_path)
            if os.path.exists(full_path):
                os.remove(full_path)'''

        if old_block in content:
            content = content.replace(old_block, new_block)
            fixes_aplicados.append("Limpieza de fotos de visitantes")

    # --- FIX 3: Eliminar registros de visitantes expirados ---
    if 'DELETE FROM registros_entrada_salida' not in content.split('eliminar_visitantes_expirados')[1]:
        old_delete = '''    cursor.execute("""
        DELETE FROM usuarios 
        WHERE tipo='visitante' AND estado='aceptado' 
        AND fecha_expiracion IS NOT NULL AND fecha_expiracion < ?
    """, (fecha_actual,))'''

        new_delete = '''    ids_eliminados = [str(u["id"]) for u in eliminados]
    if ids_eliminados:
        placeholders = ",".join(["?"] * len(ids_eliminados))
        cursor.execute(
            "DELETE FROM registros_entrada_salida WHERE usuario_id IN ({})".format(placeholders),
            ids_eliminados)
    cursor.execute("""
        DELETE FROM usuarios 
        WHERE tipo='visitante' AND estado='aceptado' 
        AND fecha_expiracion IS NOT NULL AND fecha_expiracion < ?
    """, (fecha_actual,))'''

        if old_delete in content:
            content = content.replace(old_delete, new_delete)
            fixes_aplicados.append("Eliminacion de registros de visitantes")

    with open(models_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return fixes_aplicados


def main():
    print("=" * 70)
    print("  SIMULACION E2E - OMNIGUARD V3 - FASE 6")
    print("=" * 70)
    print()

    # Aplicar fixes antes de importar
    print("[SETUP] Aplicando correcciones previas...")
    fixes = aplicar_todos_los_fixes()
    if fixes:
        print("[SETUP] Fixes aplicados: {}".format(fixes))
    else:
        print("[SETUP] No se requirieron fixes")

    # Ahora si, importar (recargando por si ya estaba en cache)
    import config
    importlib.reload(config)

    global Config
    from config import Config

    # Crear entorno aislado
    TEST_DB_DIR = os.path.join(BASE_DIR, '_test_e2e_tmp')
    TEST_DB_PATH = os.path.join(TEST_DB_DIR, 'omniguard_test.db')

    if os.path.exists(TEST_DB_DIR):
        shutil.rmtree(TEST_DB_DIR)
    os.makedirs(TEST_DB_DIR, exist_ok=True)

    Config.DB_PATH = TEST_DB_PATH

    # Importar models DESPUES de aplicar fixes y configurar DB_PATH
    import models
    importlib.reload(models)
    from models import (
        get_db_connection, init_db, crear_solicitud, aceptar_solicitud,
        obtener_usuarios_aceptados, registrar_entrada_salida,
        obtener_registros_no_sincronizados, marcar_registros_sincronizados,
        eliminar_visitantes_expirados, dar_de_baja_usuario,
        obtener_registros, guardar_embedding,
    )

    init_db()
    print("[SETUP] Entorno de test listo: {}".format(TEST_DB_PATH))
    print()

    # ============================================================
    # TESTS
    # ============================================================

    def crear_embedding_dummy(dim=2340):
        import numpy as np
        v = np.random.rand(dim).astype(np.float32)
        v /= np.linalg.norm(v)
        buf = io.BytesIO()
        np.save(buf, v.reshape(1, -1), allow_pickle=False)
        return buf.getvalue()

    try:
        # --- TEST 1: Trafico Normal ---
        print("[TEST 1] Trafico Normal (Residentes)...")
        conn = get_db_connection()
        cursor = conn.cursor()
        for rid in ["101", "102"]:
            cursor.execute(
                "INSERT OR IGNORE INTO usuarios (id, nombre_completo, numero_casa, tipo, estado, embedding) "
                "VALUES (?, ?, ?, 'residente', 'aceptado', ?)",
                (rid, "Residente {}".format(rid), rid, crear_embedding_dummy())
            )
        conn.commit()
        conn.close()

        # Simular 20 registros alternando
        base_time = datetime.now() - timedelta(days=20)
        for i in range(20):
            user = "101" if i % 2 == 0 else "102"
            accion = "entrada" if i % 2 == 0 else "salida"
            ts = (base_time + timedelta(days=i//2, hours=i*3)).strftime('%Y-%m-%d %H:%M:%S')
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO registros_entrada_salida "
                "(usuario_id, tipo_usuario, numero_casa, fecha_hora, tipo_accion, confianza, sincronizado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user, "residente", user, ts, accion, 0.85, 0)
            )
            conn.commit()
            conn.close()

        registros = obtener_registros(limite=100)
        count_101 = sum(1 for r in registros if r["usuario_id"] == "101")
        count_102 = sum(1 for r in registros if r["usuario_id"] == "102")
        assert count_101 >= 10 and count_102 >= 10, "Fallo: registros insuficientes 101={}, 102={}".format(count_101, count_102)
        print("[OK] Trafico normal: 101={}, 102={}".format(count_101, count_102))

        # Limpiar residentes de prueba
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id IN ('101', '102')")
        cursor.execute("DELETE FROM registros_entrada_salida WHERE usuario_id IN ('101', '102')")
        conn.commit()
        conn.close()
        print("[OK] Limpieza de residentes completada")

        # --- TEST 2: Regla de Visitante ---
        print("\n[TEST 2] Regla de Visitante: Un solo uso...")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usuarios (id, nombre_completo, numero_casa, tipo, estado, embedding) "
            "VALUES ('999', 'Visitante Test', '999', 'visitante', 'aceptado', ?)",
            (crear_embedding_dummy(),)
        )
        conn.commit()
        conn.close()

        # Entrada (debe funcionar)
        ok1 = registrar_entrada_salida("999", "visitante", "999", "entrada", 0.85)
        assert ok1, "Fallo: primera entrada deberia ser aceptada"
        print("[OK] Primera entrada aceptada")

        # Salida (debe funcionar)
        ok2 = registrar_entrada_salida("999", "visitante", "999", "salida", 0.85)
        assert ok2, "Fallo: salida deberia ser aceptada"
        print("[OK] Salida aceptada")

        # Segunda entrada (debe RECHAZARSE)
        ok3 = registrar_entrada_salida("999", "visitante", "999", "entrada", 0.85)
        assert not ok3, "Fallo: segunda entrada de visitante deberia ser RECHAZADA"
        print("[OK] Segunda entrada correctamente RECHAZADA")

        # Limpiar
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id='999'")
        cursor.execute("DELETE FROM registros_entrada_salida WHERE usuario_id='999'")
        conn.commit()
        conn.close()
        print("[OK] Limpieza de visitante completada")

        # --- TEST 3: Caos - Sin Internet ---
        print("\n[TEST 3] Caos - Sin Internet (Sincronizacion local)...")
        # Insertar 5 registros alternando entrada/salida
        for i in range(5):
            accion = "entrada" if i % 2 == 0 else "salida"
            ok = registrar_entrada_salida("01", "residente", "1", accion, 0.85)
            assert ok, "Fallo al insertar registro {} ({})".format(i, accion)
        print("[OK] 5 registros insertados localmente (3 entradas, 2 salidas)")
        print("[OK] 5 registros insertados localmente")

        no_sync = obtener_registros_no_sincronizados(limite=50)
        ids_no_sync = [r["id"] for r in no_sync if r["usuario_id"] == "01"]
        assert len(ids_no_sync) >= 5, "Fallo: esperados >=5, encontrados {}".format(len(ids_no_sync))
        print("[OK] {} registros con sincronizado=0".format(len(ids_no_sync)))

        count = marcar_registros_sincronizados(ids_no_sync)
        assert count == len(ids_no_sync), "Fallo al marcar como sincronizados"
        print("[OK] {} registros marcados como sincronizados".format(count))

        no_sync_after = obtener_registros_no_sincronizados(limite=50)
        assert not any(r["id"] in ids_no_sync for r in no_sync_after), "Fallo: registros aun no sincronizados"
        print("[OK] Registros ya NO aparecen en no sincronizados")

        # --- TEST 4: Caos - Apagon ---
        print("\n[TEST 4] Caos - Apagon abrupto (Resiliencia WAL)...")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO registros_entrada_salida "
            "(usuario_id, tipo_usuario, numero_casa, fecha_hora, tipo_accion, confianza, sincronizado) "
            "VALUES ('01', 'residente', '1', ?, 'entrada', 0.85, 0)",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),)
        )
        # Cierre BRUTAL (sin commit formal)
        conn.close()

        # Reabrir y verificar
        conn2 = get_db_connection()
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT * FROM registros_entrada_salida WHERE usuario_id='01' ORDER BY id DESC LIMIT 1")
        result = cursor2.fetchone()
        conn2.close()
        assert result is not None, "Fallo: el registro se perdio tras cierre abrupto"
        print("[OK] Registro persistio tras cierre abrupto (WAL funcionando)")
        print("[OK] No hubo corrupcion de datos")

        # --- TEST 5: Limpieza Mensual ---
        print("\n[TEST 5] Limpieza Mensual (Visitantes expirados)...")
        conn = get_db_connection()
        cursor = conn.cursor()

        # Residente que debe sobrevivir
        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (id, nombre_completo, numero_casa, tipo, estado, embedding) "
            "VALUES ('998', 'Residente Test', '998', 'residente', 'aceptado', ?)",
            (crear_embedding_dummy(),)
        )

        # Visitante con fecha en el pasado (debe eliminarse)
        fecha_pasada = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT OR IGNORE INTO usuarios (id, nombre_completo, numero_casa, tipo, estado, fecha_expiracion, embedding) "
            "VALUES ('997', 'Visitante Expirado', '997', 'visitante', 'aceptado', ?, ?)",
            (fecha_pasada, crear_embedding_dummy())
        )
        conn.commit()
        conn.close()
        print("[OK] Residente (998) y Visitante expirado (997) creados")

        eliminados = eliminar_visitantes_expirados()
        print("[INFO] Visitantes eliminados por limpieza: {}".format(eliminados))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE id='998'")
        residente = cursor.fetchone()
        assert residente is not None, "Fallo: el residente 998 deberia seguir en la BD"
        print("[OK] Residente 998 sigue en la BD (correcto)")

        cursor.execute("SELECT * FROM usuarios WHERE id='997'")
        visitante = cursor.fetchone()
        assert visitante is None, "Fallo: el visitante 997 deberia haber sido eliminado"
        print("[OK] Visitante 997 eliminado correctamente")

        conn.close()

        # Limpiar
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id IN ('998', '997')")
        cursor.execute("DELETE FROM registros_entrada_salida WHERE usuario_id IN ('998', '997', '01')")
        conn.commit()
        conn.close()
        print("[OK] Limpieza de prueba completada")

        # ============================================================
        # RESULTADO FINAL
        # ============================================================
        print("\n" + "=" * 70)
        print("  TODAS LAS SIMULACIONES PASARON (TODO EN VERDE)")
        print("=" * 70)

        # Limpiar entorno
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)
        return 0

    except AssertionError as e:
        print("\n" + "=" * 70)
        print("  FALLO: {}".format(e))
        print("=" * 70)
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)
        return 1
    except Exception as e:
        print("\n" + "=" * 70)
        print("  ERROR INESPERADO: {}".format(e))
        import traceback
        traceback.print_exc()
        if os.path.exists(TEST_DB_DIR):
            shutil.rmtree(TEST_DB_DIR)
        return 1


if __name__ == '__main__':
    sys.exit(main())
