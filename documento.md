# OmniGuard Residential AI - Documentación Completa del Sistema

## 1. Visión General del Proyecto

### 1.1 Descripción
**OmniGuard Residential AI** es un sistema de seguridad basado en reconocimiento facial diseñado específicamente para fraccionamientos residenciales. El sistema permite el registro de residentes y visitantes mediante una aplicación web segura, y automatiza el control de acceso a través de detección facial en tiempo real.

### 1.2 Funcionalidades Principales
- **Registro de usuarios**: Los residentes y visitantes pueden registrarse subiendo una foto de su rostro
- **Reconocimiento facial en tiempo real**: Detecta y compara rostros con los usuarios registrados
- **Control de acceso automático**: Determina si una persona es residente o visitante y registra entrada/salida
- **Sistema de dos cámaras**: Configurable para cámara de entrada y cámara de salida
- **Panel de control del guardia**: Interfaz intuitiva para gestionar solicitudes y ver registros
- **Eliminación automática de visitantes**: Los visitantes expirados se eliminan después de 1 mes
- **Registros mensuales**: Exportación automática de registros cada fin de mes

### 1.3 Flujo de Operación

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  Usuario   │────▶│   Registro   │────▶│   Guardia  │────▶│    Cámara    │
│  Externo   │     │    (Web)     │     │  (Aprueba) │     │  (Detecta)   │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
       │                   │                    │                    │
       │                   │                    │                    │
       ▼                   ▼                    ▼                    ▼
  Solicitud           BD: Solicitud         Solicitud           Registro de
  Pendiente          Pendiente             Aceptada            Entrada/Salida
```

---

## 2. Arquitectura del Sistema

### 2.1 Diagrama de Arquitectura

```
                            INTERNET / RED LOCAL
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │     SERVIDOR FLASK           │
                    │   (Puerto 5000)              │
                    │                               │
                    │  ┌─────────────────────────┐ │
                    │  │  API REST               │ │
                    │  │  - Registro              │ │
                    │  │  - Cámara               │ │
                    │  │  - Usuarios              │ │
                    │  └─────────────────────────┘ │
                    │               │               │
                    │   ┌───────────┴───────────┐  │
                    │   ▼                       ▼  │
                    │ ┌──────┐            ┌─────────┐
                    │ │SQLite│            │ OpenCV │
                    │ │  DB  │            │ Detección│
                    │ └──────┘            └─────────┘
                    │    │                     │
                    └────┼─────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
   ┌─────────┐     ┌─────────┐     ┌─────────┐
   │ Cámara │     │ Cámara  │     │ static/ │
   │  USB   │     │   IP    │     │  fotos/ │
   └─────────┘     └─────────┘     └─────────┘
