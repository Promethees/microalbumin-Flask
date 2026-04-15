import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-in-production'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    DOWNLOAD_FOLDER = 'downloads'
    CLEANUP_DATA_FILE = 'cleanup_data.json'
    
    # Cleanup settings
    CLEANUP_DELAY = 300  # 5 minutes in seconds
    WARNING_THRESHOLD = 60  # Warn 1 minute before cleanup
    ALLOWED_EXTENSIONS = {'txt', 'docx', 'html', 'md', 'rtf'}
    
    # Google Drive API
    GOOGLE_CREDENTIALS_FILE = 'credentials.enc'  # Encrypted version
    GOOGLE_ENCRYPTION_KEY = os.environ.get('GOOGLE_ENCRYPTION_KEY')  # Required in env
    GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive']  # Full Drive access
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5003/auth/google/callback')
    
    PRODUCTION_MODE = os.environ.get('PRODUCTION_MODE', 'False').lower() == 'true'