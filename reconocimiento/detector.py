import cv2
import numpy as np
import os
from config import Config
from models import obtener_usuarios_aceptados, obtener_embedding, obtener_usuario_por_id, registrar_entrada_salida, obtener_ultimo_registro
from datetime import datetime, timedelta
import threading
import time

face_recognition = None
try:
    import face_recognition as fr
    fr.face_encodings([])
    face_recognition = fr
except Exception as e:
    print("[WARN] face_recognition no disponible, usando OpenCV")

class DetectorRostro:
    def __init__(self):
        self.modelo = None
        self.usuarios_cache = []
        self.embeddings_cache = {}
        self.ultimo_ids_detencion = {}
        self.inicializado = False
        self.face_cascade = None
        
    def inicializar(self):
        try:
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            if face_recognition is not None:
                print("[INFO] Detector facial: face_recognition (dlib) + OpenCV")
            else:
                print("[INFO] Detector facial: OpenCV Haar Cascade")
            
            self.actualizar_cache()
            self.inicializado = True
            print("[INFO] Sistema de deteccion facial inicializado")
            return True
        except Exception as e:
            print(f"[ERROR] Error al inicializar detector: {e}")
            return False
    
    def actualizar_cache(self):
        try:
            usuarios = obtener_usuarios_aceptados()
            self.usuarios_cache = usuarios
            self.embeddings_cache = {}
            
            for usuario in usuarios:
                embedding = obtener_embedding(usuario['id'])
                if embedding:
                    try:
                        if face_recognition is not None:
                            self.embeddings_cache[usuario['id']] = np.frombuffer(embedding, dtype=np.float64)
                        else:
                            self.embeddings_cache[usuario['id']] = np.frombuffer(embedding, dtype=np.float32)
                    except:
                        pass
            
            print(f"[INFO] Cache actualizado: {len(self.embeddings_cache)} usuarios")
        except Exception as e:
            print(f"[ERROR] Error al actualizar cache: {e}")
    
    def detectar_rostro_dlib(self, imagen):
        try:
            imagen_rgb = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(imagen_rgb)
            
            if len(locations) > 0:
                top, right, bottom, left = locations[0]
                return top, left, bottom, right, 0.95
        except:
            pass
        return None
    
    def detectar_rostro_opencv(self, imagen):
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        rostros = self.face_cascade.detectMultiScale(gris, 1.1, 4)
        
        if len(rostros) > 0:
            x, y, w, h = rostros[0]
            return y, x+w, y+h, x, 0.85
        
        return None
    
    def detectar_rostro(self, imagen):
        if face_recognition is not None:
            resultado = self.detectar_rostro_dlib(imagen)
            if resultado:
                return resultado
        
        return self.detectar_rostro_opencv(imagen)
    
    def extraer_embedding_dlib(self, imagen, caja_rostro):
        try:
            imagen_rgb = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(imagen_rgb)
            
            if len(encodings) > 0:
                return encodings[0]
        except:
            pass
        return None
    
    def extraer_embedding_opencv(self, imagen, caja_rostro):
        x1, y1, x2, y2 = caja_rostro
        rostro = imagen[y1:y2, x1:x2]
        
        if rostro.size == 0:
            return None
        
        try:
            rostro_redim = cv2.resize(rostro, (150, 150))
            gris = cv2.cvtColor(rostro_redim, cv2.COLOR_BGR2GRAY)
            
            embedding = np.mean(gris, axis=0).flatten()
            embedding = embedding / (np.linalg.norm(embedding) + 1e-6)
            
            return embedding.astype(np.float32)
        except:
            return None
    
    def extraer_embedding(self, imagen, caja_rostro):
        if face_recognition is not None:
            embedding = self.extraer_embedding_dlib(imagen, caja_rostro)
            if embedding is not None:
                return embedding
        
        return self.extraer_embedding_opencv(imagen, caja_rostro)
    
    def comparar_rostros(self, embedding1, embedding2):
        if embedding1 is None or embedding2 is None:
            return 0.0
        
        try:
            if face_recognition is not None:
                distancia = np.linalg.norm(embedding1 - embedding2)
            else:
                distancia = np.linalg.norm(embedding1.astype(float) - embedding2.astype(float))
            
            similitud = 1.0 / (1.0 + distancia)
            return similitud
        except:
            return 0.0
    
    def reconocer_usuario(self, imagen):
        if not self.inicializado:
            return None, 0.0
        
        resultado = self.detectar_rostro(imagen)
        if resultado is None:
            return None, 0.0
        
        top, left, bottom, right, confianza_deteccion = resultado
        embedding = self.extraer_embedding(imagen, (left, top, right, bottom))
        
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
    
    def dibujar_deteccion(self, imagen):
        resultado = self.detectar_rostro(imagen)
        
        if resultado:
            top, left, bottom, right, confianza = resultado
            cv2.rectangle(imagen, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(imagen, f"Rostro: {confianza*100:.1f}%", (left, top-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        cv2.putText(imagen, "OMNIGUARD", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return imagen
    
    def procesar_frame(self, frame):
        usuario_id, confianza = self.reconocer_usuario(frame)
        
        if usuario_id:
            self.procesar_deteccion(usuario_id, confianza)
        
        return usuario_id, confianza
    
    def procesar_deteccion(self, usuario_id, confianza):
        ahora = datetime.now()
        
        if usuario_id in self.ultimo_ids_detencion:
            tiempo_ultimo = self.ultimo_ids_detencion[usuario_id]
            if (ahora - tiempo_ultimo).total_seconds() < 60:
                return
        
        ultimo = obtener_ultimo_registro()
        tipo_accion = 'entrada'
        
        if ultimo and ultimo['usuario_id'] == usuario_id:
            try:
                tiempo_diff = ahora - datetime.strptime(ultimo['fecha_hora'], '%Y-%m-%d %H:%M:%S')
                if tiempo_diff.total_seconds() < (Config.TIEMPO_SALIDA_MINUTOS * 60):
                    return
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
            self.ultimo_ids_detencion[usuario_id] = ahora
            print(f"[REGISTRO] {usuario['nombre_completo']} - {tipo_accion} - Confianza: {confianza*100:.1f}%")

detector = DetectorRostro()

def iniciar_deteccion():
    if detector.inicializar():
        return True
    return False

def obtener_detector():
    return detector