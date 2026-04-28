import cv2
import numpy as np
import os
from config import Config
from models import (obtener_usuarios_aceptados, obtener_embedding, 
                   obtener_usuario_por_id, registrar_entrada_salida, 
                   obtener_ultimo_registro)
from datetime import datetime, timedelta
import threading
import time

# face_recognition se maneja opcionalmente dentro de métodos
face_recognition = None

def intentar_cargar_face_recognition():
    """Carga face_recognition de forma segura dentro de una función"""
    global face_recognition
    if face_recognition is not None:
        return face_recognition
    try:
        import face_recognition as fr
        face_recognition = fr
        print("[INFO] face_recognition (dlib) cargado")
        return fr
    except:
        face_recognition = None
        return None

class DetectorRostro:
    def __init__(self):
        self.usuarios_cache = []
        self.embeddings_cache = {}
        self.ultimo_ids_deteccion = {}
        self.inicializado = False
        self.face_cascade = None
        
    def inicializar(self):
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            if self.face_cascade.empty():
                return False
            intentar_cargar_face_recognition()
            self.actualizar_cache()
            self.inicializado = True
            return True
        except:
            return False
    
    def actualizar_cache(self):
        try:
            usuarios = obtener_usuarios_aceptados()
            self.usuarios_cache = usuarios
            self.embeddings_cache = {}
            for usuario in usuarios:
                embedding_blob = obtener_embedding(usuario['id'])
                if embedding_blob:
                    try:
                        if face_recognition is not None:
                            self.embeddings_cache[usuario['id']] = np.frombuffer(embedding_blob, dtype=np.float64)
                        else:
                            self.embeddings_cache[usuario['id']] = np.frombuffer(embedding_blob, dtype=np.float32)
                    except:
                        pass
        except:
            pass
    
    def detectar_rostro_opencv(self, imagen):
        if self.face_cascade is None:
            return None
        try:
            gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
            rostros = self.face_cascade.detectMultiScale(gris, 1.1, 4)
            if len(rostros) > 0:
                x, y, w, h = rostros[0]
                return (x, y, x + w, y + h, 0.85)
            return None
        except:
            return None
    
    def extraer_embedding_opencv(self, imagen, caja_rostro):
        try:
            x1, y1, x2, y2 = caja_rostro
            rostro = imagen[y1:y2, x1:x2]
            if rostro.size == 0:
                return None
            rostro_redim = cv2.resize(rostro, (150, 150))
            gris = cv2.cvtColor(rostro_redim, cv2.COLOR_BGR2GRAY)
            embedding = np.mean(gris, axis=0).flatten()
            embedding = embedding / (np.linalg.norm(embedding) + 1e-6)
            return embedding.astype(np.float32)
        except:
            return None
    
    def comparar_rostros(self, embedding1, embedding2):
        if embedding1 is None or embedding2 is None:
            return 0.0
        try:
            distancia = np.linalg.norm(embedding1.astype(float) - embedding2.astype(float))
            similitud = 1.0 / (1.0 + distancia)
            return similitud
        except:
            return 0.0
    
    def reconocer_usuario(self, imagen):
        if not self.inicializado:
            return None, 0.0
        resultado = self.detectar_rostro_opencv(imagen)
        if resultado is None:
            return None, 0.0
        top, left, bottom, right, confianza = resultado
        embedding = self.extraer_embedding_opencv(imagen, (left, top, right, bottom))
        if embedding is None:
            return None, 0.0
        mejor_coincidencia = None
        mejor_confianza = Config.CONFIDENCE_THRESHOLD
        for usuario_id, embedding_guardado in self.embeddings_cache.items():
            similitud = self.comparar_rostros(embedding, embedding_guardado)
            if similitud > mejor_confianza:
                mejor_confianza = similitud
                mejor_coincidencia = usuario_id
        return mejor_coincidencia, mejor_confianza
    
    def procesar_deteccion(self, usuario_id, confianza):
        ahora = datetime.now()
        if usuario_id in self.ultimo_ids_deteccion:
            tiempo_ultimo = self.ultimo_ids_deteccion[usuario_id]
            if (ahora - tiempo_ultimo).total_seconds() < 60:
                return
        ultimo = obtener_ultimo_registro()
        tipo_accion = 'entrada'
        if ultimo and ultimo['usuario_id'] == usuario_id:
            try:
                fecha_ultimo = datetime.strptime(ultimo['fecha_hora'], '%Y-%m-%d %H:%M:%S')
                tiempo_diff = ahora - fecha_ultimo
                if tiempo_diff.total_seconds() < (Config.TIEMPO_SALIDA_MINUTOS * 60):
                    return
                if ultimo['tipo_accion'] == 'entrada':
                    tipo_accion = 'salida'
            except:
                tipo_accion = 'entrada'
        usuario = obtener_usuario_por_id(usuario_id)
        if usuario:
            registrar_entrada_salida(
                usuario_id,
                usuario['tipo'],
                usuario['numero_casa'],
                tipo_accion,
                round(confianza * 100, 2)
            )
            self.ultimo_ids_deteccion[usuario_id] = ahora

detector = DetectorRostro()

def iniciar_deteccion():
    return detector.inicializar()

def obtener_detector():
    return detector
