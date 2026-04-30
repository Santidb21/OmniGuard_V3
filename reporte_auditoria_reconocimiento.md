# Reporte de Auditoría de Reconocimiento Facial - OmniGuard V3

**Fecha:** 2026-04-30  
**Estado:** FALLA DETECTADA - Falsos positivos por baja discriminación inter-persona

---

## 1. Entorno de Ejecución

| Componente | Valor |
|---|---|
| **Sistema Operativo** | Windows 11 (AMD64) |
| **CPU** | Intel64 Family 6 Model 190 (GenuineIntel) |
| **Python** | 3.12.7 (CPython) |
| **OpenCV** | 4.9.0 |
| **NumPy** | 1.26.3 |
| **SQLite** | 3.45.3 |
| **face_recognition** | NO DISPONIBLE (timeout tras 8s) |
| **Motor activo** | OpenCV fallback (HOG + LBP + Proyecciones) |

---

## 2. Arquitectura del Embedding OpenCV

El sistema genera vectores de **2340 dimensiones** compuestos por:

| Componente | Dimensiones | Descripción |
|---|---|---|
| **HOG** | 1764 | Histogram of Oriented Gradients sobre rostro 64x64 |
| **LBP Histograms** | 512 | Local Binary Patterns en grilla 4x4 (16 celdas × 32 bins) |
| **Proyecciones** | 64 | Promedios horizontal (32) + vertical (32) de intensidad |

Todos los vectores son normalizados a norma unitaria (`embedding / ||embedding||`).

---

## 3. Estado de la Base de Datos

| Usuario | ID | Tipo | Muestras | Dim | Norma |
|---|---|---|---|---|---|
| israel | 01 | residente | 5 | 2340 | 1.0 |
| Santiago Alvarado | 03 | residente | 3 | 2340 | 1.0 |

**Compatibilidad dimensional:** TODAS COMPATIBLES (2340 == 2340)

---

## 4. Hallazgo Crítico: BAJA DISCRIMINACIÓN INTER-PERSONA

### 4.1 Consistencia INTRA-persona (misma persona, distintas fotos)

| Usuario | Muestras comparadas | Cosine Similarity |
|---|---|---|
| israel | muestra_0 vs muestra_1 | **0.9461** |
| israel | muestra_0 vs muestra_2 | **0.9178** |
| israel | muestra_0 vs muestra_3 | **0.9301** |
| israel | muestra_0 vs muestra_4 | **0.9532** |
| Santiago | muestra_0 vs muestra_1 | **0.9713** |
| Santiago | muestra_0 vs muestra_2 | **0.7345** |

Promedio intra-persona israel: **0.9368** (rango 0.91-0.95)

### 4.2 Confusión INTER-persona (foto de persona A vs embeddings de persona B)

| Foto de | Contra embeddings de | Mejor similitud | Peor similitud | Promedio |
|---|---|---|---|---|
| israel | Santiago Alvarado | **0.8296** | 0.7418 | **0.7730** |

### 4.3 El Problema Matemático

El umbral de confianza del sistema es **0.78**.

```
Foto de israel vs mejor embedding de Santiago: cosine = 0.8296
Umbral del sistema:                           0.78
                                              ────────
0.8296 > 0.78  →  FALSO POSITIVO CONFIRMADO
```

La foto de "israel" comparada contra los embeddings de "Santiago Alvarado" produce una similitud de **0.8296**, que **supera el umbral de 0.78**. Esto significa que el sistema **podría reconocer erróneamente a israel como Santiago** (o viceversa).

### 4.4 Margen de Separación

| Métrica | Valor |
|---|---|
| Mejor similitud intra-persona (israel) | 0.9532 |
| Mejor similitud inter-persona (israel→Santiago) | 0.8296 |
| **Margen de separación** | **0.1236** |
| Umbral del sistema | 0.78 |
| `RECOGNITION_MARGIN` configurado | 0.08 |

