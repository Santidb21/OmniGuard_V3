# Registro de Errores - Fase 5: Hardware y Panel de Control

## Problemas detectados durante la implementación

### 1. Error de tipado en `extraer_embedding_imagen` (Fase 2 - previo)
- **Archivo:** `app.py` línea 135
- **Error:** `No overloads for "mean" match the provided arguments`
- **Causa:** `np.mean()` aplicado a una imagen `MatLike` de OpenCV
- **Solución:** La función funciona en runtime. Se mantiene así para compatibilidad.
- **Estado:** No bloqueante (warning de LSP, no error de ejecución)

### 2. cv2.data.haarcascades - Advertencia LSP
- **Archivo:** `reconocimiento/detector.py` línea 39
- **Error:** `"data" is not a known attribute of module "cv2"`
- **Causa:** LSP de Python no reconoce el atributo `data` de OpenCV
- **Solución:** Funciona correctamente en runtime. OpenCV incluye este atributo.
- **Estado:** Falso positivo del LSP, no afecta ejecución

### 3. Typing de CAPTURAS (VideoCapture vs None)
- **Archivo:** `app.py`
- **Error:** `Cannot access attribute "read/release/isOpened" for class "None"`
- **Causa:** `CAPTURAS` se inicializa con `None`, pero se asignan objetos `VideoCapture`
- **Solución:** Verificaciones previas en el código previenen errores en runtime.
- **Estado:** Los checks `if CAPTURAS.get(tipo_camara) is None` protegen el acceso

### 4. Parámetro faltante en extraer_embedding_opencv
- **Archivo:** `reconocimiento/detector.py`
- **Error:** `Argument missing for parameter "caja_rostro"` / `"imagen" is not defined`
- **Causa:** Refactorización incompleta entre `extraer_embedding_opencv` y `reconocer_usuario`
- **Solución:** Se agregó parámetro `imagen` a `extraer_embedding_opencv` y se pasa correctamente
- **Estado:** ✅ Corregido

### 5. OpenCV y hilos de video
- **Problema potencial:** OpenCV `VideoCapture` puede tener problemas en entornos multi-hilo
- **Mitigación:** Se usa una variable global por tipo de cámara (`entrada`, `salida`)
- **Nota:** En producción, si hay múltiples guardias accediendo simultáneamente, considerar usar locks

### 6. Detección facial en tiempo real
- **Problema:** El detector Haar Cascade es menos preciso que dlib/face_recognition
- **Solución implementada:** Se usa Haar para detección rápida y embeddings para reconocimiento
- **Trade-off:** Velocidad > Precisión absoluta. Umbral de confianza configurable en `Config.CONFIDENCE_THRESHOLD`

## Configuraciones recomendadas para producción

```bash
# Usar índices correctos de cámara (pueden variar)
export CAMERA_INDEX=0  # o 1, 2 dependiendo del hardware

# Ajustar sensibilidad de reconocimiento
export CONFIDENCE_THRESHOLD=0.60

# Tiempo mínimo entre detecciones (minutos)
export TIEMPO_SALIDA_MINUTOS=30
```

## Estado final
- ✅ Streaming de video implementado
- ✅ Detección y reconocimiento facial en tiempo real
- ✅ Registro automático de entradas/salidas
- ✅ Panel de control conectado
- ✅ Tests de Fase 5 creados
- ⚠️ LSP warnings presentes pero no bloquean ejecución
