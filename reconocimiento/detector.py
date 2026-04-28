import io
import os
import time
from datetime import datetime

import cv2
import numpy as np

from config import BASE_DIR, Config
from models import (
    obtener_usuarios_aceptados,
    obtener_embedding,
    obtener_usuario_por_id,
    registrar_entrada_salida,
    obtener_ultimo_registro,
    obtener_ultimo_registro_usuario,
    guardar_embedding,
)


face_recognition = None


def intentar_cargar_face_recognition():
    global face_recognition
    if face_recognition is not None:
        return face_recognition
    try:
        import face_recognition as fr

        face_recognition = fr
        print("[INFO] face_recognition (dlib) cargado")
        return fr
    except Exception:
        face_recognition = None
        return None


class DetectorRostro:
    def __init__(self):
        self.usuarios_cache = []
        self.embeddings_cache = {}
        self.ultimo_ids_deteccion = {}
        self.inicializado = False
        self.face_cascades = []
        self.hog = cv2.HOGDescriptor(
            _winSize=(64, 64),
            _blockSize=(16, 16),
            _blockStride=(8, 8),
            _cellSize=(8, 8),
            _nbins=9,
        )
        self.feature_dim = None

    def inicializar(self):
        try:
            self.face_cascades = []
            nombres_cascade = [
                "haarcascade_frontalface_default.xml",
                "haarcascade_frontalface_alt2.xml",
            ]
            for nombre in nombres_cascade:
                cascade_path = cv2.data.haarcascades + nombre
                cascade = cv2.CascadeClassifier(cascade_path)
                if not cascade.empty():
                    self.face_cascades.append(cascade)

            if not self.face_cascades:
                return False

            intentar_cargar_face_recognition()
            dummy = np.zeros((96, 96, 3), dtype=np.uint8)
            self.feature_dim = len(self.extraer_embedding_opencv(dummy, (0, 0, 96, 96)))
            self.actualizar_cache()
            self.inicializado = True
            return True
        except Exception as e:
            print("[ERROR] Inicializando detector: {}".format(e))
            return False

    def serializar_embeddings(self, embeddings):
        validos = [e.astype(np.float32) for e in embeddings if e is not None and e.size > 0]
        if not validos:
            return None
        arr = np.vstack(validos).astype(np.float32)
        buffer = io.BytesIO()
        np.save(buffer, arr, allow_pickle=False)
        return buffer.getvalue()

    def deserializar_embeddings(self, embedding_blob):
        if not embedding_blob:
            return []
        data = bytes(embedding_blob)
        try:
            if data.startswith(b"\x93NUMPY"):
                arr = np.load(io.BytesIO(data), allow_pickle=False)
            else:
                arr = np.frombuffer(data, dtype=np.float32)
                if arr.size == 0 or arr.size % max(1, self.feature_dim or arr.size) != 0:
                    arr = np.frombuffer(data, dtype=np.float64).astype(np.float32)

            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            return [fila.astype(np.float32) for fila in arr if fila.size > 0]
        except Exception:
            return []

    def actualizar_cache(self):
        try:
            usuarios = obtener_usuarios_aceptados()
            self.usuarios_cache = usuarios
            self.embeddings_cache = {}

            for usuario in usuarios:
                embeddings = self.deserializar_embeddings(obtener_embedding(usuario["id"]))
                embeddings = [e for e in embeddings if self.embedding_compatible(e)]

                if not embeddings and usuario["foto_path"]:
                    embeddings = self.reentrenar_desde_foto_usuario(usuario)

                if embeddings:
                    self.embeddings_cache[usuario["id"]] = embeddings

            print("[INFO] Cache facial: {} usuarios, {} muestras".format(
                len(self.embeddings_cache),
                sum(len(v) for v in self.embeddings_cache.values()),
            ))
        except Exception as e:
            print("[ERROR] Actualizando cache facial: {}".format(e))

    def embedding_compatible(self, embedding):
        return (
            embedding is not None
            and embedding.ndim == 1
            and self.feature_dim is not None
            and embedding.size == self.feature_dim
        )

    def reentrenar_desde_foto_usuario(self, usuario):
        try:
            foto_path = usuario["foto_path"] or ""
            ruta_relativa = foto_path.lstrip("/").replace("/", os.sep)
            ruta_abs = os.path.join(str(BASE_DIR), ruta_relativa)
            if not os.path.exists(ruta_abs):
                ruta_abs = os.path.join(os.path.dirname(Config.DB_PATH), "..", ruta_relativa)
            if not os.path.exists(ruta_abs):
                return []

            embeddings = self.extraer_embeddings_de_archivo(ruta_abs)
            serializado = self.serializar_embeddings(embeddings)
            if serializado:
                guardar_embedding(usuario["id"], serializado)
            return embeddings
        except Exception:
            return []

    def preprocesar_gris(self, imagen):
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if len(imagen.shape) == 3 else imagen
        gris = cv2.GaussianBlur(gris, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gris)

    def detectar_rostros_opencv(self, imagen):
        if not self.face_cascades:
            return []

        try:
            gris = self.preprocesar_gris(imagen)
            alto, ancho = gris.shape[:2]
            min_lado = max(56, int(min(ancho, alto) * 0.14))
            candidatos = []

            for cascade in self.face_cascades:
                rostros = cascade.detectMultiScale(
                    gris,
                    scaleFactor=1.05,
                    minNeighbors=6,
                    minSize=(min_lado, min_lado),
                )
                for x, y, w, h in rostros:
                    aspecto = w / float(h)
                    area = w * h
                    if 0.70 <= aspecto <= 1.35 and area >= min_lado * min_lado:
                        candidatos.append((int(x), int(y), int(x + w), int(y + h)))

            return self.filtrar_rostros(candidatos)
        except Exception:
            return []

    def detectar_rostro_opencv(self, imagen):
        rostros = self.detectar_rostros_opencv(imagen)
        if not rostros:
            return None
        x1, y1, x2, y2 = rostros[0]
        return (x1, y1, x2, y2, 0.85)

    def filtrar_rostros(self, cajas):
        if not cajas:
            return []

        cajas = sorted(cajas, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
        finales = []
        for caja in cajas:
            if all(self.iou(caja, existente) < 0.35 for existente in finales):
                finales.append(caja)
        return finales

    def iou(self, a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        return inter / float(area_a + area_b - inter + 1e-6)

    def normalizar_caja(self, imagen, caja_rostro):
        x1, y1, x2, y2 = caja_rostro
        alto, ancho = imagen.shape[:2]
        w, h = x2 - x1, y2 - y1
        margen_x, margen_y = int(w * 0.12), int(h * 0.16)
        x1, y1 = max(0, x1 - margen_x), max(0, y1 - margen_y)
        x2, y2 = min(ancho, x2 + margen_x), min(alto, y2 + margen_y)
        return x1, y1, x2, y2

    def extraer_embedding_opencv(self, imagen, caja_rostro):
        try:
            x1, y1, x2, y2 = self.normalizar_caja(imagen, caja_rostro)
            rostro = imagen[y1:y2, x1:x2]
            if rostro.size == 0:
                return None

            gris = self.preprocesar_gris(rostro)
            gris_96 = cv2.resize(gris, (96, 96), interpolation=cv2.INTER_AREA)
            gris_64 = cv2.resize(gris, (64, 64), interpolation=cv2.INTER_AREA)

            hog = self.hog.compute(gris_64).flatten().astype(np.float32)
            lbp_hist = self.histograma_lbp(gris_96)
            proyecciones = self.proyecciones(gris_96)

            embedding = np.concatenate([hog, lbp_hist, proyecciones]).astype(np.float32)
            norm = np.linalg.norm(embedding)
            if norm <= 1e-6:
                return None
            return embedding / norm
        except Exception:
            return None

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
        filas = np.array_split(lbp, 4, axis=0)
        for fila in filas:
            celdas = np.array_split(fila, 4, axis=1)
            for celda in celdas:
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

    def extraer_embeddings_de_archivo(self, image_path):
        imagen = cv2.imread(image_path)
        if imagen is None:
            return []
        rostros = self.detectar_rostros_opencv(imagen)
        if not rostros:
            return []
        embedding = self.extraer_embedding_opencv(imagen, rostros[0])
        return [embedding] if embedding is not None else []

    def comparar_rostros(self, embedding1, embedding2):
        if not self.embedding_compatible(embedding1) or not self.embedding_compatible(embedding2):
            return 0.0
        try:
            similitud = float(np.dot(embedding1, embedding2))
            return max(0.0, min(1.0, similitud))
        except Exception:
            return 0.0

    def analizar_frame(self, imagen):
        if not self.inicializado:
            return {"rostro": None, "usuario_id": None, "confianza": 0.0}

        rostros = self.detectar_rostros_opencv(imagen)
        if not rostros:
            return {"rostro": None, "usuario_id": None, "confianza": 0.0}

        caja = rostros[0]
        embedding = self.extraer_embedding_opencv(imagen, caja)
        if embedding is None:
            return {"rostro": caja, "usuario_id": None, "confianza": 0.0}

        mejor_coincidencia = None
        mejor_confianza = 0.0
        umbral = float(Config.CONFIDENCE_THRESHOLD)

        for usuario_id, muestras in self.embeddings_cache.items():
            for embedding_guardado in muestras:
                similitud = self.comparar_rostros(embedding, embedding_guardado)
                if similitud > mejor_confianza:
                    mejor_confianza = similitud
                    mejor_coincidencia = usuario_id

        if mejor_confianza < umbral:
            mejor_coincidencia = None

        return {
            "rostro": caja,
            "usuario_id": mejor_coincidencia,
            "confianza": mejor_confianza,
        }

    def reconocer_usuario(self, imagen):
        resultado = self.analizar_frame(imagen)
        return resultado["usuario_id"], resultado["confianza"]

    def procesar_deteccion(self, usuario_id, confianza, tipo_accion=None):
        ahora = datetime.now()
        tipo_forzado = tipo_accion in ("entrada", "salida")
        tipo_cache = (usuario_id, tipo_accion) if tipo_forzado else usuario_id

        if tipo_cache in self.ultimo_ids_deteccion:
            tiempo_ultimo = self.ultimo_ids_deteccion[tipo_cache]
            if (ahora - tiempo_ultimo).total_seconds() < 20:
                return

        if tipo_forzado:
            ultimo = obtener_ultimo_registro_usuario(usuario_id)
            if ultimo and ultimo["tipo_accion"] == tipo_accion:
                try:
                    fecha_ultimo = datetime.strptime(ultimo["fecha_hora"], "%Y-%m-%d %H:%M:%S")
                    if (ahora - fecha_ultimo).total_seconds() < 60:
                        return
                except Exception:
                    pass
        else:
            ultimo = obtener_ultimo_registro()
            tipo_accion = "entrada"
            if ultimo and ultimo["usuario_id"] == usuario_id:
                try:
                    fecha_ultimo = datetime.strptime(ultimo["fecha_hora"], "%Y-%m-%d %H:%M:%S")
                    tiempo_diff = ahora - fecha_ultimo
                    if tiempo_diff.total_seconds() < (Config.TIEMPO_SALIDA_MINUTOS * 60):
                        return
                    if ultimo["tipo_accion"] == "entrada":
                        tipo_accion = "salida"
                except Exception:
                    tipo_accion = "entrada"

        if tipo_accion not in ("entrada", "salida"):
            return

        usuario = obtener_usuario_por_id(usuario_id)
        if usuario:
            registrar_entrada_salida(
                usuario_id,
                usuario["tipo"],
                usuario["numero_casa"],
                tipo_accion,
                round(confianza * 100, 2),
            )
            self.ultimo_ids_deteccion[tipo_cache] = ahora


detector = DetectorRostro()


def iniciar_deteccion():
    return detector.inicializar()


def obtener_detector():
    return detector