```

### 2.2 Estructura de Archivos

```
OmniGuard_V3/
│
├── app.py                      # Servidor principal Flask
│                               # Maneja todas las rutas API y páginas web
├── config.py                   # Configuraciones del sistema
│                               # (BD, puerto, credenciales, umbral)
├── models.py                   # Modelos de base de datos SQLite
│                               # Funciones CRUD y gestión de datos
├── requirements.txt           # Dependencias Python
├── documento.md               # Esta documentación
├── servicio_windows.py        # Servicio de Windows con cámara
│                               # Para ejecución en segundo plano
├── probar_camara.py           # Script de prueba de cámara
│
├── reconocimiento/
│   ├── __init__.py
│   ├── detector.py           # Motor de detección facial
│   │                         # Usa OpenCV Haar Cascade
│   │                         # (o face_recognition si está disponible)
│   └── registros.py          # Lógica de registros mensuales
│
├── templates/
│   ├── registro.html         # Página de registro de usuarios
│   ├── guardia.html          # Panel de control del guardia
│   └── login.html            # Página de inicio de sesión
│
├── static/
│   ├── css/
│   │   └── estilos.css       # Estilos CSS (Diseño Bruce Wayne)
│   │                         # Colores oscuros, dorado sutil
│   └── fotos/                # Fotos de rostros de usuarios
│       └── *.jpg            # Imágenes cargadas por usuarios
│
├── DB/
│   ├── omniguard.db         # Base de datos SQLite principal
│   │                         # Tablas: usuarios, solicitudes,
│   │                         # registros_entrada_salida, etc.
│   └── Registros_Mensuales/  # Backups mensuales
│       └── Abril_2026.db    # Registros exportados por mes
│
└── logs/                     # Archivos de log del sistema
```

### 2.3 Tecnologías Utilizadas

| Componente | Tecnología | Versión |
|------------|------------|---------|
| Backend | Flask | 3.0.0 |
| Base de Datos | SQLite | 3.x |
| Reconocimiento Facial | OpenCV | 4.9.0 |
| (Opcional) Reconocimiento | face_recognition (dlib) | 1.3.0 |
| Frontend | HTML5, CSS3, JavaScript | - |
| Diseño UI | Estilo Bruce Wayne | - |

---

## 3. Especificación Técnica

### 3.1 Modelo de Datos

#### Tabla: usuarios
| Campo | Tipo | Descripción | Ejemplo |
|-------|------|-------------|---------|
| id | TEXT | ID único (residente: 01-99, visitante: 001-999) | "01" |
| nombre_completo | TEXT | Nombre completo del usuario | "Juan Pérez" |
| numero_casa | TEXT | Número de casa | "42" |
| tipo | TEXT | "residente" o "visitante" | "residente" |
| foto_path | TEXT | Ruta de la foto del rostro | "/static/fotos/20260425_foto.jpg" |
| fecha_registro | DATETIME | Fecha de registro en el sistema | "2026-04-25 14:30:00" |
| fecha_aceptacion | DATETIME | Fecha en que el guardia aceptó la solicitud | "2026-04-25 15:00:00" |
| fecha_expiracion | DATETIME | Fecha de expiración (visitantes) | "2026-05-25 15:00:00" |
| estado | TEXT | Estado: pendientes/aceptado/denegado/baja | "aceptado" |
| embedding | BLOB | Vector numérico (128 valores) que representa el rostro | (datos binarios) |

#### Tabla: solicitudes
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | ID automático de la solicitud |
| usuario_id | TEXT | ID del usuario asociado |
| nombre_completo | TEXT | Copia del nombre |
| numero_casa | TEXT | Copia del número de casa |
| tipo | TEXT | Residente o visitante |
| foto_path | TEXT | Ruta de la foto |
| estado | TEXT | "pendiente", "aceptado", "denegado" |
| fecha_solicitud | DATETIME | Fecha de la solicitud |
| revisado_por | TEXT | Usuario que revisó (guardia) |

#### Tabla: registros_entrada_salida
| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | ID automático del registro |
| usuario_id | TEXT | ID del usuario detectado |
| tipo_usuario | TEXT | Residente o visitante |
| numero_casa | TEXT | Número de casa del usuario |
| fecha_hora | DATETIME | Fecha y hora de la detección |
| tipo_accion | TEXT | "entrada" o "salida" |
| confianza | REAL | Porcentaje de confianza del reconocimiento (0-100) |

### 3.2 Algoritmo de Reconocimiento Facial

#### Proceso de Registro:
1. Usuario sube foto del rostro
2. Sistema detecta el rostro en la imagen
3. Se calcula el **embedding** (vector de 128 valores numéricos)
4. El embedding se guarda en la base de datos

#### Proceso de Detección:
1. Cámara captura frame de video
2. Se detecta el rostro en el frame (OpenCV Haar Cascade)
3. Se calcula el embedding del rostro detectado
4. Se compara con todos los embeddings en la base de datos
5. Si la similitud >= 60%, se identifica al usuario
6. Se registra entrada o salida según la cámara

#### Fórmula de Similitud:
```
similitud = 1 / (1 + distancia euclidiana entre embeddings)
```

### 3.3 Lógica de Entrada/Salida

```
┌─────────────────────────────────────────────────────────────┐
│                    LÓGICA DE DETECCIÓN                       │
├─────────────────────────────────────────────────────────────┤
│  1. Usuario detectado en cámara                             │
│       │                                                      │
│       ▼                                                      │
│  2. ¿Es usuario registrado?                                 │
│       │                                                      │
│       ├── NO → Ignorar (no registrar)                        │
│       │                                                      │
│       └── SÍ → ¿Ya fue detectado recientemente?            │
│                     │                                        │
│                     ├── SÍ (< 30 min) → Ignorar              │
│                     │                                        │
│                     └── NO → Determinar acción              │
│                                   │                          │
│                                   ▼                          │
│                    ┌────────────────────────────────┐       │
│                    │  ¿Última acción registrada      │       │
│                    │  del usuario fue ENTRADA?      │       │
│                    └────────────────────────────────┘       │
│                           │                                  │
│                           ├── SÍ →Registrar SALIDA           │
│                           │                                  │
│                           └── NO →Registrar ENTRADA         │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Instalación

