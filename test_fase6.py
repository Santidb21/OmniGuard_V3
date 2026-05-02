# -*- coding: utf-8 -*-
"""
test_fase6.py
Prueba automatica para verificar la Fase 6: Arquitectura Hibrida y Resiliencia.
"""

import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from models import (
    get_db_connection,
    obtener_registros_no_sincronizados,
    marcar_registros_sincronizados,
    registrar_entrada_salida,
    obtener_registros,
)

def test_pragma_wal():
    print("[TEST] Verificando modo WAL en SQLite...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    result = cursor.fetchone()
    conn.close()
    mode = result[0] if result else "unknown"
    assert mode.upper() == "WAL", "WAL no esta activo. Modo actual: {}".format(mode)
    print("[OK] Modo WAL activo: {}".format(mode))


def test_columna_sincronizado():
    print("[TEST] Verificando columna 'sincronizado' en registros_entrada_salida...")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(registros_entrada_salida);")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    assert 'sincronizado' in columns, "Columna 'sincronizado' no encontrada. Columnas: {}".format(columns)
    print("[OK] Columna 'sincronizado' presente. Columnas: {}".format(columns))


def test_insertar_y_sincronizar():
    print("[TEST] Probando insercion y sincronizacion de registros...")

    # Insertar un registro de prueba (sincronizado=0 por defecto)
    ok = registrar_entrada_salida(
        usuario_id="TEST01",
        tipo_usuario="residente",
        numero_casa="99",
        tipo_accion="entrada",
        confianza=0.95,
    )
    assert ok, "Fallo al insertar registro de prueba"
    print("[OK] Registro de prueba insertado (sincronizado=0)")

    # Obtener registros no sincronizados
    no_sync = obtener_registros_no_sincronizados(limite=50)
    ids_no_sync = [r["id"] for r in no_sync if r["usuario_id"] == "TEST01"]
    assert len(ids_no_sync) > 0, "No se encontro el registro recien insertado en no sincronizados"
    print("[OK] Registro encontrado en no sincronizados: IDs={}".format(ids_no_sync))

    # Marcar como sincronizado
    count = marcar_registros_sincronizados(ids_no_sync)
    assert count == len(ids_no_sync), "No se marcaron todos los registros. Esperado={}, Obtenido={}".format(len(ids_no_sync), count)
    print("[OK] Registros marcados como sincronizados: {}".format(count))

    # Verificar que ya no aparecen en no sincronizados
    no_sync_after = obtener_registros_no_sincronizados(limite=50)
    ids_after = [r["id"] for r in no_sync_after if r["id"] in ids_no_sync]
    assert len(ids_after) == 0, "Los registros aun aparecen como no sincronizados despues de marcarlos"
    print("[OK] Registro ya NO aparece en no sincronizados")

    # Limpiar registro de prueba
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros_entrada_salida WHERE usuario_id='TEST01'")
    conn.commit()
    conn.close()
    print("[OK] Registro de prueba eliminado")


def main():
    print("=" * 60)
    print("  TEST FASE 6: ARQUITECTURA HIBRIDA Y RESILIENCIA")
    print("=" * 60)
    print()

    try:
        test_pragma_wal()
        print()
        test_columna_sincronizado()
        print()
        test_insertar_y_sincronizar()
        print()
        print("=" * 60)
        print("  TODOS LOS TESTS PASARON (TODO EN VERDE)")
        print("=" * 60)
    except AssertionError as e:
        print()
        print("[FAIL] " + str(e))
        print("=" * 60)
        print("  TEST FALLIDO")
        print("=" * 60)
        sys.exit(1)
    except Exception as e:
        print()
        print("[ERROR] Excepcion inesperada: {}".format(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
