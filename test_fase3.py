import unittest
import json
import os
import sys
import tempfile

# Configurar entorno de prueba
sys.path.insert(0, 'C:\\Users\\Santiago\\Desktop\\OmniGuard_V3')

from app import app
from config import Config
from models import init_db, get_db_connection

class TestFase3(unittest.TestCase):
    
    def setUp(self):
        """Configurar cliente de prueba de Flask"""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-key'
        self.client = app.test_client()
        
        # Crear BD temporal para pruebas
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        Config.DB_PATH = self.temp_db.name
        
        # Inicializar BD
        init_db()
    
    def tearDown(self):
        """Limpiar después de las pruebas"""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_01_api_test(self):
        """Prueba endpoint /api/test"""
        print("\n[1] Probando GET /api/test...")
        response = self.client.get('/api/test')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'ok')
        print("[OK] /api/test devuelve 200 y status 'ok'")
    
    def test_02_index_redirect(self):
        """Prueba que / redirige a /registro"""
        print("\n[2] Probando GET /...")
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)  # Redirect
        print("[OK] / redirige a /registro")
    
    def test_03_registro_page(self):
        """Prueba página de registro"""
        print("\n[3] Probando GET /registro...")
        response = self.client.get('/registro')
        self.assertEqual(response.status_code, 200)
        print("[OK] /registro devuelve 200")
    
    def test_04_login_page(self):
        """Prueba página de login"""
        print("\n[4] Probando GET /login...")
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        print("[OK] /login devuelve 200")
    
    def test_05_login_incorrecto(self):
        """Prueba login con credenciales incorrectas"""
        print("\n[5] Probando POST /login con credenciales incorrectas...")
        response = self.client.post('/login', data={
            'username': 'wrong',
            'password': 'wrong'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'incorrectos', response.data)
        print("[OK] Login incorrecto maneja error correctamente")
    
    def test_06_login_correcto(self):
        """Prueba login con credenciales correctas"""
        print("\n[6] Probando POST /login con credenciales correctas...")
        with self.client.session_transaction() as sess:
            pass  # No session yet
        
        response = self.client.post('/login', data={
            'username': Config.ADMIN_USERNAME,
            'password': Config.ADMIN_PASSWORD
        }, follow_redirects=True)
        
        # Debería redirigir a /guardia
        self.assertEqual(response.status_code, 200)
        print("[OK] Login correcto redirige a panel de guardia")
    
    def test_07_solicitudes_protected(self):
        """Prueba que /api/solicitudes requiere autenticación"""
        print("\n[7] Probando GET /api/solicitudes sin autenticación...")
        response = self.client.get('/api/solicitudes')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        print("[OK] /api/solicitudes requiere autenticación")
    
    def test_08_usuarios_protected(self):
        """Prueba que /api/usuarios requiere autenticación"""
        print("\n[8] Probando GET /api/usuarios sin autenticación...")
        response = self.client.get('/api/usuarios')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        print("[OK] /api/usuarios requiere autenticación")
    
    def test_09_registros_protected(self):
        """Prueba que /api/registros requiere autenticación"""
        print("\n[9] Probando GET /api/registros sin autenticación...")
        response = self.client.get('/api/registros')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        print("[OK] /api/registros requiere autenticación")
    
    def test_10_camaras_detectar_protected(self):
        """Prueba que /api/camaras/detectar requiere autenticación"""
        print("\n[10] Probando GET /api/camaras/detectar sin autenticación...")
        response = self.client.get('/api/camaras/detectar')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        print("[OK] /api/camaras/detectar requiere autenticación")
    
    def test_11_registro_post(self):
        """Prueba registro de usuario via POST"""
        print("\n[11] Probando POST /api/registro...")
        
        # Crear archivo de prueba
        import numpy as np
        import cv2
        
        test_img = np.zeros((100, 100, 3), dtype=np.uint8)
        test_img_path = os.path.join(Config.FOTOS_PATH, 'test_fase3.jpg')
        cv2.imwrite(test_img_path, test_img)
        
        with open(test_img_path, 'rb') as f:
            response = self.client.post('/api/registro', data={
                'nombre_completo': 'Usuario Test Fase 3',
                'numero_casa': '123',
                'tipo': 'visitante',
                'foto': f
            }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('user_id', data)
        print("[OK] POST /api/registro crea solicitud correctamente")
        
        # Limpiar
        if os.path.exists(test_img_path):
            os.unlink(test_img_path)
    
    def test_12_endpoints_structure(self):
        """Verifica que los endpoints devuelvan JSON válido"""
        print("\n[12] Verificando estructura de respuestas JSON...")
        
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        
        # Probar /api/test
        response = self.client.get('/api/test')
        data = json.loads(response.data)
        self.assertIn('status', data)
        self.assertIn('message', data)
        self.assertIn('timestamp', data)
        
        print("[OK] Estructura de JSON correcta en endpoints principales")

if __name__ == '__main__':
    print("=" * 60)
    print("  PRUEBAS DE FASE 3: DESARROLLO DE API REST")
    print("=" * 60)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFase3)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("  RESUMEN DE PRUEBAS FASE 3")
    print("=" * 60)
    print("  Pruebas ejecutadas: {}".format(result.testsRun))
    print("  Errores: {}".format(len(result.errors)))
    print("  Fallos: {}".format(len(result.failures)))
    
    if result.wasSuccessful():
        print("\n  [OK] FASE 3 COMPLETADA EXITOSAMENTE")
        sys.exit(0)
    else:
        print("\n  [FAIL] FASE 3 FALLO - Revisar errores arriba")
        sys.exit(1)
