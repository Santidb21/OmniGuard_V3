import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
import time
import cv2
from datetime import datetime
from app import app
from reconocimiento.detector import detector, iniciar_deteccion, FACE_RECOGNITION_DISPONIBLE
from reconocimiento.registros import exportar_registros_mensuales
from models import init_db, eliminar_visitantes_expirados
from config import Config

class OmniGuardService:
    def __init__(self):
        self.servidor_activo = False
        self.deteccion_activa = False
        self.hilo_servidor = None
        self.hilo_deteccion = None
        self.cap = None
        
    def iniciar_servidor(self):
        print("[INFO] Iniciando servidor Flask...")
        app.run(host=Config.HOST, port=Config.PORT, debug=False, use_reloader=False)
    
    def iniciar_deteccion_video(self):
        print("[INFO] Iniciando sistema de deteccion facial...")
        
        while not detector.inicializado:
            time.sleep(1)
        
        tipo_camara = Config.CAMERA_TYPE.lower()
        
        if tipo_camara == 'usb':
            self.cap = cv2.VideoCapture(Config.CAMERA_INDEX, cv2.CAP_DSHOW)
        elif tipo_camara == 'ip':
            self.cap = cv2.VideoCapture(Config.CAMERA_URL)
        else:
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        
        if not self.cap.isOpened():
            print("[ERROR] No se pudo abrir la camara")
            return
        
        print("[INFO] Camara iniciada correctamente")
        print("[INFO] Mostrando ventana de video en vivo...")
        frame_count = 0
        
        while self.deteccion_activa:
            ret, frame = self.cap.read()
            
            if not ret:
                print("[WARN] Error al capturar frame")
                time.sleep(1)
                continue
            
            frame = detector.dibujar_deteccion(frame)
            
            cv2.imshow('OMNIGUARD - Deteccion Facial en Vivo', frame)
            
            frame_count += 1
            
            if frame_count % int(Config.DETECTION_INTERVAL * 30) == 0:
                usuario_id, confianza = detector.procesar_frame(frame)
                
                if usuario_id:
                    print(f"[DETECCION] Usuario: {usuario_id}, Confianza: {confianza*100:.1f}%")
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                print("[INFO] Cerrando ventana de video...")
                break
            
            time.sleep(Config.DETECTION_INTERVAL)
        
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        print("[INFO] Camara liberada")
    
    def iniciar(self):
        print("=" * 50)
        print("  OMNIGUARD RESIDENTIAL AI - SERVICIO")
        print("  Sistema de Seguridad Inteligente")
        print("=" * 50)
        print("  Face Recognition: " + ("ACTIVO" if FACE_RECOGNITION_DISPONIBLE else "INACTIVO"))
        
        init_db()
        
        eliminar_visitantes_expirados()
        
        if not iniciar_deteccion():
            print("[WARN] Detector facial no disponible, continuando sin deteccion")
        
        self.servidor_activo = True
        self.deteccion_activa = True
        
        self.hilo_servidor = threading.Thread(target=self.iniciar_servidor, daemon=True)
        self.hilo_servidor.start()
        
        time.sleep(2)
        
        self.hilo_deteccion = threading.Thread(target=self.iniciar_deteccion_video, daemon=True)
        self.hilo_deteccion.start()
        
        print("\n" + "=" * 50)
        print("[INFO] Servidor iniciado en puerto " + str(Config.PORT))
        print("[INFO] Registro: http://localhost:" + str(Config.PORT) + "/registro")
        print("[INFO] Panel Guardia: http://localhost:" + str(Config.PORT) + "/login")
        print("[OK] Sistema activo y funcionando")
        print("")
        print("  CONTROLES:")
        print("  - Presiona 'Q' en la ventana de video para salir")
        print("=" * 50)
        
        try:
            while self.servidor_activo and self.deteccion_activa:
                time.sleep(10)
                
                if hasattr(detector, 'usuarios_cache'):
                    if len(detector.embeddings_cache) != len(detector.usuarios_cache):
                        detector.actualizar_cache()
                
                eliminar_visitantes_expirados()
                        
        except KeyboardInterrupt:
            print("\n[INFO] Deteniendo servicio...")
            self.detener()
    
    def detener(self):
        self.servidor_activo = False
        self.deteccion_activa = False
        
        if self.cap:
            self.cap.release()
        
        cv2.destroyAllWindows()
        print("[INFO] Servicio detenido")

def main():
    servicio = OmniGuardService()
    servicio.iniciar()

if __name__ == '__main__':
    main()
