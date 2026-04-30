# -*- coding: utf-8 -*-
"""
auditoria_reconocimiento.py
Script de diagnostico para evaluar la compatibilidad de embeddings OpenCV vs BD.
NO modifica ningun archivo del sistema. Solo lectura y diagnostico.
"""

import os
import sys
import io
import platform
import datetime
import subprocess

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BASE_DIR, Config
from models import obtener_usuarios_aceptados, obtener_embedding, get_db_connection

# ============================================================
# 1. INFO DE HARDWARE Y VERSIONES
# ============================================================

def recopilar_info_sistema():
    info = {}
    info['sistema'] = platform.system()
    info['release'] = platform.release()
    info['maquina'] = platform.machine()
    info['procesador'] = platform.processor()
    info['python_version'] = platform.python_version()
    info['python_impl'] = platform.python_implementation()

    try:
        info['cv2_version'] = cv2.__version__
    except:
        info['cv2_version'] = 'no disponible'

    info['numpy_version'] = np.__version__

    try:
        import sqlite3
        info['sqlite_version'] = sqlite3.sqlite_version
    except:
        info['sqlite_version'] = 'no disponible'

    try:
        info['opencv_backends'] = [
            'DSHOW' if hasattr(cv2, 'CAP_DSHOW') else 'N/A',
            'MSMF' if hasattr(cv2, 'CAP_MSMF') else 'N/A',
        ]
    except:
        info['opencv_backends'] = []

    return info

# ============================================================
# 2. REPLICAR EL PIPELINE DE EXTRACCION DE EMBEDDINGS
# ============================================================