### 4.1 Requisitos del Sistema

| Requisito | Especificación Mínima |
|-----------|----------------------|
| Sistema Operativo | Windows 10/11 o Linux |
| Python | 3.8 o superior |
| RAM | 4 GB |
| Almacenamiento | 500 MB libres |
| Cámara | USB o IP (para detección) |

### 4.2 Instalación de Dependencias

```cmd
# Navegar al directorio del proyecto
cd C:\Users\Santiago\Desktop\OmniGuard_V3

# Instalar dependencias
pip install -r requirements.txt
```

### 4.3 Dependencias del requirements.txt

```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-CORS==4.0.0
opencv-python==4.9.0.80
numpy==1.26.3
Pillow>=10.2.0
python-socketio==5.11.0
eventlet==0.35.1
werkzeug==3.0.1
face-recognition>=1.3.0
deepface>=0.0.90  # Alternativa a face_recognition
```

### 4.4 Instalación de face_recognition (Requisito Obligatorio)

El sistema **requiere** face_recognition para funcionar correctamente. Para mayor precisión en el reconocimiento facial:

```cmd
# Navegar al directorio del proyecto
cd C:\Users\Santiago\Desktop\OmniGuard_V3

# Instalar face_recognition
pip install face_recognition

# Instalar los modelos (requiere Git en el PATH)
pip install git+https://github.com/ageitgey/face_recognition_models
```

### 4.5 Alternativa: DeepFace

Si face_recognition no puede instalarse (por ejemplo, si Git no está disponible), se puede usar **DeepFace** como alternativa:

```cmd
pip install deepface
```

DeepFace ofrece:
- Precisión ~97%
- Instalación simple con pip (sin Git)
- Soporte para múltiples backends (TensorFlow, PyTorch, etc.)

**Nota**: Si ambos están instalados, el sistema prioriza face_recognition.

---

## 5. Configuración

### 5.1 Archivo config.py

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()

