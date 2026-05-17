import os
from datetime import timedelta

class Config:
    """Base configuration class."""
    
    # Secret key for session management
    SECRET_KEY = os.environ.get('SESSION_SECRET') or 'dev-secret-key-change-in-production'
    
    # Database configuration - defaults to SQLite for simplicity
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///blog.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Admin credentials - should be set via environment variables in production
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    
    # File upload configuration
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB limit for file uploads

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    FLASK_ENV = 'development'

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    FLASK_ENV = 'production'
    
    # Force HTTPS in production (PythonAnywhere supports this)
    PREFERRED_URL_SCHEME = 'https'
    
    # Security headers
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    def __init__(self):
        # Ensure SECRET_KEY is set in production
        if not os.environ.get('SESSION_SECRET'):
            raise ValueError("SESSION_SECRET environment variable must be set for production!")
        self.SECRET_KEY = os.environ['SESSION_SECRET']
        
        # Ensure admin password hash is set in production
        if not os.environ.get('ADMIN_PASSWORD_HASH'):
            raise ValueError("ADMIN_PASSWORD_HASH environment variable must be set for production!")
        self.ADMIN_PASSWORD_HASH = os.environ['ADMIN_PASSWORD_HASH']
        
        # Admin username is required
        if not os.environ.get('ADMIN_USERNAME'):
            raise ValueError("ADMIN_USERNAME environment variable must be set for production!")
        self.ADMIN_USERNAME = os.environ['ADMIN_USERNAME']

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}