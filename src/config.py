import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-in-production'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    DOWNLOAD_FOLDER = 'downloads'
    CLEANUP_DATA_FILE = 'cleanup_data.json'
    
    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL')
    
    # Cleanup settings
    CLEANUP_DELAY = 300  # 5 minutes in seconds
    WARNING_THRESHOLD = 60  # Warn 1 minute before cleanup
    ALLOWED_EXTENSIONS = {'txt', 'docx', 'html', 'md', 'rtf'}
    
    # Google Drive API
    GOOGLE_CREDENTIALS_FILE = 'credentials.enc'  # Encrypted version
    GOOGLE_ENCRYPTION_KEY = os.environ.get('GOOGLE_ENCRYPTION_KEY')  # Required in env
    GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive']  # Full Drive access
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5003/auth/google/callback')
    
    # AI Assistant (Groq)
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    AI_MODEL = os.environ.get('AI_MODEL', 'llama-3.1-8b-instant')

    # Automatic Production Detection (Heroku uses 'DYNO', generic servers often use 'PORT')
    _prod_env = os.environ.get('PRODUCTION_MODE')
    if _prod_env is not None:
        PRODUCTION_MODE = _prod_env.lower() == 'true'
    else:
        # Default to True if on Heroku or generic server, otherwise False
        PRODUCTION_MODE = any(os.environ.get(k) for k in ['DYNO', 'PORT', 'HEROKU_APP_NAME'])