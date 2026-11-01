"""
Django settings for SmartDispatch project.
Modernized for Django 5.1 / Python 3.13
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'z59pg9@9huqluf!9#p9qrh@-y0!s+c)kn^-6%ory@$6)wd@uqr'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'datadrivendispatch.com', 'smartdispatch.westus.cloudapp.azure.com']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_sb_admin',
    'map.apps.MapConfig',   # use MapConfig so APScheduler auto-starts
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'test.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # APP_DIRS=True causes Django to look for templates in <app>/templates/
        # No hardcoded machine-specific paths.
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'test.wsgi.application'

# Database - SQLite for local development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'  # IST for Chandigarh
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'

# Default primary key field type (Django 3.2+ requires this)
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Google Maps API Key — set via environment variable before running.
# PowerShell:  $env:GGL_API_KEY="your_key_here"
# CMD:         set GGL_API_KEY=your_key_here
GGL_API_KEY = os.environ.get('GGL_API_KEY', '')

# -----------------------------------------------------------------------
# Celery Configuration (modern django-celery-results style, no djcelery)
# To use Celery you also need a broker (Redis or RabbitMQ).
# For local development without a broker, tasks are executed eagerly.
# -----------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = True   # run tasks synchronously when no broker
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'memory://')
CELERY_RESULT_BACKEND = 'cache'
CELERY_CACHE_BACKEND = 'memory'

# ── Logging ─────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'map': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'apscheduler': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
    },
}
