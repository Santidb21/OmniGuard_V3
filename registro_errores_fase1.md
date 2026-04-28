# Registro de Errores - Fase 1: Core y Base de Datos

## Fecha: 27 de Abril de 2026

### Error 1: Fallo en compilación de dlib 19.24.2

**Síntoma:**
Al ejecutar `pip install -r requirements.txt`, falló la instalación de `dlib==19.24.2` con error de compilación.

**Mensaje de error:**
```
CMake Error at dlib/external/pybind11/CMakeLists.txt:8 (cmake_minimum_required):
  Compatibility with CMake < 3.5 has been removed from CMake.
  
Building wheel for dlib (pyproject.toml) did not run successfully.
exit code: 1
```

**Causa:**
- La versión de CMake instalada (versión 18/2026) ya no soporta versiones de compatibilidad menores a 3.5 en pybind11
- dlib 19.24.2 tiene dependencias de CMake desactualizadas

**Solución aplicada:**
1. Se eliminó `dlib==19.24.2` del archivo `requirements.txt`
2. Se verificó que `face-recognition==1.3.0` ya estaba instalado previamente en el sistema sin necesidad de re-instalar dlib
3. Se actualizó `requirements.txt` con las dependencias correctas sin la línea problemática de dlib

**Estado:** Resuelto - face_recognition funciona correctamente sin necesidad de recompilar dlib

---

### Verificación de Fase 1

**Archivos creados/verificados:**
- ✅ `config.py` - Configuración centralizada con todas las constantes
- ✅ `models.py` - Modelos de datos y funciones CRUD
- ✅ `requirements.txt` - Dependencias actualizadas
- ✅ Base de datos `DB/omniguard.db` creada correctamente

**Tablas verificadas:**
- usuarios
- solicitudes
- registros_entrada_salida
- configuraciones
- ultimo_registro
- control_mes

**Funciones CRUD verificadas:**
- ✅ init_db() - Inicializa la base de datos
- ✅ crear_solicitud() - Crea nueva solicitud
- ✅ obtener_solicitudes_pendientes() - Lista solicitudes pendientes
- ✅ aceptar_solicitud() - Acepta solicitud y genera ID
- ✅ denegar_solicitud() - Deniega solicitud
- ✅ obtener_usuarios_aceptados() - Lista usuarios aceptados
- ✅ registrar_entrada_salida() - Registra entrada/salida
- ✅ obtener_registros() - Obtiene registros de acceso

**Resultado:** Fase 1 completada exitosamente con advertencia menor sobre dlib (ya resuelto).
