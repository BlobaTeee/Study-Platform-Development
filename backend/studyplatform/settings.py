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

# Said out loud so nobody changes it by accident: the newer apps' tables use
# 32-bit keys. The older apps (analytics, flashcards, materials, quizzes,
# users) were made with 64-bit keys and say so in their AppConfig. Changing
# this line would ask for migrations that rewrite primary keys.
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

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
    'exercises',
    'live',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'studyplatform.throttling.RefundFailedGeneration',
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

# Vietnamese is the main language; English is the alternative a user picks.
LANGUAGE_CODE = 'vi'
# Spaced repetition turns on where the day boundary falls: a card due "today"
# must mean the learner's today, not UTC's. Timestamps are still stored in UTC
# (USE_TZ), so this only decides how a date is read back.
TIME_ZONE = config('TIME_ZONE', default='Asia/Ho_Chi_Minh')
USE_I18N = True
USE_TZ = True

# The API answers in the language the frontend is showing: the axios client
# sends Accept-Language from its `lang` cookie and LocaleMiddleware activates
# it. Translations live in backend/locale/<code>/LC_MESSAGES/django.po;
# `manage.py compilemessages` builds the .mo files (gitignored) at setup.
LANGUAGES = [('en', 'English'), ('vi', 'Tiếng Việt')]
LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Gemini (get key: https://aistudio.google.com/apikey)
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
# Measured on the question-quality scorecard (ml_pipeline/reports/question_quality.json):
# 3.8-flash scored 10/10 and ran fastest, 2.5-flash 14/15, 3.1-flash-lite 13/15.
# Pinned rather than 'gemini-flash-latest' so a measurement keeps meaning what it
# said. Two models only (2026-11-15): flash-latest and 2.5-flash timed out at
# 28 s on the same afternoon 3.8-flash did, so a longer chain only made the
# student wait longer. Each model has its own free daily quota (about 20).
GEMINI_MODEL = config('GEMINI_MODEL', default='gemini-3.8-flash')
GEMINI_MODEL_FALLBACKS = config('GEMINI_MODEL_FALLBACKS', default='gemini-3.1-flash-lite,gemini-3.5-flash,gemini-2.5-flash')
# The quick lane (notebooks/services/model_lane.py): short judgements the
# student waits on go to this model first, with the main one as fallback.
# Measured on one grading prompt: flash-lite answered in 3.1 s with no thinking
# but marked a right sentence wrong; with 'low' it took 6.2 s and was right.
GEMINI_FAST_MODEL = config('GEMINI_FAST_MODEL', default='gemini-3.1-flash-lite')
GEMINI_FAST_THINKING = config('GEMINI_FAST_THINKING', default='low')
# A quick-lane model gets this long before the other one is asked.
GEMINI_FAST_TIMEOUT_SECONDS = config('GEMINI_FAST_TIMEOUT_SECONDS', default=12, cast=int)
# Reading a photo or a many-page file is one long answer: it gets this long.
# An 18-page exam with its figure boxes took 84 s on 2026-11-23, so 90 was too close.
GEMINI_READ_TIMEOUT_SECONDS = config('GEMINI_READ_TIMEOUT_SECONDS', default=150, cast=int)
GEMINI_READ_THINKING = config('GEMINI_READ_THINKING', default='low')
# How many excerpts may be generated at once. Each excerpt is one provider call
# of several seconds and they are independent, so running them together is the
# single biggest latency win; the cap exists because firing all of them at once
# is the quickest way to collect a rate-limit error.
GENERATE_CONCURRENCY = config('GENERATE_CONCURRENCY', default=3, cast=int)
# Requests one deck or quiz may use. The free tier gives a model 20 requests
# a day, so the passages go in one request by default; raise it where quota
# is plentiful and parallel answers (a few seconds faster) are worth more.
GENERATE_CALLS = config('GENERATE_CALLS', default=1, cast=int)
# The most items one request asks for. A request for 32 quiz questions timed
# out on every model; about a dozen answers well inside the deadline. A
# bigger batch is split into parallel requests of this size.
GENERATE_PER_REQUEST = config('GENERATE_PER_REQUEST', default=12, cast=int)

# Concept names and forgotten-card groupings are kept for a day so a reload
# costs no AI request. In memory they were lost every time the dev server
# reloaded, which is every code change; a file survives that. Tests keep an
# in-memory cache, since they clear it between tests and must not clear the
# running server's.
import sys as _sys
if 'pytest' in _sys.modules:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
else:
    CACHES = {'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': config('CACHE_DIR', default=str(BASE_DIR / '.cache' / 'django')),
    }}

# Một ngày học có giới hạn. Nghỉ hai tuần là có hàng trăm thẻ đến hạn, và hiện
# nguyên con số đó là lúc người học bỏ cuộc. Phần không vừa trong ngày vẫn đến
# hạn và đứng đầu hàng ngày mai. Thẻ mới chờ trong lúc còn nợ nhiều hơn phần
# của hôm nay, vì mỗi thẻ học hôm nay là một lần ôn nợ ngày mai.
DAILY_REVIEW_LIMIT = config('DAILY_REVIEW_LIMIT', default=40, cast=int)
DAILY_NEW_LIMIT = config('DAILY_NEW_LIMIT', default=10, cast=int)

