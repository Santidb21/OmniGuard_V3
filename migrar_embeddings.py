# -*- coding: utf-8 -*-
"""
migrar_embeddings.py
Re-extrae embeddings de fotos existentes usando el nuevo pipeline con
normalizacion a 150x150 y actualiza la BD SQLite.
"""

import os
import sys
import io
import glob as globmod

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BASE_DIR, Config
from models import obtener_usuarios_aceptados, obtener_embedding, guardar_embedding, get_db_connection

# Constantes del nuevo pipeline (espejo de detector.py)
FACE_SIZE_ESTANDAR = (150, 150)

hog = cv2.HOGDescriptor(
    _winSize=(64, 64),
    _blockSize=(16, 16),
    _blockStride=(8, 8),
    _cellSize=(8, 8),
    _nbins=9,
)

cascades = []
for nombre in ["haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml"]:
    path = cv2.data.haarcascades + nombre
    cascade = cv2.CascadeClassifier(path)
    if not cascade.empty():
        cascades.append(cascade)


def preprocesar_gris(imagen):
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if len(imagen.shape) == 3 else imagen
    gris = cv2.GaussianBlur(gris, (3, 3), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gris)


def detectar_rostros(imagen):
    if not cascades:
        return []
    gris = preprocesar_gris(imagen)
    alto, ancho = gris.shape[:2]
    min_lado = max(30, int(min(ancho, alto) * 0.08))
    candidatos = []
    for cascade in cascades:
        rostros = cascade.detectMultiScale(
            gris, scaleFactor=1.1, minNeighbors=4, minSize=(min_lado, min_lado))
        for x, y, w, h in rostros:
            aspecto = w / float(h)
            if 0.60 <= aspecto <= 1.50:
                candidatos.append((int(x), int(y), int(x + w), int(y + h)))
    # filtrar por IoU
    if not candidatos:
        return []
    candidatos.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
    finales = []
    for caja in candidatos:
        if all(iou(caja, e) < 0.35 for e in finales):
            finales.append(caja)
    return finales


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    return inter / float((ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter + 1e-6)


def normalizar_caja(imagen, caja):
    x1, y1, x2, y2 = caja
    alto, ancho = imagen.shape[:2]
    w, h = x2 - x1, y2 - y1
    mx, my = int(w * 0.12), int(h * 0.16)
    return max(0, x1 - mx), max(0, y1 - my), min(ancho, x2 + mx), min(alto, y2 + my)


def histograma_lbp(gris):
    centro = gris[1:-1, 1:-1]
    lbp = np.zeros_like(centro, dtype=np.uint8)
    vecinos = [
        gris[:-2, :-2], gris[:-2, 1:-1], gris[:-2, 2:],
        gris[1:-1, 2:], gris[2:, 2:], gris[2:, 1:-1],
        gris[2:, :-2], gris[1:-1, :-2],
    ]
    for bit, vecino in enumerate(vecinos):
        lbp |= ((vecino >= centro) << bit).astype(np.uint8)
    histogramas = []
    for fila in np.array_split(lbp, 4, axis=0):
        for celda in np.array_split(fila, 4, axis=1):
            hist, _ = np.histogram(celda, bins=32, range=(0, 256))
            hist = hist.astype(np.float32)
            hist /= hist.sum() + 1e-6
            histogramas.append(hist)
    return np.concatenate(histogramas).astype(np.float32)


def proyecciones(gris):
    normalizado = gris.astype(np.float32) / 255.0
    horizontal = cv2.resize(normalizado.mean(axis=1).reshape(-1, 1), (1, 32)).flatten()
    vertical = cv2.resize(normalizado.mean(axis=0).reshape(1, -1), (32, 1)).flatten()
    return np.concatenate([horizontal, vertical]).astype(np.float32)


def extraer_embedding_nuevo(imagen, caja):
    x1, y1, x2, y2 = normalizar_caja(imagen, caja)
    rostro = imagen[y1:y2, x1:x2]
    if rostro.size == 0:
        return None
    rostro_norm = cv2.resize(rostro, FACE_SIZE_ESTANDAR, interpolation=cv2.INTER_AREA)
    gris = preprocesar_gris(rostro_norm)
    gris_96 = cv2.resize(gris, (96, 96), interpolation=cv2.INTER_AREA)
    gris_64 = cv2.resize(gris, (64, 64), interpolation=cv2.INTER_AREA)
    hog_feat = hog.compute(gris_64).flatten().astype(np.float32)
    lbp_hist = histograma_lbp(gris_96)
    proy = proyecciones(gris_96)
    embedding = np.concatenate([hog_feat, lbp_hist, proy]).astype(np.float32)
    norm = np.linalg.norm(embedding)
    if norm <= 1e-6:
        return None
    return embedding / norm


def serializar_embeddings(embeddings):
    validos = [e.astype(np.float32) for e in embeddings if e is not None and e.size > 0]
    if not validos:
        return None
    arr = np.vstack(validos).astype(np.float32)
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    return buf.getvalue()


def main():
    print("=" * 60)
    print("  MIGRACION DE EMBEDDINGS - NUEVO PIPELINE 150x150")
    print("=" * 60)
    print()

    feature_dim = None
    # calcular dimension con imagen dummy
    dummy = np.zeros((96, 96, 3), dtype=np.uint8)
    dummy_gray = cv2.cvtColor(dummy, cv2.COLOR_BGR2GRAY)
    dummy_gray = cv2.GaussianBlur(dummy_gray, (3, 3), 0)
    dummy_gray = cv2.resize(dummy_gray, FACE_SIZE_ESTANDAR, interpolation=cv2.INTER_AREA)
    gris_proc = preprocesar_gris(dummy)
    gris_proc_norm = cv2.resize(gris_proc, FACE_SIZE_ESTANDAR, interpolation=cv2.INTER_AREA)
    gris_64 = cv2.resize(gris_proc_norm, (64, 64), interpolation=cv2.INTER_AREA)
    feature_dim = hog.compute(gris_64).flatten().size + 512 + 64
    print("[INFO] Nueva dimension del embedding: {}".format(feature_dim))
    print()

    usuarios = obtener_usuarios_aceptados()
    if not usuarios:
        print("[WARN] No hay usuarios aceptados")
        return

    fotos_dir = str(Config.FOTOS_PATH)
    migrados = 0
    fallidos = 0

    for usuario in usuarios:
        uid = usuario["id"]
        nombre = usuario["nombre_completo"]
        foto_path = usuario["foto_path"] or ""
        print("[INFO] Procesando usuario: '{}' (id={})".format(nombre, uid))

        # Buscar todas las fotos asociadas a este usuario en la BD
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT foto_path FROM usuarios WHERE id=? OR (nombre_completo=? AND estado='aceptado')",
            (uid, nombre))
        fotos_asociadas = set()
        for row in cursor.fetchall():
            fp = row[0]
            if fp:
                fotos_asociadas.add(fp)
        conn.close()

        # Buscar archivos fisicos en fotos_dir que coincidan
        archivos_usuario = []
        for fname in sorted(os.listdir(fotos_dir)):
            if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            ruta_rel = "/static/fotos/{}".format(fname)
            for fp in fotos_asociadas:
                if fname in fp or fp in ruta_rel:
                    archivos_usuario.append(os.path.join(fotos_dir, fname))
                    break

        # Tambien buscar por patron de fecha en nombre (formato similar)
        if not archivos_usuario:
            # Intentar encontrar por prefijo de fecha
            for fname in sorted(os.listdir(fotos_dir)):
                if not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                archivos_usuario.append(os.path.join(fotos_dir, fname))

        if not archivos_usuario:
            print("  [WARN] No se encontraron fotos fisicas para '{}'".format(nombre))
            fallidos += 1
            continue

        # Si hay mas fotos que las del usuario, priorizar las que estan en BD
        fotos_a_procesar = archivos_usuario
        print("  [INFO] {} fotos encontradas".format(len(fotos_a_procesar)))

        nuevos_embeddings = []
        for fpath in fotos_a_procesar:
            imagen = cv2.imread(fpath)
            if imagen is None:
                print("  [WARN] No se pudo leer: {}".format(fpath))
                continue
            rostros = detectar_rostros(imagen)
            if not rostros:
                print("  [WARN] Sin rostro detectado en: {}".format(os.path.basename(fpath)))
                continue
            emb = extraer_embedding_nuevo(imagen, rostros[0])
            if emb is not None:
                nuevos_embeddings.append(emb)
                print("  [OK] Embedding extraido de {} (dim={}, norma={:.4f})".format(
                    os.path.basename(fpath), emb.size, np.linalg.norm(emb)))
            else:
                print("  [WARN] Embedding nulo para: {}".format(os.path.basename(fpath)))

        if nuevos_embeddings:
            serializado = serializar_embeddings(nuevos_embeddings)
            guardar_embedding(uid, serializado)
            print("  [INFO] BD actualizada con {} nuevo(s) embedding(s) para '{}'".format(
                len(nuevos_embeddings), nombre))
            migrados += 1
        else:
            print("  [WARN] No se pudo extraer ningun embedding para '{}'".format(nombre))
            fallidos += 1
        print()

    print("=" * 60)
    print("  MIGRACION COMPLETADA")
    print("  Usuarios migrados: {}".format(migrados))
    print("  Usuarios fallidos: {}".format(fallidos))
    print("=" * 60)


if __name__ == '__main__':
    main()
