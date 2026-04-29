import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'omniguard-secret-key-2026')
    
    DB_PATH = os.path.join(BASE_DIR, 'DB', 'omniguard.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    CAMERA_TYPE = os.environ.get('CAMERA_TYPE', 'usb')
    CAMERA_INDEX = int(os.environ.get('CAMERA_INDEX', 0))
    CAMERA_URL = os.environ.get('CAMERA_URL', '')
    
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'guardia')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
    
    CONFIDENCE_THRESHOLD = float(os.environ.get('CONFIDENCE_THRESHOLD', 0.78))
    RECOGNITION_MARGIN = float(os.environ.get('RECOGNITION_MARGIN', 0.08))
    RECOGNITION_CONFIRM_FRAMES = int(os.environ.get('RECOGNITION_CONFIRM_FRAMES', 3))
    RECOGNITION_CONFIRM_WINDOW = float(os.environ.get('RECOGNITION_CONFIRM_WINDOW', 2.0))
    DETECTION_INTERVAL = float(os.environ.get('DETECTION_INTERVAL', 2.0))
    
    FOTOS_PATH = os.path.join(BASE_DIR, 'static', 'fotos')
    REGISTROS_PATH = os.path.join(BASE_DIR, 'DB', 'Registros_Mensuales')
    LOGS_PATH = os.path.join(BASE_DIR, 'logs')
    
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'fotos')
    
    TIEMPO_SALIDA_MINUTOS = 30

class DevelopmentConfig(Config):
    DEBUG = False

class ProductionConfig(Config):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