# How long one model may take before the work is handed to the next model in
# GEMINI_MODEL_FALLBACKS. A busy model does not answer with an error — it just
# stops answering, and without a deadline the student waits with it.
GEMINI_TIMEOUT_SECONDS = config('GEMINI_TIMEOUT_SECONDS', default=30, cast=int)
# How much the model may think before answering: 'default' leaves it to the
# model, 'off' forbids it, 'low'/'high' set a level on the models that take one.
# Measured on one excerpt, thinking was 2.089 tokens against 765 of answer on
# gemini-2.5-flash — over half the spend. Older models reject the setting and
# are retried without it, so changing this cannot break the fallback chain.
GEMINI_THINKING = config('GEMINI_THINKING', default='default')
# Sau khi một model quá tải hoặc hết hạn chờ, bỏ qua nó trong bao lâu. Mỗi model
# không trả lời tốn trọn một deadline trước khi nhường, nên nhớ lại trong ít phút
# giúp những lượt sinh sau không phải trả lại cái giá đó. Nếu cả chuỗi đang bị bỏ
# qua thì model đầu vẫn được thử, vì thà chờ còn hơn báo lỗi khi nó có thể đã hồi.
# 15 phút: một model quá tải thường quá tải cả buổi, như chiều 2026-11-15.
GEMINI_COOLDOWN_SECONDS = config('GEMINI_COOLDOWN_SECONDS', default=900, cast=int)

USE_LOCAL_FALLBACK_ON_QUOTA = config('USE_LOCAL_FALLBACK_ON_QUOTA', default=True, cast=bool)
# When True, use local spaCy/scikit-learn pipeline first (fully offline capable).
USE_ML_PRIMARY = config('USE_ML_PRIMARY', default=False, cast=bool)
MAX_PDF_UPLOAD_MB = config('MAX_PDF_UPLOAD_MB', default=10, cast=int)
# LibreOffice draws a Word file into a PDF before the AI reads it (exercises/services/photo.py);
# empty finds `soffice` on PATH, and without it the file is read as text.
SOFFICE_PATH = config('SOFFICE_PATH', default='')

# AI provider for generation: 'gemini' (cloud), 'ollama' (local generative LLM),
# or 'custom'. For a fully local generative setup: AI_PROVIDER=ollama and
# USE_ML_PRIMARY=False (the extractive ML remains the offline fallback).
AI_PROVIDER = config('AI_PROVIDER', default='gemini')
OLLAMA_BASE_URL = config('OLLAMA_BASE_URL', default='http://localhost:11434')
OLLAMA_MODEL = config('OLLAMA_MODEL', default='llama3.2:3b')
OLLAMA_TIMEOUT = config('OLLAMA_TIMEOUT', default=120, cast=int)
# Document excerpts generated from per request. More = better coverage and more
# reliable small-model output, but one model call each (the main latency cost).
RAG_CHUNKS = config('RAG_CHUNKS', default=3, cast=int)

SUPABASE_URL = config('SUPABASE_URL', default=config('NEXT_PUBLIC_SUPABASE_URL', default='')).rstrip('/')
# Server-only. Lets the backend remove a Supabase auth user when the student
# deletes their account; without it only the local data is removed.
SUPABASE_SERVICE_ROLE_KEY = config('SUPABASE_SERVICE_ROLE_KEY', default='')

# --- Email (planned-test reminders) ---
# Real SMTP. The credential must be a provider *app password*, never an account
# password, and lives in backend/.env, which is gitignored. With EMAIL_HOST
# unset the console backend is used instead, so a developer without credentials
# still sees exactly what would have been sent rather than hitting an error.
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL',
                            default='StudyFlow <no-reply@studyflow.local>')
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default=('django.core.mail.backends.smtp.EmailBackend' if EMAIL_HOST
             else 'django.core.mail.backends.console.EmailBackend'),
)

# Where a reminder tells the student to go to sit their test.
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000').rstrip('/')

def _rate_or_none(rate: str):
    """A DRF rate, or None (no limit) for 'off'."""
    return None if rate.strip().lower() in ('', 'off', 'none') else rate.strip()


REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'users.authentication.SupabaseJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Blanket per-user ceiling for the cheap endpoints. The expensive ones
    # (anything that generates content) opt into the tighter `generate` scope
    # via studyplatform.throttling.GenerationRateThrottle. Anonymous requests
    # are already refused by IsAuthenticated before throttling runs.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': config('THROTTLE_USER', default='60/min'),
        # 'off' lifts it (a demo should not run out mid-way); 30/hour once deployed.
        'generate': _rate_or_none(config('THROTTLE_GENERATE', default='30/hour')),
    },
    'EXCEPTION_HANDLER': 'studyplatform.throttling.exception_handler',
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
