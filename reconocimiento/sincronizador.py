import os
import json
import time
import threading
import requests as http_requests
from datetime import datetime, timedelta

from config import Config
from models import (
    obtener_registros_no_sincronizados,
    marcar_registros_sincronizados,
    get_db_connection,
    ahora_cdmx,
    fecha_hora_cdmx,
)


def archivo_diario():
    return os.path.join(
        Config.RESPALDOS_PATH,
        "{}_resp.jsonl".format(datetime.now().strftime("%Y-%m-%d")),
    )


def exportar_respaldo_local(registros, archivo):
    try:
        escritos = 0
        with open(archivo, "a", encoding="utf-8") as f:
            for r in registros:
                linea = {
                    "id": r["id"],
                    "usuario_id": r["usuario_id"],
                    "tipo_usuario": r["tipo_usuario"],
                    "numero_casa": r["numero_casa"],
                    "fecha_hora": r["fecha_hora"],
                    "tipo_accion": r["tipo_accion"],
                    "confianza": r["confianza"],
                    "caseta_id": r["caseta_id"],
                    "sincronizado_en": fecha_hora_cdmx(),
                }
                f.write(json.dumps(linea, ensure_ascii=False) + "\n")
                escritos += 1
        if escritos:
            pass
        return escritos
    except Exception as e:
        print("[ERROR] Exportando respaldo local: {}".format(e))
        return 0


def push_a_cloud(registros):
    url = Config.SYNC_URL
    if not url:
        return False
    try:
        payload = {
            "dispositivo": "omniguard-{}".format(os.environ.get("COMPUTERNAME", "local")),
            "ultimo_sync": fecha_hora_cdmx(),
            "registros": [
                {
                    "id": r["id"],
                    "usuario_id": r["usuario_id"],
                    "tipo_usuario": r["tipo_usuario"],
                    "numero_casa": r["numero_casa"],
                    "fecha_hora": r["fecha_hora"],
                    "tipo_accion": r["tipo_accion"],
                    "confianza": r["confianza"],
                    "caseta_id": r["caseta_id"],
                }
                for r in registros
            ],
        }
        r = http_requests.post(
            url.rstrip("/") + "/push",
            json=payload,
            timeout=3,
            headers={"User-Agent": "OmniGuard-Sync/3.3"},
        )
        return r.status_code == 200
    except Exception:
        return False


def pull_de_cloud():
    url = Config.SYNC_URL
    if not url:
        return []
    try:
        r = http_requests.get(
            url.rstrip("/") + "/pull",
            params={"dispositivo": os.environ.get("COMPUTERNAME", "local")},
            timeout=3,
            headers={"User-Agent": "OmniGuard-Sync/3.3"},
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("registros", [])
        return []
    except Exception:
        return []


def aplicar_cambios_cloud(registros_remotos):
    if not registros_remotos:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for reg in registros_remotos:
            rid = reg.get("id")
            if not rid:
                continue
            cur.execute(
                "SELECT id FROM registros_entrada_salida WHERE id = ?", (rid,)
            )
            if cur.fetchone() is None:
                cur.execute(
                    """INSERT OR IGNORE INTO registros_entrada_salida
                       (id, usuario_id, tipo_usuario, numero_casa, fecha_hora, tipo_accion, confianza, sincronizado, caseta_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (
                        rid,
                        reg.get("usuario_id", ""),
                        reg.get("tipo_usuario", ""),
                        reg.get("numero_casa", ""),
                        reg.get("fecha_hora", fecha_hora_cdmx()),
                        reg.get("tipo_accion", ""),
                        reg.get("confianza", 0.0),
                        reg.get("caseta_id"),
                    ),
                )
        conn.commit()
        conn.close()
    except Exception as e:
        print("[ERROR] Aplicando cambios cloud: {}".format(e))


def limpiar_respaldos_viejos():
    try:
        ahora = time.time()
        limite = Config.RESPALDOS_DIAS * 86400
        for fname in os.listdir(Config.RESPALDOS_PATH):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(Config.RESPALDOS_PATH, fname)
            mtime = os.path.getmtime(fpath)
            if ahora - mtime > limite:
                os.remove(fpath)
    except Exception as e:
        print("[ERROR] Limpiando respaldos viejos: {}".format(e))


def bucle_sincronizacion():
    os.makedirs(Config.RESPALDOS_PATH, exist_ok=True)
    contador = 0
    while True:
        try:
            registros = obtener_registros_no_sincronizados(limite=100)
            if registros:
                archivo = archivo_diario()
                exportar_respaldo_local(registros, archivo)
                push_a_cloud(registros)
                ids = [r["id"] for r in registros]
                marcar_registros_sincronizados(ids)
                remotos = pull_de_cloud()
                if remotos:
                    aplicar_cambios_cloud(remotos)
            contador += 1
            if contador >= 120:
                limpiar_respaldos_viejos()
                contador = 0
        except Exception as e:
            print("[ERROR] Ciclo de sincronizacion: {}".format(e))
        time.sleep(Config.SYNC_INTERVAL)


def iniciar_sincronizador():
    hilo = threading.Thread(target=bucle_sincronizacion, daemon=True, name="SyncThread")
    hilo.start()
    print("[INFO] Sincronizador continuo iniciado (intervalo={}s, respaldos={})".format(
        Config.SYNC_INTERVAL, Config.RESPALDOS_PATH))
    return hilo
