import unittest
import os
import sys
import tempfile

sys.path.insert(0, 'C:\\Users\\Santiago\\Desktop\\OmniGuard_V3')

from app import app
from config import Config
from models import init_db, get_db_connection

class TestFase4(unittest.TestCase):
    
    def setUp(self):
        """Configurar cliente de prueba"""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-key'
        self.client = app.test_client()
        
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        Config.DB_PATH = self.temp_db.name
        init_db()
    
    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_01_registro_page(self):
        """Verifica que /registro renderiza correctamente"""
        print("\n[1] Probando GET /registro...")
        response = self.client.get('/registro')
        self.assertEqual(response.status_code, 200)
        data = response.data.decode('utf-8')
        self.assertIn('Registro de Usuario', data)
        self.assertIn('OMNI', data)  # Parte del logo dividido
        self.assertIn('GUARD', data)  # Parte del logo dividido
        print("[OK] /registro renderiza HTML correcto")
    
    def test_02_login_page(self):
        """Verifica que /login renderiza correctamente"""
        print("\n[2] Probando GET /login...")
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        data = response.data.decode('utf-8')
        self.assertIn('Iniciar Sesión', data)
        self.assertIn('OMNI', data)  # Parte del logo
        self.assertIn('GUARD', data)  # Parte del logo
        print("[OK] /login renderiza HTML correcto")
    
    def test_03_guardia_page_requires_auth(self):
        """Verifica que /guardia requiere autenticación"""
        print("\n[3] Probando GET /guardia sin auth...")
        response = self.client.get('/guardia')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        print("[OK] /guardia requiere autenticación")
    
    def test_04_guardia_page_with_auth(self):
        """Verifica que /guardia renderiza con auth"""
        print("\n[4] Probando GET /guardia con auth...")
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        
        response = self.client.get('/guardia')
        self.assertEqual(response.status_code, 200)
        data = response.data.decode('utf-8')
        self.assertIn('OMNI', data)  # Parte del logo
        self.assertIn('GUARD', data)  # Parte del logo
        self.assertIn('Panel', data)
        print("[OK] /guardia renderiza HTML correcto con auth")
    
    def test_05_static_css(self):
        """Verifica que el CSS se sirve correctamente"""
        print("\n[5] Probando GET /static/css/estilos.css...")
        response = self.client.get('/static/css/estilos.css')
        self.assertEqual(response.status_code, 200)
        data = response.data.decode('utf-8')
        # CSS file uses lowercase hex codes
        self.assertIn('#0a0a0a', data.lower())  # bg-primary in lowercase
        self.assertIn('#c9a962', data.lower())  # accent-gold in lowercase
        self.assertIn('font-family:', data)
        print("[OK] CSS se sirve con paleta Bruce Wayne")
    
    def test_06_jinja2_syntax(self):
        """Verifica que no hay errores de sintaxis en templates"""
        print("\n[6] Verificando sintaxis Jinja2 en templates...")
        
        templates = ['registro.html', 'login.html', 'guardia.html']
        for template in templates:
            try:
                with self.client.session_transaction() as sess:
                    sess['usuario'] = Config.ADMIN_USERNAME
                
                if template == 'registro.html':
                    response = self.client.get('/registro')
                elif template == 'login.html':
                    response = self.client.get('/login')
                else:
                    response = self.client.get('/guardia')
                
                self.assertEqual(response.status_code, 200)
                print("  [OK] {} - Sin errores Jinja2".format(template))
            except Exception as e:
                self.fail("Error en {}: {}".format(template, str(e)))
        
        print("[OK] Todos los templates sin errores de sintaxis")
    
    def test_07_branding_bruce_wayne(self):
        """Verifica elementos de diseño Bruce Wayne en templates"""
        print("\n[7] Verificando diseño Bruce Wayne...")
        
        with self.client.session_transaction() as sess:
            sess['usuario'] = Config.ADMIN_USERNAME
        
        # Verificar que el CSS está linkeado en el HTML
        response = self.client.get('/guardia')
        data = response.data.decode('utf-8')
        self.assertIn('estilos.css', data)  # CSS linkeado
        self.assertIn('OMNI', data)  # Logo parte 1
        self.assertIn('GUARD', data)  # Logo parte 2
        
        # Verificar que el CSS tiene la paleta correcta
        response_css = self.client.get('/static/css/estilos.css')
        css_data = response_css.data.decode('utf-8')
        self.assertIn('--bg-primary', css_data)  # Variable CSS
        self.assertIn('--accent:', css_data)  # Variable CSS  
        self.assertIn('Montserrat', css_data)  # Fuente título
        self.assertIn('Roboto', css_data)  # Fuente cuerpo
        self.assertIn('#0a0a0a', css_data)  # Color dark
        self.assertIn('#c9a962', css_data)  # Dorado
        
        print("[OK] Diseño Bruce Wayne presente en templates")
    
    def test_08_login_error_display(self):
        """Verifica que errores de login se muestran"""
        print("\n[8] Probando visualización de errores en login...")
        response = self.client.post('/login', data={
            'username': 'wrong',
            'password': 'wrong'
        }, follow_redirects=True)
        
        data = response.data.decode('utf-8')
        self.assertIn('incorrectos', data.lower())
        print("[OK] Errores de login se muestran correctamente")

if __name__ == '__main__':
    print("=" * 60)
    print("  PRUEBAS DE FASE 4: FRONTEND Y UI (BRUCE WAYNE)")
    print("=" * 60)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFase4)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("  RESUMEN DE PRUEBAS FASE 4")
    print("=" * 60)
    print("  Pruebas ejecutadas: {}".format(result.testsRun))
    print("  Errores: {}".format(len(result.errors)))
    print("  Fallos: {}".format(len(result.failures)))
    
    if result.wasSuccessful():
        print("\n  [OK] FASE 4 COMPLETADA EXITOSAMENTE")
        sys.exit(0)
    else:
        print("\n  [FAIL] FASE 4 FALLO - Revisar errores arriba")
        sys.exit(1)
