import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'rental-system-super-secret-key-change-in-prod-2026')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "instance", "rental_management.db")}'
    )
    
    # Session security
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # File upload configurations
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'csv', 'xlsx'}
    
    # Default Currency & Localization
    DEFAULT_CURRENCY = 'KES'
    DEFAULT_DATE_FORMAT = '%d/%m/%Y'
    
    # Daraja M-Pesa Defaults (overridden by DB settings)
    MPESA_ENV = os.environ.get('MPESA_ENV', 'sandbox')

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