El margen entre intra e inter persona (**0.1236**) es apenas ligeramente superior al `RECOGNITION_MARGIN` (0.08). Cualquier variación en iluminación, pose o ángulo puede cerrar esta brecha y causar falsos positivos.

---

## 5. Diagnóstico Técnico

### 5.1 ¿Por qué falla la discriminación?

**Los features HOG + LBP + Proyecciones NO son embeddings faciales.** Son descriptores genéricos de textura e intensidad que capturan:

- **HOG:** Dirección y magnitud de gradientes → bordes y contornos generales
- **LBP:** Patrones locales de textura → micro-estructuras de la imagen
- **Proyecciones:** Distribución macro de brillo → silueta general

Ninguno de estos descriptores está entrenado para distinguir **identidades faciales**. Capturan propiedades estadísticas de la imagen que son **compartidas entre todas las personas**: iluminación similar, fondo similar, resolución similar, ángulo de cámara similar.

### 5.2 Comparación con dlib (face_recognition)

| Característica | OpenCV Fallback | dlib (ResNet-34) |
|---|---|---|
| Dimensiones | 2340 | 128 |
| Tipo de features | Textura genérica (HOG+LBP) | Embedding semántico facial |
| Entrenamiento | Ninguno (algoritmos clásicos) | 3M+ caras etiquetadas |
| Invarianza a pose | Muy baja | Alta |
| Invarianza a iluminación | Baja | Media-Alta |
| Invarianza a expresión | Baja | Media |
| Separación inter-persona | ~0.12 margen | ~0.40+ margen |
| Falsos positivos esperados | **Altos** | Muy bajos |

### 5.3 Raíz del problema en código

En `detector.py`, la función `comparar_rostros()` calcula `np.dot(embedding1, embedding2)` como medida de similitud. Esto funciona matemáticamente correcto para vectores normalizados (dot product = cosine similarity). El problema no es la fórmula, es que **el espacio de features no tiene estructura semántica facial**.

El producto punto entre dos vectores HOG+LBP normalizados mide "qué tan similares son las texturas y gradientes", no "qué tan parecidas son las identidades faciales". Dos personas con iluminación y pose similares tendrán texturas estadísticamente parecidas, independientemente de quiénes sean.

---

## 6. Evidencia Numérica Concreta

### Foto de "israel" comparada contra ambos usuarios:

| Comparación | Cosine Similarity | Supera umbral 0.78? |
|---|---|---|
| israel vs sus propios embeddings (mejor) | **1.0000** | Sí (correcto) |
| israel vs sus propios embeddings (peor) | **0.9178** | Sí (correcto) |
| israel vs embeddings de Santiago (mejor) | **0.8296** | Sí (**FALSO POSITIVO**) |
| israel vs embeddings de Santiago (peor) | **0.7418** | No |

El mejor match contra la persona equivocada (0.8296) está solo **0.1236** por debajo del match contra la persona correcta (0.9532). Esta brecha es insuficiente para reconocimiento confiable.

---

## 7. Conclusión

**El fallback de OpenCV NO es viable para reconocimiento facial de identidad.** Puede detectar rostros (dibujar bounding boxes) correctamente, pero no puede distinguir entre personas de manera confiable porque:

1. Los features HOG+LBP capturan **textura genérica**, no **identidad facial**
2. El margen entre intra-persona e inter-persona (~0.12) es demasiado estrecho
3. Los falsos positivos son **inevitables** con el umbral actual de 0.78
4. Subir el umbral a 0.90+ causaría falsos negativos masivos (rechazaría a la persona correcta)

**Recomendación:** La única solución arquitectónica real es instalar `face_recognition` (dlib) correctamente, o integrar un modelo de embedding facial basado en red neuronal (ej: FaceNet, ArcFace, o InsightFace) que produzca embeddings semánticamente significativos para identificación.

---

*Reporte generado automáticamente por `auditoria_reconocimiento.py`*
