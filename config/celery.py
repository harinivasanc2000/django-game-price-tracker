"""
Celery application for background price updates.

Broker: Redis (default redis://127.0.0.1:6379/0)

Run worker:
    celery -A config worker -l info

Run beat (scheduler):
    celery -A config beat -l info

Or combined:
    celery -A config worker -B -l info
"""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Beat schedules and timezone live in Django settings so environment overrides
# have one source of truth and cannot be replaced during Celery app import.
