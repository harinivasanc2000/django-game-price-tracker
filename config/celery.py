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
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Daily refresh at 06:00 Europe/London (server TZ should match)
app.conf.beat_schedule = {
    "refresh-tracked-prices-daily": {
        "task": "apps.games.tasks.refresh_all_tracked_prices",
        "schedule": crontab(hour=6, minute=0),
    },
    # Flush queued price-drop emails every 15 minutes.
    "send-pending-alerts-quarterly": {
        "task": "apps.games.tasks.send_pending_alerts",
        "schedule": crontab(minute="*/15"),
    },
}
app.conf.timezone = "Europe/London"
