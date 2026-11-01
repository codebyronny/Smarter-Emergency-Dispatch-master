"""
Project-level Celery tasks.
Modernized for Celery 5.x - removed djcelery/absolute_import boilerplate.
"""

from .celery import app


@app.task
def add(x, y):
    return x + y
