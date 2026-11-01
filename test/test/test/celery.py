"""
Celery application for SmartDispatch.
Modernized for Celery 5.x - removed djcelery dependency.
"""

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'test.settings')

app = Celery('test')

# Read config from Django settings, using the CELERY_ namespace prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps.
app.autodiscover_tasks()
