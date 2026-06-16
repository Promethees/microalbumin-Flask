import os
from datetime import timedelta
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
    # NOTE: Google merges previously-granted scopes (from social sign-in:
    # openid/email/profile) into the Drive token response because both flows
    # share one OAuth client + include_granted_scopes=true. oauthlib aborts
    # with "Scope has changed" unless the requested list matches what's
    # returned, so the identity scopes must be listed here too.
    GOOGLE_SCOPES = [
        'https://www.googleapis.com/auth/drive',  # Full Drive access
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
        'openid',
    ]
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:5003/auth/google/callback')
    
    # OAuth — Social sign-in (Google & GitHub)
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '')
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '')
    GITHUB_OAUTH_CLIENT_ID = os.environ.get('GITHUB_OAUTH_CLIENT_ID', '')
    GITHUB_OAUTH_CLIENT_SECRET = os.environ.get('GITHUB_OAUTH_CLIENT_SECRET', '')

    # AI Assistant (Groq)
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
    AI_MODEL = os.environ.get('AI_MODEL', 'llama-3.1-8b-instant')

    # Account / download auth
    # SQLite by default; set DATABASE_URL to a PostgreSQL URL in production.
    # Render provides postgres:// URLs — rewrite to postgresql:// for SQLAlchemy.
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///accounts.db')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SMTP settings (e.g. Gmail app password)
    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USER = os.environ.get('SMTP_USER', '')
    SMTP_PASS = os.environ.get('SMTP_PASS', '')

    # Public base URL of this service (used in verification emails)
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5003')

    # GitHub details for proxying the source tarball to authenticated users
    GITHUB_PAT  = os.environ.get('GITHUB_PAT', os.environ.get('GITHUB_TOKEN', ''))
    GITHUB_OWNER = os.environ.get('GITHUB_OWNER', 'Promethees')
    GITHUB_REPO  = os.environ.get('GITHUB_REPO', 'microalbumin-Flask')

    # Persistent login session lifetime (30 days)
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    # Auto-logout after the EasyOKAPI tab has been left unopened (hidden/closed)
    # for this long. Enforced server-side in main.enforce_account_idle_timeout
    # and mirrored client-side in templates/index.html.
    ACCOUNT_IDLE_TIMEOUT = timedelta(minutes=60)

    # Automatic Production Detection (Heroku uses 'DYNO', generic servers often use 'PORT')
    _prod_env = os.environ.get('PRODUCTION_MODE')
    if _prod_env is not None:
        PRODUCTION_MODE = _prod_env.lower() == 'true'
    else:
        # Default to True if on Heroku or generic server, otherwise False
        PRODUCTION_MODE = any(os.environ.get(k) for k in ['DYNO', 'PORT', 'HEROKU_APP_NAME'])