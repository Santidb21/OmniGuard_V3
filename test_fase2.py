import sys
import os
import traceback

print("=" * 60)
print("  PRUEBAS DE FASE 2: MOTOR FACIAL Y LÓGICA")
print("=" * 60)

def test_imports():
    """Prueba que todos los módulos se importen sin errores"""
    print("\n[1] Verificando imports de Fase 2...")
    
    try:
        from reconocimiento import detector, DetectorRostro, iniciar_deteccion, obtener_detector
        print("[OK] reconocimiento/__init__.py - Imports exitosos")
    except Exception as e:
        print("[ERROR] Error importando desde __init__.py: {}".format(e))
        traceback.print_exc()
        return False
    
    try:
        from reconocimiento.detector import detector as det, DetectorRostro as DR
        print("[OK] reconocimiento/detector.py - Imports exitosos")
    except Exception as e:
        print("[ERROR] Error importando detector.py: {}".format(e))
        traceback.print_exc()
        return False
    
    try:
        from reconocimiento.registros import (exportar_registros_mensuales, 
                                           verificar_cambio_mes, 
                                           listar_archivos_mensuales,
                                           obtener_registros_mes,
                                           limpiar_registros_viejos)
        print("[OK] reconocimiento/registros.py - Imports exitosos")
    except Exception as e:
        print("[ERROR] Error importando registros.py: {}".format(e))
        traceback.print_exc()
        return False
    
    return True

def test_detector_init():
    """Prueba la inicialización del detector (sin activar cámaras)"""
    print("\n[2] Verificando inicialización del detector...")
    
    try:
        from reconocimiento.detector import detector
        
        # Verificar que el objeto detector existe
        if detector is None:
            print("[ERROR] El detector es None")
            return False
        
        print("[OK] Objeto detector creado correctamente")
        
        # Verificar atributos básicos
        if not hasattr(detector, 'inicializado'):
            print("[ERROR] El detector no tiene atributo 'inicializado'")
            return False
        
        if not hasattr(detector, 'face_cascade'):
            print("[ERROR] El detector no tiene atributo 'face_cascade'")
            return False
            
        print("[OK] Atributos del detector verificados")
        return True
        
    except Exception as e:
        print("[ERROR] Error verificando detector: {}".format(e))
        traceback.print_exc()
        return False

def test_registros_funcs():
    """Prueba las funciones de registros mensuales"""
    print("\n[3] Verificando funciones de registros...")
    
    try:
        from reconocimiento.registros import (verificar_cambio_mes, 
                                           listar_archivos_mensuales)
        
        # Probar verificar_cambio_mes
        mes = verificar_cambio_mes()
        if mes is None:
            print("[WARN] verificar_cambio_mes devolvió None")
        else:
            print("[OK] verificar_cambio_mes: {}".format(mes))
        
        # Probar listar_archivos_mensuales
        archivos = listar_archivos_mensuales()
        print("[OK] listar_archivos_mensuales: {} archivos".format(len(archivos)))
        
        return True
        
    except Exception as e:
        print("[ERROR] Error en funciones de registros: {}".format(e))
        traceback.print_exc()
        return False

def test_syntax():
    """Verifica que no haya errores de sintaxis en los archivos"""
    print("\n[4] Verificando sintaxis Python...")
    
    archivos = [
        'reconocimiento/__init__.py',
        'reconocimiento/detector.py',
        'reconocimiento/registros.py'
    ]
    
    import py_compile
    
    for archivo in archivos:
        try:
            py_compile.compile(archivo, doraise=True)
            print("[OK] {} - Sin errores de sintaxis".format(archivo))
        except py_compile.PyCompileError as e:
            print("[ERROR] Error de sintaxis en {}: {}".format(archivo, e))
            return False
    
    return True

def test_config_integration():
    """Verifica que los módulos usen Config correctamente"""
    print("\n[5] Verificando integración con Config...")
    
    try:
        from config import Config
        
        # Verificar que Config tiene los atributos necesarios
        attrs = ['CONFIDENCE_THRESHOLD', 'TIEMPO_SALIDA_MINUTOS', 
                 'DB_PATH', 'REGISTROS_PATH']
        
        for attr in attrs:
            if not hasattr(Config, attr):
                print("[ERROR] Config no tiene el atributo '{}'".format(attr))
                return False
        
        print("[OK] Config verificado con todos los atributos necesarios")
        return True
        
    except Exception as e:
        print("[ERROR] Error verificando Config: {}".format(e))
        traceback.print_exc()
        return False

if __name__ == '__main__':
    resultados = []
    
    resultados.append(("[1] Imports", test_imports()))
    resultados.append(("[2] Detector", test_detector_init()))
    resultados.append(("[3] Registros", test_registros_funcs()))
    resultados.append(("[4] Sintaxis", test_syntax()))
    resultados.append(("[5] Config", test_config_integration()))
    
    print("\n" + "=" * 60)
    print("  RESUMEN DE PRUEBAS")
    print("=" * 60)
    
    exitos = 0
    for nombre, resultado in resultados:
        estado = "[OK]" if resultado else "[FAIL]"
        print("  {} {}".format(estado, nombre))
        if resultado:
            exitos += 1
    
    print("\n  Resultado: {}/{} pruebas exitosas".format(exitos, len(resultados)))
    
    if exitos == len(resultados):
        print("\n  [OK] FASE 2 COMPLETADA EXITOSAMENTE")
        sys.exit(0)
    else:
        print("\n  [FAIL] FASE 2 FALLÓ - Revisar errores arriba")
        sys.exit(1)
