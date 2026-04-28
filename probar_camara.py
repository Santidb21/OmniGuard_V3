import cv2
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config

print("=" * 50)
print("  OMNIGUARD - PRUEBA DE CAMARA")
print("=" * 50)

print("\nIniciando camara...")

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("[ERROR] No se pudo abrir la camara")
    print("Asegurate de que la webcam este conectada")
    input("\nPresiona Enter para salir...")
    sys.exit(1)

print("[OK] Camara iniciada correctamente")
print("\nPresiona 'Q' para salir")

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

while True:
    ret, frame = cap.read()
    
    if not ret:
        print("[ERROR] Error al capturar frame")
        break
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(frame, "Rostro detectado", (x, y-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    cv2.putText(frame, "OMNIGUARD - Prueba de Camara", (10, 30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    cv2.putText(frame, "Rostos detectados: " + str(len(faces)), (10, 60), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if len(faces) > 0 else (100, 100, 100), 2)
    
    cv2.imshow('OmniGuard - Prueba de Camara', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

print("\n[OK] Camara cerrada")
print("=" * 50)