class PipelineExtractor:
    """Replica EXACTAMENTE la logica de DetectorRostro.extraer_embedding_opencv."""

    def __init__(self):
        self.hog = cv2.HOGDescriptor(
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
        self.face_cascades = cascades

        dummy = np.zeros((96, 96, 3), dtype=np.uint8)
        self.feature_dim = len(self._extraer(dummy, (0, 0, 96, 96)))

    def preprocesar_gris(self, imagen):
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if len(imagen.shape) == 3 else imagen
        gris = cv2.GaussianBlur(gris, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gris)

    def detectar_rostros(self, imagen):
        if not self.face_cascades:
            return []
        gris = self.preprocesar_gris(imagen)
        alto, ancho = gris.shape[:2]
        min_lado = max(56, int(min(ancho, alto) * 0.14))
        candidatos = []
        for cascade in self.face_cascades:
            rostros = cascade.detectMultiScale(
                gris, scaleFactor=1.05, minNeighbors=6, minSize=(min_lado, min_lado))
            for x, y, w, h in rostros:
                aspecto = w / float(h)
                area = w * h
                if 0.70 <= aspecto <= 1.35 and area >= min_lado * min_lado:
                    candidatos.append((int(x), int(y), int(x + w), int(y + h)))
        return candidatos

    def normalizar_caja(self, imagen, caja):
        x1, y1, x2, y2 = caja
        alto, ancho = imagen.shape[:2]
        w, h = x2 - x1, y2 - y1
        mx, my = int(w * 0.12), int(h * 0.16)
        return max(0, x1 - mx), max(0, y1 - my), min(ancho, x2 + mx), min(alto, y2 + my)

    def histograma_lbp(self, gris):
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

    def proyecciones(self, gris):
        normalizado = gris.astype(np.float32) / 255.0
        horizontal = cv2.resize(normalizado.mean(axis=1).reshape(-1, 1), (1, 32)).flatten()
        vertical = cv2.resize(normalizado.mean(axis=0).reshape(1, -1), (32, 1)).flatten()
        return np.concatenate([horizontal, vertical]).astype(np.float32)

    def _extraer(self, imagen, caja):
        try:
            x1, y1, x2, y2 = self.normalizar_caja(imagen, caja)
            rostro = imagen[y1:y2, x1:x2]
            if rostro.size == 0:
                return None
            gris = self.preprocesar_gris(rostro)
            gris_96 = cv2.resize(gris, (96, 96), interpolation=cv2.INTER_AREA)
            gris_64 = cv2.resize(gris, (64, 64), interpolation=cv2.INTER_AREA)
            hog = self.hog.compute(gris_64).flatten().astype(np.float32)
            lbp_hist = self.histograma_lbp(gris_96)
            proy = self.proyecciones(gris_96)
            embedding = np.concatenate([hog, lbp_hist, proy]).astype(np.float32)
            norm = np.linalg.norm(embedding)
            if norm <= 1e-6:
                return None
            return embedding / norm
        except Exception as e:
            print("[ERROR] _extraer: {}".format(e))
            return None

    def extraer_de_imagen(self, image_path):
        imagen = cv2.imread(image_path)
        if imagen is None:
            return None, None
        rostros = self.detectar_rostros(imagen)
        if not rostros:
            return imagen, None
        embedding = self._extraer(imagen, rostros[0])
        return imagen, embedding, rostros[0]


# ============================================================
# 3. DESERIALIZAR EMBEDDINGS DE LA BD
# ============================================================

def deserializar_embedding(blob, feature_dim):
    if not blob:
        return []
    data = bytes(blob)
    try:
        if data.startswith(b"\x93NUMPY"):
            arr = np.load(io.BytesIO(data), allow_pickle=False)
        else:
            arr = np.frombuffer(data, dtype=np.float32)
            if arr.size == 0 or arr.size % max(1, feature_dim or arr.size) != 0:
                arr = np.frombuffer(data, dtype=np.float64).astype(np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return [fila.astype(np.float32) for fila in arr if fila.size > 0]
    except Exception as e:
        print("[ERROR] deserializar: {}".format(e))
        return []


# ============================================================
# 4. FUNCIONES DE ANALISIS
# ============================================================

def cos_sim(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def estadisticas_vector(v, nombre):
    return {
        'nombre': nombre,
        'shape': v.shape,
        'dimension': v.size,
        'dtype': str(v.dtype),
        'min': float(np.min(v)),
        'max': float(np.max(v)),
        'mean': float(np.mean(v)),
        'std': float(np.std(v)),
        'norm': float(np.linalg.norm(v)),
        'no_ceros': int(np.count_nonzero(v)),
        'ceros': int(v.size - np.count_nonzero(v)),
    }


def similitud_distribucion(v1, v2):
    """Analiza la similitud componente a componente."""
    diffs = np.abs(v1 - v2)
    return {
        'cosine_similarity': cos_sim(v1, v2),
        'dot_product': float(np.dot(v1, v2)),
        'euclidean_distance': float(np.linalg.norm(v1 - v2)),
        'mean_abs_diff': float(np.mean(diffs)),
        'max_abs_diff': float(np.max(diffs)),
        'min_abs_diff': float(np.min(diffs)),
        'std_abs_diff': float(np.std(diffs)),
        'componentes_similares_gt_095': int(np.sum(diffs < 0.05)),
        'componentes_similares_gt_090': int(np.sum(diffs < 0.10)),
    }


# ============================================================
# 5. MAIN
# ============================================================

def main():
    print("=" * 70)
    print("  AUDITORIA DE RECONOCIMIENTO FACIAL - OMNIGUARD V3")
    print("=" * 70)
    print()

    # --- Sistema ---
    info = recopilar_info_sistema()
    print("[1] INFORMACION DEL SISTEMA")
    print("    OS: {} {} ({})".format(info['sistema'], info['release'], info['maquina']))
    print("    CPU: {}".format(info['procesador']))
    print("    Python: {} ({})".format(info['python_version'], info['python_impl']))
    print("    OpenCV: {}".format(info['cv2_version']))
    print("    NumPy: {}".format(info['numpy_version']))
    print("    SQLite: {}".format(info['sqlite_version']))
    print()

    # --- Pipeline ---
    print("[2] INICIALIZANDO PIPELINE DE EXTRACCION")
    extractor = PipelineExtractor()
    feature_dim = extractor.feature_dim
    print("    feature_dim del pipeline OpenCV: {}".format(feature_dim))
    print("    Cascadas cargadas: {}".format(len(extractor.face_cascades)))
    print()

    # --- Fotos ---
    fotos_dir = Config.FOTOS_PATH
    fotos = sorted([f for f in os.listdir(fotos_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    if not fotos:
        print("[ERROR] No hay fotos en {}".format(fotos_dir))
        return
    primera_foto = fotos[0]
    foto_path = os.path.join(fotos_dir, primera_foto)
    print("[3] PRIMERA FOTO DE REFERENCIA")
    print("    Archivo: {}".format(primera_foto))
    print("    Ruta: {}".format(foto_path))
    print("    Tamano: {} bytes".format(os.path.getsize(foto_path)))
    print()

    # --- Extraer embedding de la foto ---
    print("[4] EXTRAYENDO EMBEDDING DE LA FOTO")
    imagen, embedding_foto, caja = extractor.extraer_de_imagen(foto_path)
    if embedding_foto is None:
        print("    [ERROR] No se detecto rostro en la foto!")
        if imagen is not None:
            print("    Dimensiones de imagen: {}x{}".format(imagen.shape[1], imagen.shape[0]))
            rostros = extractor.detectar_rostros(imagen)
            print("    Rostros detectados por cascadas: {}".format(len(rostros)))
        return
    print("    Rostro detectado en caja: {}".format(caja))
    stats_foto = estadisticas_vector(embedding_foto, "embedding_foto")
    print("    Dimension: {}".format(stats_foto['dimension']))
    print("    Norma: {:.6f}".format(stats_foto['norm']))
    print("    Rango: [{:.6f}, {:.6f}]".format(stats_foto['min'], stats_foto['max']))
    print("    Media: {:.6f}".format(stats_foto['mean']))
    print("    DesvStd: {:.6f}".format(stats_foto['std']))
    print("    Componentes no-cero: {} / {}".format(stats_foto['no_ceros'], stats_foto['dimension']))
    print("    Componentes cero: {}".format(stats_foto['ceros']))
    print()

    # --- Usuarios en BD ---
    print("[5] USUARIOS EN BASE DE DATOS")
    usuarios = obtener_usuarios_aceptados()
    if not usuarios:
        print("    No hay usuarios aceptados en la BD")
        return

    foto_rel = "/static/fotos/{}".format(primera_foto)
    usuario_asociado = None
    for u in usuarios:
        uid = u["id"]
        nombre = u["nombre_completo"]
        foto_db = u["foto_path"] or ""
        tipo = u["tipo"]

        # Verificar si esta foto corresponde a este usuario
        if primera_foto in foto_db or foto_rel in foto_db:
            usuario_asociado = u

        # Leer embedding de BD
        blob = obtener_embedding(uid)
        if blob is None:
            print("    Usuario '{}' (id={}): SIN embedding en BD".format(nombre, uid))
            continue

        embeddings_bd = deserializar_embedding(blob, feature_dim)
        print("    Usuario '{}' (id={}, tipo={})".format(nombre, uid, tipo))
        print("      foto_path en BD: {}".format(foto_db))
        print("      Embeddings deserializados: {}".format(len(embeddings_bd)))

        if embeddings_bd:
            bd = embeddings_bd[0]
            stats_bd = estadisticas_vector(bd, "embedding_BD")
            print("      Dimension BD: {}".format(stats_bd['dimension']))
            print("      Norma BD: {:.6f}".format(stats_bd['norm']))
            print("      Rango BD: [{:.6f}, {:.6f}]".format(stats_bd['min'], stats_bd['max']))
            print("      Media BD: {:.6f}".format(stats_bd['mean']))
            print("      DesvStd BD: {:.6f}".format(stats_bd['std']))
            print("      Componentes no-cero BD: {} / {}".format(stats_bd['no_ceros'], stats_bd['dimension']))

            if len(embeddings_bd) > 1:
                print("      Variabilidad entre embeddings del mismo usuario:")
                for i in range(1, len(embeddings_bd)):
                    sim = cos_sim(embeddings_bd[0], embeddings_bd[i])
                    print("        muestra_0 vs muestra_{}: cosine={:.4f}".format(i, sim))
        print()

    # --- Comparacion cruzada ---
    print("[6] ANALISIS DE COMPATIBILIDAD DE DIMENSIONES")
    print("    feature_dim pipeline actual: {}".format(feature_dim))

    todos_compatibles = True
    for u in usuarios:
        blob = obtener_embedding(u["id"])
        if blob is None:
            continue
        embeddings_bd = deserializar_embedding(blob, feature_dim)
        if embeddings_bd:
            dim_bd = embeddings_bd[0].size
            compatible = dim_bd == feature_dim
            if not compatible:
                todos_compatibles = False
            print("    Usuario '{}': dim_BD={} vs dim_pipeline={} -> {}".format(
                u["nombre_completo"], dim_bd, feature_dim,
                "COMPATIBLE" if compatible else "INCOMPATIBLE"))
        else:
            print("    Usuario '{}': 0 embeddings deserializados".format(u["nombre_completo"]))
    print()

    # --- Comparacion con usuario asociado ---
    if usuario_asociado:
        print("[7] COMPARACION: FOTO vs EMBEDDING EN BD (MISMO USUARIO)")
        blob = obtener_embedding(usuario_asociado["id"])
        if blob:
            embeddings_bd = deserializar_embedding(blob, feature_dim)
            if embeddings_bd and embedding_foto is not None:
                for i, emb_bd in enumerate(embeddings_bd):
                    sim = similitud_distribucion(embedding_foto, emb_bd)
                    print("    Foto vs muestra_{} del usuario '{}':".format(i, usuario_asociado["nombre_completo"]))
                    print("      Cosine Similarity:  {:.6f}".format(sim['cosine_similarity']))
                    print("      Dot Product:        {:.6f}".format(sim['dot_product']))
                    print("      Dist. Euclidiana:   {:.6f}".format(sim['euclidean_distance']))
                    print("      Mean Abs Diff:      {:.6f}".format(sim['mean_abs_diff']))
                    print("      Max Abs Diff:       {:.6f}".format(sim['max_abs_diff']))
                    print("      Std Abs Diff:       {:.6f}".format(sim['std_abs_diff']))
                    print("      Componentes similares (>0.95): {} / {}".format(
                        sim['componentes_similares_gt_095'], feature_dim))
                    print()

                # Umbral del sistema
                umbral = Config.CONFIDENCE_THRESHOLD
                print("    Umbral de confianza del sistema: {}".format(umbral))
                mejor_sim = max(cos_sim(embedding_foto, emb) for emb in embeddings_bd)
                if mejor_sim >= umbral:
                    print("    RESULTADO: RECONOCERIA al usuario (mejor_sim={} >= umbral={})".format(
                        mejor_sim, umbral))
                else:
                    print("    RESULTADO: NO RECONOCERIA al usuario (mejor_sim={} < umbral={})".format(
                        mejor_sim, umbral))
        print()

    # --- Comparacion cruzada con TODOS los usuarios ---
    print("[8] COMPARACION CRUZADA: FOTO vs TODOS LOS USUARIOS")
    for u in usuarios:
        blob = obtener_embedding(u["id"])
        if blob is None:
            continue
        embeddings_bd = deserializar_embedding(blob, feature_dim)
        if not embeddings_bd:
            continue

        sims = [cos_sim(embedding_foto, emb) for emb in embeddings_bd]
        mejor = max(sims)
        peor = min(sims)
        promedio = np.mean(sims)
        print("    Usuario '{}': mejor={:.6f}, peor={:.6f}, promedio={:.6f}".format(
            u["nombre_completo"], mejor, peor, promedio))

    print()

    # --- Analisis de componentes del embedding ---
    print("[9] DESCOMPOSICION DEL EMBEDDING OPENCV (dim={})".format(feature_dim))
    gris = extractor.preprocesar_gris(np.zeros((96, 96, 3), dtype=np.uint8))
    gris_64 = cv2.resize(gris, (64, 64), interpolation=cv2.INTER_AREA)
    hog_dim = extractor.hog.compute(gris_64).flatten().size

    gris_96 = cv2.resize(gris, (96, 96), interpolation=cv2.INTER_AREA)
    centro = gris_96[1:-1, 1:-1]
    lbp_temp = np.zeros_like(centro, dtype=np.uint8)
    vecinos = [
        gris_96[:-2, :-2], gris_96[:-2, 1:-1], gris_96[:-2, 2:],
        gris_96[1:-1, 2:], gris_96[2:, 2:], gris_96[2:, 1:-1],
        gris_96[2:, :-2], gris_96[1:-1, :-2],
    ]
    for bit, vecino in enumerate(vecinos):
        lbp_temp |= ((vecino >= centro) << bit).astype(np.uint8)
    lbp_hist_dim = 0
    for fila in np.array_split(lbp_temp, 4, axis=0):
        for celda in np.array_split(fila, 4, axis=1):
            lbp_hist_dim += 32

    proy_dim = 64  # 32 horizontal + 32 vertical

    print("    HOG (64x64):      {} dimensiones".format(hog_dim))
    print("    LBP Histograms:   {} dimensiones (16 celdas x 32 bins)".format(lbp_hist_dim))
    print("    Proyecciones:     {} dimensiones".format(proy_dim))
    print("    TOTAL:            {}".format(hog_dim + lbp_hist_dim + proy_dim))
    print()

    # --- Analisis discriminativo ---
    print("[10] ANALISIS DISCRIMINATIVO")
    print("     El embedding OpenCV combina:")
    print("       - HOG: gradientes orientados (textura/bordes)")
    print("       - LBP: patrones binarios locales (micro-textura)")
    print("       - Proyecciones: distribucion horizontal/vertical de intensidad")
    print()
    print("     Limitaciones inherentes de este enfoque:")
    print("       1. HOG y LBP son features GENERICOS de textura, no especificos de identidad facial")
    print("       2. Son muy sensibles a cambios de iluminacion, pose y expresion")
    print("       3. No tienen invarianza a rotacion/escala como los embeddings de redes neuronales")
    print("       4. La similaridad por coseno asume que embeddings de la misma persona")
    print("          estaran cerca en el espacio, pero con features genericos esto no se cumple")
    print("       5. Dlib usa una red neuronal (ResNet-34) entrenada en millones de caras,")
    print("          produciendo embeddings de 128 dims semanticamente significativos")
    print()

    print("=" * 70)
    print("  AUDITORIA COMPLETADA")
    print("=" * 70)


if __name__ == '__main__':
    main()
