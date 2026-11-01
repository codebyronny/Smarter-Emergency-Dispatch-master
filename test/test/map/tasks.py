"""
Celery periodic tasks for the map app.
Modernized for Celery 5.x:
  - Removed deprecated djcelery periodic_task decorator and crontab from celery.task.schedules
  - Use celery.schedules.crontab and celery.shared_task instead
  - To schedule this task, configure CELERY_BEAT_SCHEDULE in settings.py
    or use django-celery-beat with a database scheduler.

NOTE: For the Django dev server to run without a Celery broker, this module
imports are safe because the task is only executed when a worker is running.
"""

import datetime
from celery import shared_task
from map.models import Current_ambulance, Current_predictions, Predictions


@shared_task
def get_current_preds():
    """
    Hourly task: refreshes the Current_predictions table with data for
    the current hour from the Predictions table.
    """
    now = datetime.datetime.now()
    month = now.month
    day = now.day
    hour = now.hour
    year = now.year

    # Clear current predictions
    Current_predictions.objects.all().delete()

    # Filter main predictions table for the current hour
    t = Predictions.objects.filter(
        year=year, month=month, day_of_month=day, hour_of_day=hour
    ).values_list()

    # Repopulate current predictions
    for line in t:
        t2 = Current_predictions(
            zcta=line[1], year=line[2], month=line[3], day_of_month=line[4],
            hour_of_day=line[5], day_of_year=line[6], week_of_year=line[7],
            day_of_week=line[8], is_weekend=line[9], call_counts=line[10]
        )
        t2.save()