class Config:
    # ============ BASE DE DATOS ============
    SECRET_KEY = 'omniguard-secret-key-2026'
    DB_PATH = os.path.join(BASE_DIR, 'DB', 'omniguard.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ============ SERVIDOR ============
    HOST = '0.0.0.0'  # 0.0.0.0 = accesible desde cualquier IP
    PORT = 5000
    DEBUG = True
    
    # ============ CÁMARAS ============
    CAMERA_TYPE = 'usb'  # usb | ip
    CAMERA_INDEX = 0    # Índice de cámara USB (0 = primera cámara)
    CAMERA_URL = ''     # URL de cámara IP (rtsp://...)
    
    # ============ SEGURIDAD ============
    ADMIN_USERNAME = 'guardia'
    ADMIN_PASSWORD = 'admin123'
    
    # ============ RECONOCIMIENTO FACIAL ============
    # Umbral de similitud (0.60 = 60%)
    # Mayor = más estricto, Menor = más flexible
    CONFIDENCE_THRESHOLD = 0.60
    # Intervalo entre detecciones (segundos)
    DETECTION_INTERVAL = 2.0
    
    # ============ RUTAS ============
    FOTOS_PATH = os.path.join(BASE_DIR, 'static', 'fotos')
    REGISTROS_PATH = os.path.join(BASE_DIR, 'DB', 'Registros_Mensuales')
    LOGS_PATH = os.path.join(BASE_DIR, 'logs')
    
    # ============ LÍMITES ============
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB máx para fotos
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    TIEMPO_SALIDA_MINUTOS = 30  # Minutos entre entrada y salida
```

### 5.2 Configuración de Cámaras

#### Cámara USB:
Simplemente conecte la cámara al puerto USB y el sistema la detectará automáticamente.

#### Cámara IP (Inalámbrica):
1. Obtenga la URL de stream de su cámara IP
2. Configure en `config.py`:
```python
CAMERA_TYPE = 'ip'
CAMERA_URL = 'rtsp://usuario:password@192.168.1.100:554/stream'
```

### 5.3 Credenciales por Defecto

| Campo | Valor |
|-------|-------|
| Usuario del guardia | `guardia` |
| Contraseña | `admin123` |

**Nota**: Se recomienda cambiar estas credenciales en producción.

---

## 6. Uso del Sistema

### 6.1 Iniciar el Servidor

```cmd
python C:\Users\Santiago\Desktop\OmniGuard_V3\app.py
```

El servidor iniciado en:
- **Local**: http://localhost:5000
- **Red local**: http://192.168.1.55:5000 (varía según IP)

### 6.2 URLs del Sistema

| Página | URL | Descripción |
|--------|-----|-------------|
| Registro | http://localhost:5000/registro | Para que usuarios se registren |
| Login | http://localhost:5000/login | Acceso del guardia |
| Panel Guardia | http://localhost:5000/guardia | Panel de control |

---

## 7. Manual del Usuario (Guardia)

### 7.1 Iniciar Sesión

1. Abra el navegador y vaya a: `http://localhost:5000/login`
2. Ingrese las credenciales:
   - Usuario: `guardia`
   - Contraseña: `admin123`
3. Click en "Iniciar Sesión"

### 7.2 Panel del Guardia - Secciones

#### Sección 1: Configuración de Cámaras
- **Detectar cámaras**: El sistema muestra las cámaras disponibles
- **Seleccionar cámara de entrada**: Elija la cámara para registrar entradas
- **Seleccionar cámara de salida**: Elija la cámara para registrar salidas
- **Iniciar Cámaras**: Activa las cámaras seleccionadas
- **Detener**: Desactiva las cámaras

#### Sección 2: Solicitudes Pendientes
Muestra las solicitudes de registro pendientes de aprobación.
- **Aceptar**: Aprueba al usuario y le asigna un ID
- **Denegar**: Rechaza la solicitud

#### Sección 3: Usuarios Registrados
Lista de todos los usuarios aceptados.
- Muestra: ID, Nombre, Casa, Tipo
- **Botón borrar**: Elimina al usuario y su foto

#### Sección 4: Cámaras (Video en Vivo)
- Vista previa de la cámara seleccionada
- Thumbnails de ambas cámaras
- Detección de rostros en tiempo real (rectángulos verdes)

#### Sección 5: Registros
Historial de entradas y salidas.
- Filtros por tipo (residente/visitante)
- Filtros por acción (entrada/salida)
- Filtros por número de casa

### 7.3 Flujo de Trabajo Diario

1. **Mañana**: Iniciar sesión y verificar solicitudes pendientes
2. **Durante el día**: Monitorear cámaras y registros
3. **Aprobar solicitudes**: Revisar nuevas solicitudes y aprobar/denegar
4. **Registros**: Consultar registros si necesita información

---

## 8. Sistema de Cámaras

### 8.1 Tipos de Cámara Soportadas

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| USB | Cámara conectada directamente al puerto USB | Webcam integrada laptop, USB webcam |
| IP | Cámara de seguridad en red (inalámbrica) | Cámaras WiFi, cámaras PoE |

### 8.2 Configuración de Cámaras

#### Cámaras USB:
- Conecte la cámara USB
- El sistema la detecta automáticamente
- Seleccione el índice (0, 1, 2...)

#### Cámaras IP:
- Configure la URL en `config.py`
- Formato typical: `rtsp://usuario:password@ip:puerto/stream`

### 8.3 Solución de Problemas de Cámaras

| Problema | Posible Causa | Solución |
|----------|---------------|----------|
| No detecta cámaras | Cámara ocupada por otra app | Cierre otras apps que usen la cámara |
| Video.no carga | Cámara no inicializada correctamente | Verifique que la cámara funcione en otra app |
| Error "index out of range" | Índice de cámara incorrecto | Ajuste el índice en el panel |
| Cámara lenta | Iluminación insuficiente | Mejore la iluminación del área |

---

## 9. Reconocimiento Facial - Detalle Técnico

**IMPORTANTE**: El reconocimiento facial es un **requisito obligatorio** del sistema. Sin esta funcionalidad, no es posible identificar a los usuarios registrados ni registrar entradas/salidas.

### 9.1 Métodos de Reconocimiento

#### Método 1: face_recognition (dlib) - RECOMENDADO Y PRINCIPAL
- **Ventaja**: Mayor precisión (~95-99%)
- **Precisión**: 95-99%
- **Dependencias**: face_recognition + face_recognition_models
- **Instalación**:
```cmd
pip install face_recognition
pip install git+https://github.com/ageitgey/face_recognition_models
```
- **Requisito**: Tener Git instalado y en el PATH de Windows

#### Método 2: DeepFace - ALTERNATIVA
- **Ventaja**: Se instala completamente con pip (sin Git)
- **Precisión**: ~97%
- **Dependencias**: deepface
- **Instalación**:
```cmd
pip install deepface
```

#### Método 3: OpenCV Haar Cascade - FALLBACK (Menos Preciso)
- **Uso**: Solo si face_recognition y DeepFace no están disponibles
- **Precisión**: ~60-70%
- **Dependencias**: Solo OpenCV
- **Advertencia**: No recomendado para producción debido a menor precisión

### 9.2 Cómo Funciona el Reconocimiento

El sistema debe ser capaz de:

1. **Identificar rostros**: Detectar rostros humanos en el video de la cámara
2. **Comparar rostros**: Comparar el rostro detectado con los rostros de usuarios registrados
3. **Reconocer personas**: Determinar si la persona detectada es un usuario registrado
4. **Registrar acceso**: Registrar la entrada o salida según la cámara configurada

### 9.3 Proceso de Identificación

```
┌────────────────────────────────────────────────────────────┐
│              PROCESO DE IDENTIFICACIÓN                      │
├───────────────────────────────────────��────────────────────┤
│  1. Cámara captura frame de video                          │
│       │                                                    │
│       ▼                                                    │
│  2. Detectar rostros en el frame                          │
│       │                                                    │
│       ▼                                                    │
│  3. Extraer vector facial (embedding) del rostro        │
│       │                                                    │
│       ▼                                                    │
│  4. Comparar con embeddings de usuarios registrados        │
│       │                                                    │
│       ├── Similitud >= Umbral (80%)                        │
│       │       │                                            │
│       │       └── Identificar usuario → Registrar acceso  │
│       │                                                     │
│       └── Similitud < Umbral                               │
│               │                                            │
│               └── Ignorar (no es usuario registrado)      │
└────────────────────────────────────────────────────────────┘
```

### 9.4 Recomendaciones para Mejor Detección

1. **Iluminación**:
   - Luz frontal, no contraluz
   - Evitar sombras en el rostro
   - Iluminación uniforme

2. **Posición de la Cámara**:
   - A la altura del rostro
   - Distancia recomendada: 1-2 metros
   - Ángulo recto o ligeramente diagonal

3. **Calidad de Imagen**:
   - Resolución mínima recomendada: 720p
   - Evitar cámaras muy antiguas

---

## 10. Acceso Remoto (Desde Internet)

### 10.1 Configuración

Para que usuarios accedan desde internet:

1. **IP Estática o DDNS**: Obtenga una IP estática o use un servicio como No-IP
2. **Port Forwarding**: Configure su router:
   - Puerto externo: 8080 (o el que prefiera)
   - Puerto interno: 5000
   - Protocolo: TCP
3. **Firewall**: Permita conexiones entrantes en el puerto

### 10.2 Ejemplo de Acceso

```
# Desde internet (usando IP o dominio)
http://tu-ip-publica:8080/registro
http://tu-ip-publica:8080/login
```

### 10.3 Seguridad

- **强烈建议**: Usar HTTPS en producción
- **强烈建议**: Cambiar credenciales por defecto
- **强烈建议**: Usar VPN para acceso al panel del guardia

---

## 11. Problemas Conocidos

### 11.1 Cámaras No Funcionan

**Síntomas**:
- El sistema detecta la cámara pero el video no aparece
- Error 500 en `/api/camaras/detectar`

**Posibles Causas**:
1. La cámara está siendo usada por otra aplicación
2. Driver de la cámara no instalado correctamente
3. Conflicto con el índice de cámara

**Soluciones**:
1. Cierre otras aplicaciones que usen la cámara
2. Verifique que la cámara funcione en Zoom/Teams
3. Pruebe con diferente índice de cámara
4. Reinstale los drivers de la cámara

### 11.2 Reconocimiento Facial No Funciona

**Síntomas**:
- Mensaje "face_recognition no disponible"
- Sistema no identifica usuarios registrados

**Causa 1**: Se instaló la librería pero no los modelos
**Solución 1**:
```cmd
# Necesita Git en el PATH
pip install git+https://github.com/ageitgey/face_recognition_models
```

**Causa 2**: No se puede instalar face_recognition (Git no disponible)
**Solución 2**: Usar DeepFace como alternativa
```cmd
pip install deepface
```

### 11.3 Error "obsensor_uvc_stream_channel"

**Síntomas**:
- Mensajes de error de OpenCV en la terminal

**Causa**:
- OpenCV intenta acceder a índices de cámara que no existen

**Solución**:
- Estos errores son informativos, no afectan el funcionamiento
- El sistema maneja estos errores internamente

---

## 12. Diseño Visual - Estilo Bruce Wayne

### 12.1 Paleta de Colores

| Elemento | Color | Código |
|----------|-------|--------|
| Fondo principal | Negro profundo | #0A0A0A |
| Fondo secundario | Gris muy oscuro | #141414 |
| Fondo tarjetas | Gris oscuro | #1A1A1A |
| Texto principal | Blanco | #FFFFFF |
| Texto secundario | Gris claro | #A0A0A0 |
| Acentos | Dorado sutil | #C9A962 |
| Éxito | Verde | #4ADE80 |
| Peligro | Rojo | #EF4444 |

### 12.2 Tipografía

| Elemento | Fuente |
|----------|--------|
| Títulos | Montserrat |
| Cuerpo de texto | Roboto |

### 12.3 Estilo Visual

- **Minimalista**: Elementos limpios, sin excesos
- **Elegante**: Bordes delgados, efectos sutiles
- ** Oscuro**: Fondo oscuro con acentos dorados/blancos
- **Profesional**: Apariencia de tecnología de vanguardia

---

## 13. Base de Datos

### 13.1 Estructura de Archivos

```
DB/
├── omniguard.db              # Base de datos activa
│   ├── usuarios             # Tabla de usuarios
│   ├── solicitudes          # Tabla de solicitudes
│   ├── registros_entrada_salida  # Registros de acceso
│   └── control_mes         # Control de exportación mensual
│
└── Registros_Mensuales/      # Backups mensuales
    ├── Abril_2026.db       # Registros de abril 2026
    └── Mayo_2026.db         # Registros de mayo 2026
```

### 13.2 Respaldo Manual

Para hacer un respaldo manual:
1. Copie el archivo `DB/omniguard.db`
2. Guárdelo en una ubicación segura

---

## 14. API Endpoints

| Método | Endpoint | Descripción | Requiere Auth |
|--------|----------|-------------|---------------|
| GET | `/api/camaras/detectar` | Detectar cámaras USB | Sí |
| POST | `/api/camaras/configurar` | Configurar cámaras | Sí |
| POST | `/api/camaras/detener` | Detener cámaras | Sí |
| GET | `/api/camaras/estado` | Estado de cámaras | Sí |
| GET | `/api/solicitudes` | Solicitudes pendientes | Sí |
| POST | `/api/solicitudes/{id}/aceptar` | Aceptar solicitud | Sí |
| POST | `/api/solicitudes/{id}/denegar` | Denegar solicitud | Sí |
| GET | `/api/registros` | Registros de acceso | Sí |
| GET | `/api/usuarios/activos` | Usuarios activos | Sí |
| POST | `/api/usuarios/{id}/borrar` | Eliminar usuario | Sí |
| GET | `/video_feed/{tipo}` | Stream de video | Sí |

---

## 15. Roadmap de Implementación (Secuencia para IA)

Esta sección define la secuencia recomendada para que cualquier agente de IA pueda construir el sistema OmniGuard desde cero, sin alucinaciones ni suposiciones incorrectas.

### Instrucciones Generales

- **Orden obligatorio**: Seguir las fases en orden secuencial (1 → 5)
- **Verificación requerida**: Cada fase debe probarse antes de avanzar
- **Sin saltos**: No comenzar una fase sin completar la anterior
- **Estilo de código**: Python PEP 8, Flask con rutas moderno

---

### Fase 1: Core y Base de Datos

**Objetivo**: Establecer el esqueleto del sistema con Flask y SQLite

**Archivos a crear**:
1. `config.py` - Todas las configuraciones centralizadas
2. `models.py` - Todas las funciones de base de datos

**Pasos específicos**:

1. **Crear config.py**:
   - Definir clase `Config` con todas las constantes
   - Incluir: DB_PATH, PORT, HOST, credenciales, umbrales, rutas

2. **Crear models.py**:
   - Crear función `init_db()` que asegure directorios y cree tablas
   - Crear tabla `usuarios` (id, nombre_completo, numero_casa, tipo, foto_path, fecha_registro, fecha_aceptacion, fecha_expiracion, estado, embedding)
   - Crear tabla `solicitudes` (id, usuario_id, nombre_completo, numero_casa, tipo, foto_path, estado, fecha_solicitud, revisado_por)
   - Crear tabla `registros_entrada_salida` (id, usuario_id, tipo_usuario, numero_casa, fecha_hora, tipo_accion, confianza)
   - Crear funciones CRUD: crear_solicitud, obtener_solicitudes_pendientes, aceptar_solicitud, denegar_solicitud, obtener_usuarios_aceptados, registrar_entrada_salida, obtener_registros

3. **Verificación**:
   - Ejecutar `init_db()` y verificar que `DB/omniguard.db` se cree
   - Probar funciones CRUD básico

---

### Fase 2: Motor Facial y Lógica

**Objetivo**: Implementar el sistema de reconocimiento facial

**Archivos a crear**:
1. `reconocimiento/__init__.py`
2. `reconocimiento/detector.py` - Motor de detección
3. `reconocimiento/registros.py` - Lógica de exportación mensual

**Pasos específicos**:

1. **Prioridad de implementación**:
   - **PRIMERO**: Intentar importar face_recognition (dlib)
   - **SEGUNDO**: Si falla, usar DeepFace
   - **TERCERO**: Solo como fallback, usar OpenCV Haar Cascade

2. **Crear detector.py**:
   - Crear clase `DetectorRostro`
   - Implementar método `detectar_rostro()` que intente face_recognition primero
   - Implementar método `extraer_embedding()` para obtener vector facial
   - Implementar método `comparar_rostros()` con fórmula de similitud
   - Implementar método `reconocer_usuario()` que compare embeddings
   - Implementar lógica de entrada/salida (último registro determina acción)

3. **Crear registros.py**:
   - Función para exportar registros mensuales a CSV/SQLite
   - Programar ejecución automática o manual

4. **Verificación**:
   - Cargar una foto de prueba
   - Verificar que se detecte el rostro y calculé embedding
   - Probar comparación entre dos rostros

---

### Fase 3: Desarrollo de API REST

**Objetivo**: Construir todos los endpoints de Flask

**Archivo principal**: `app.py`

**Pasos específicos**:

1. **Configuración básica Flask**:
   - Inicializar Flask app
   - Configurar secret_key y carpetas estáticas

2. **Endpoints de autenticación**:
   - `/login` (GET) - Renderizar template login.html
   - `/login` (POST) - Validar credenciales
   - `/logout` - Cerrar sesión
   - Decorador `@login_requerido` para endpoints protegidos

3. **Endpoints de cámaras**:
   - `/api/camaras/detectar` - Listar cámaras disponibles
   - `/api/camaras/configurar` - Configurar cámaras entrada/salida
   - `/api/camaras/detener` - Detener cámaras
   - `/video_feed/{tipo}` - Stream de video MJPEG

4. **Endpoints de solicitudes**:
   - `/api/solicitudes` - GET solicitudes pendientes
   - `/api/solicitudes/{id}/aceptar` - POST aceptar
   - `/api/solicitudes/{id}/denegar` - POST denegar

5. **Endpoints de usuarios**:
   - `/api/usuarios/activos` - GET usuarios aceptados
   - `/api/usuarios/{id}/borrar` - POST eliminar usuario y foto

6. **Endpoints de registros**:
   - `/api/registros` - GET registros de acceso

7. **Verificación**:
   - Probar cada endpoint con curl o Postman
   - Verificar que las respuestas sean JSON válidas

---

### Fase 4: Frontend y UI (Estilo Bruce Wayne)

**Objetivo**: Crear interfacesweb con diseño específico

**Archivos a crear**:
1. `templates/registro.html`
2. `templates/guardia.html`
3. `templates/login.html`
4. `static/css/estilos.css`

**Pasos específicos**:

1. **Crear estilos.css** ( строго paleta):
   - Fondo principal: #0A0A0A
   - Fondo secundario: #141414
   - Fondo tarjetas: #1A1A1A
   - Texto principal: #FFFFFF
   - Texto secundario: #A0A0A0
   - Acentos: #C9A962 (dorado)
   - Fuentes: Montserrat (títulos), Roboto (cuerpo)

2. **Crear registro.html**:
   - Formulario con campos: nombre, número de casa, tipo (residente/visitante)
   - Input file para subir foto
   - Diseño Bruce Wayne oscuro

3. **Crear login.html**:
   - Formulario con usuario/contraseña
   - Diseño minimalista oscuro

4. **Crear guardia.html**:
   - Sección 1: Configuración de cámaras
   - Sección 2: Solicitudes pendientes (tabla con aceptar/denegar)
   - Sección 3: Usuarios registrados (tabla con borrar)
   - Sección 4: Video en vivo (iframes o elementos video)
   - Sección 5: Registros (tabla con filtros)

5. **Verificación**:
   - Abrir cada página en navegador
   - Verificar diseño oscuro con acentos dorados
   - Probar funcionalidad de formularios

---

### Fase 5: Hardware y Panel de Control

**Objetivo**: Integrar cámaras y funcionalidad completa

**Pasos específicos**:

1. **Detección de cámaras**:
   - Implementar función para escanear índices de cámara USB
   - Soporte para cámaras IP (URL RTSP)
   - Video streaming con Flask Response/MJPEG

2. **Lógica de detección en tiempo real**:
   - Capturar frames de cámara
   - Pasarlos por el detector facial
   - Registrar entrada/salida automáticamente

3. **Panel interactivo del guardia**:
   - Auto-iniciar cámaras al abrir panel
   - Botones de iniciar/detener
   - Video en vivo con overlays de detección
   - Actualización en tiempo real (polling o WebSocket)

4. **Funcionalidades adicionales**:
   - Eliminación automática de visitantes expirados
   - Exportación mensual de registros
   - thumbers de cámaras

5. **Verificación**:
   - Probar con cámara real USB
   - Verificar streaming en navegador
   - Probar detección de rostro
   - Verificar registro de entrada/salida

---

### Resumen de Secuencia

| Fase | Componente | Archivos Clave |
|------|-----------|-----------------|
| 1 | Core + DB | config.py, models.py |
| 2 | Facial | reconocimiento/detector.py, reconocimiento/registros.py |
| 3 | API | app.py |
| 4 | UI | templates/*.html, static/css/estilos.css |
| 5 | Hardware | Cámaras + Panel Guardia |

---

## 17. Historial de Versiones

### v3.1 (26/Abril/2026) - Actual
- Sistema de dos cámaras (entrada/salida)
- Video en vivo en el panel del guardia
- Eliminación automática de visitantes expirados (1 mes)
- Eliminación de foto al borrar usuario
- Cámaras se encienden automáticamente al abrir panel
- Diseño Bruce Wayne implementado
- Thumbnail de cámaras en el panel

### v3.0 (Inicial)
- Registro de usuarios vía web
- Panel del guardia con aceptar/denegar
- Reconocimiento facial (OpenCV como fallback)
- Registros mensuales automáticos

---

## 18. Información de Contacto

| Campo | Valor |
|-------|-------|
| Sistema | OmniGuard Residential AI |
| Versión | 3.2 |
| Fecha | Abril 2026 |
| Desarrollado para | Fraccionamientos residenciales |

---

*Este documento fue creado y actualizado automáticamente para el sistema OmniGuard Residential AI.*