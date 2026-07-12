"""
Django settings for studyplatform project.
"""

from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from decouple import Config, RepositoryEnv

BASE_DIR = Path(__file__).resolve().parent.parent

# Always load backend/.env (not .env.example, not the frontend .env.local)
_env_file = BASE_DIR / '.env'
config = Config(RepositoryEnv(_env_file)) if _env_file.exists() else Config()

SECRET_KEY = config('SECRET_KEY', default='django-insecure-ew7^ibbhoh@ieel_%0c0(b!(ag5l74^e$+v^h_1^0kl)_+q=k0')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'django_filters',
    'users',
    'materials',
    'flashcards',
    'quizzes',
    'analytics',
    'ml',
    'notebooks',
    'study_sessions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'studyplatform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'studyplatform.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Gemini (get key: https://aistudio.google.com/apikey)
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
# gemini-2.0-flash free tier is often exhausted; 2.5-flash usually works on free tier
GEMINI_MODEL = config('GEMINI_MODEL', default='gemini-2.5-flash')
GEMINI_MODEL_FALLBACKS = config(
    'GEMINI_MODEL_FALLBACKS',
    default='gemini-2.5-flash-lite,gemini-2.0-flash-lite,gemini-1.5-flash',
)
USE_LOCAL_FALLBACK_ON_QUOTA = config('USE_LOCAL_FALLBACK_ON_QUOTA', default=True, cast=bool)
# When True, use local spaCy/scikit-learn pipeline first (fully offline capable).
USE_ML_PRIMARY = config('USE_ML_PRIMARY', default=False, cast=bool)
MAX_PDF_UPLOAD_MB = config('MAX_PDF_UPLOAD_MB', default=10, cast=int)

SUPABASE_URL = config('SUPABASE_URL', default=config('NEXT_PUBLIC_SUPABASE_URL', default='')).rstrip('/')

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.authentication.SupabaseJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# Comma-separated list of allowed frontend origins. Defaults to local dev;
# set CORS_ALLOWED_ORIGINS in the environment to your production origin(s).
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in config(
        'CORS_ALLOWED_ORIGINS',
        default='http://localhost:3000,http://127.0.0.1:3000',
    ).split(',')
    if origin.strip()
]

def build_database_config():
    database_url = config('DATABASE_URL', default='').strip()
    if not database_url:
        database_url = config('SUPABASE_DB_URL', default='').strip()

    use_postgres = config('USE_POSTGRES', default=False, cast=bool) or bool(database_url)

    if database_url:
        parsed = urlparse(database_url)
        if parsed.scheme not in {'postgres', 'postgresql'}:
            raise ValueError('DATABASE_URL must use a postgres:// or postgresql:// scheme')

        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        sslmode = query.get('sslmode', config('DB_SSLMODE', default='require'))
        options = {'sslmode': sslmode} if sslmode else {}

        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed.path.lstrip('/'),
            'USER': parsed.username or '',
            'PASSWORD': parsed.password or '',
            'HOST': parsed.hostname or 'localhost',
            'PORT': str(parsed.port or 5432),
            'OPTIONS': options,
        }

    if use_postgres:
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='studyflow'),
            'USER': config('DB_USER', default='studyflow_user'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {'sslmode': config('DB_SSLMODE', default='prefer')},
        }

    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }


DATABASES = {
    'default': build_database_config(),
}
