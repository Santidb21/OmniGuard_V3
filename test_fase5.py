import unittest
import os
import sys
import tempfile
import time

sys.path.insert(0, 'C:\\Users\\Santiago\\Desktop\\OmniGuard_V3')

from app import app, CONFIG_CAMARAS, CAPTURAS, CAMARAS_ACTIVAS, inicializar_sistema
from config import Config
from models import init_db, get_db_connection

class TestFase5(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-key'
        self.client = app.test_client()

        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        Config.DB_PATH = self.temp_db.name
        init_db()

        if not hasattr(app, '_detector_inicializado'):
            inicializar_sistema()

    def tearDown(self):
        CAMARAS_ACTIVAS['entrada'] = False
        CAMARAS_ACTIVAS['salida'] = False
        if CAPTURAS.get('entrada'):
            CAPTURAS['entrada'].release()
            CAPTURAS['entrada'] = None
        if CAPTURAS.get('salida'):
            CAPTURAS['salida'].release()
            CAPTURAS['salida'] = None
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_01_video_feed_entrada_no_camara(self):
        """Verifica que /video_feed/entrada responde (aunque no haya cámara)"""
        print("\n[1] Probando GET /video_feed/entrada sin cámara...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        CAMARAS_ACTIVAS['entrada'] = False
        response = self.client.get('/video_feed/entrada')
        self.assertEqual(response.status_code, 200)
        print("[OK] Endpoint /video_feed/entrada responde")

    def test_02_video_feed_salida_no_camara(self):
        """Verifica que /video_feed/salida responde (aunque no haya cámara)"""
        print("\n[2] Probando GET /video_feed/salida sin cámara...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        CAMARAS_ACTIVAS['salida'] = False
        response = self.client.get('/video_feed/salida')
        self.assertEqual(response.status_code, 200)
        print("[OK] Endpoint /video_feed/salida responde")

    def test_03_video_feed_invalid_type(self):
        """Verifica que un tipo inválido retorna 400"""
        print("\n[3] Probando GET /video_feed/tipo_invalido...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        response = self.client.get('/video_feed/tipo_invalido')
        self.assertEqual(response.status_code, 400)
        print("[OK] Tipo inválido retorna 400")

    def test_04_api_camaras_detectar(self):
        """Verifica que el endpoint de detección de cámaras funciona"""
        print("\n[4] Probando GET /api/camaras/detectar...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        response = self.client.get('/api/camaras/detectar')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('camaras', data)
        self.assertIn('config', data)
        print("[OK] Detección de cámaras funciona. Detectadas: {}".format(len(data['camaras'])))

    def test_05_api_camaras_estado(self):
        """Verifica que el endpoint de estado de cámaras funciona"""
        print("\n[5] Probando GET /api/camaras/estado...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        response = self.client.get('/api/camaras/estado')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('entrada', data)
        self.assertIn('salida', data)
        self.assertIn('detectadas', data)
        print("[OK] Estado de cámaras reporta correctamente")

    def test_06_api_camaras_configurar_sin_camara(self):
        """Verifica que configurar cámara sin hardware no causa error 500"""
        print("\n[6] Probando POST /api/camaras/configurar (sin cámara física)...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        response = self.client.post('/api/camaras/configurar',
                                    json={'entrada': 99, 'salida': 100},
                                    content_type='application/json')
        self.assertNotEqual(response.status_code, 500)
        data = response.get_json()
        self.assertIn('success', data)
        print("[OK] Configuración de cámaras no causa error 500")

    def test_07_api_camaras_detener(self):
        """Verifica que detener cámaras funciona"""
        print("\n[7] Probando POST /api/camaras/detener...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        response = self.client.post('/api/camaras/detener',
                                    json={'tipo': 'todas'},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        print("[OK] Detener cámaras funciona")

    def test_08_login_requerido_video_feed(self):
        """Verifica que /video_feed requiere autenticación"""
        print("\n[8] Probando GET /video_feed/entrada sin auth...")
        response = self.client.get('/video_feed/entrada')
        self.assertEqual(response.status_code, 302)
        print("[OK] /video_feed requiere autenticación")

    def test_09_detector_inicializado(self):
        """Verifica que el detector facial se puede inicializar"""
        print("\n[9] Verificando inicialización del detector facial...")
        from reconocimiento.detector import obtener_detector
        detector = obtener_detector()
        if detector:
            self.assertTrue(detector.inicializado or detector.inicializar())
            print("[OK] Detector facial inicializado")
        else:
            print("[WARN] Detector no disponible (opcional)")

    def test_10_registro_entrada_salida_model(self):
        """Verifica que el modelo puede registrar entradas/salidas"""
        print("\n[10] Probando registro de entrada/salida en BD...")
        from models import registrar_entrada_salida, obtener_registros
        registrar_entrada_salida('01', 'residente', '42', 'entrada', 85.5)
        registros = obtener_registros(limite=10)
        self.assertTrue(len(registros) > 0)
        self.assertEqual(registros[0]['usuario_id'], '01')
        self.assertEqual(registros[0]['tipo_accion'], 'entrada')
        print("[OK] Registro entrada/salida funciona en BD")

if __name__ == '__main__':
    print("=" * 60)
    print("  PRUEBAS DE FASE 5: HARDWARE Y PANEL DE CONTROL")
    print("=" * 60)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestFase5)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("  RESUMEN DE PRUEBAS FASE 5")
    print("=" * 60)
    print("  Pruebas ejecutadas: {}".format(result.testsRun))
    print("  Errores: {}".format(len(result.errors)))
    print("  Fallos: {}".format(len(result.failures)))

    if result.wasSuccessful():
        print("\n  [OK] FASE 5 COMPLETADA EXITOSAMENTE")
        sys.exit(0)
    else:
        print("\n  [FAIL] FASE 5 FALLO - Revisar errores arriba")
        sys.exit(1)
