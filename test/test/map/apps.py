"""
map/apps.py — Django AppConfig for the map app.

Starts two APScheduler jobs when the server boots:
  1. Hourly ambulance repositioning (runs at :00 each hour).
  2. EMS call simulation (runs every 3 minutes — generates realistic fake
     calls so the map always has live activity to show).

Both jobs are skipped gracefully if DB tables don't exist yet (migrations
haven't run) so manage.py migrate and check work without errors.
"""

import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MapConfig(AppConfig):
    name            = 'map'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """
        Called once when Django starts. Boots the APScheduler.
        Guard against double-start (Django reloader runs ready() twice).
        """
        import os
        # Only start scheduler in the main process, not the reloader child
        if os.environ.get('RUN_MAIN') != 'true':
            return

        try:
            self._start_scheduler()
        except Exception as e:
            logger.warning(f"Scheduler could not start: {e}")

    def _start_scheduler(self):
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron    import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        import pytz

        tz = pytz.timezone('Asia/Kolkata')  # IST
        scheduler = BackgroundScheduler(timezone=tz)

        # ── Job 1: Hourly ambulance repositioning ────────────────────
        scheduler.add_job(
            _job_reposition_ambulances,
            trigger=CronTrigger(minute=0, timezone=tz),
            id='hourly_reposition',
            replace_existing=True,
            misfire_grace_time=300,
        )

        # ── Job 2: EMS simulation — new call every 3 minutes ─────────
        scheduler.add_job(
            _job_simulate_ems_call,
            trigger=IntervalTrigger(minutes=3),
            id='ems_simulation',
            replace_existing=True,
            misfire_grace_time=60,
        )

        # ── Job 3: Auto-resolve old EMS calls (after 10 minutes) ─────
        scheduler.add_job(
            _job_resolve_old_calls,
            trigger=IntervalTrigger(minutes=10),
            id='auto_resolve',
            replace_existing=True,
            misfire_grace_time=60,
        )

        scheduler.start()
        logger.info("SmartDispatch scheduler started (reposition + simulation + auto-resolve).")


# ── Scheduled job functions ───────────────────────────────────────────────────

def _job_reposition_ambulances():
    """
    Runs at the top of each hour.
    Uses K-Means on current demand to optimally place all active ambulances.
    """
    try:
        from map.positioning import reposition_ambulances
        result = reposition_ambulances()
        logger.info(f"Hourly reposition: {len(result)} ambulances repositioned.")
    except Exception as e:
        logger.error(f"Reposition job failed: {e}")


def _job_simulate_ems_call():
    """
    Runs every 3 minutes.
    Generates a realistic fake EMS call at a random demand-weighted location.
    Automatically dispatches the nearest ambulance.
    """
    try:
        import random
        from map.chandigarh_data import get_current_demand, weighted_random_zone, random_point_in_zone, ZONE_BY_ID
        from map.models import Current_ambulance, Current_emscall, EMS_Calls, Event_feed

        # Only simulate if there are active ambulances
        if not Current_ambulance.objects.filter(AVAILABLE=1).exists():
            return

        # 20% chance of no call this interval (makes it realistic, not constant)
        if random.random() < 0.20:
            return

        demand  = get_current_demand()
        zone_id = weighted_random_zone(demand)
        lat, lng = random_point_in_zone(zone_id)
        zone_name = ZONE_BY_ID[zone_id][1]

        # Archive and replace current EMS call
        for call in Current_emscall.objects.all():
            EMS_Calls.objects.get_or_create(
                ems_id=call.id,
                defaults=dict(addr=call.addr, LAT=call.LAT, LONG=call.LONG, time=call.time)
            )
        Current_emscall.objects.all().delete()

        new_call = Current_emscall.objects.create(
            addr=zone_name, LAT=lat, LONG=lng
        )

        Event_feed.objects.create(
            event_type='Event',
            event_desc=f"EMS #{new_call.id} incoming: {zone_name}",
            unit=new_call.id, LAT=lat, LONG=lng
        )

        # Dispatch nearest ambulance
        amb_obj = Current_ambulance()
        amb_obj.dispatch_ambulance(lat, lng)

        logger.info(f"Simulated EMS call at {zone_name} ({lat:.4f}, {lng:.4f})")

    except Exception as e:
        logger.error(f"EMS simulation job failed: {e}")


def _job_resolve_old_calls():
    """
    Runs every 10 minutes.
    Resolves the current EMS call (clears Current_emscall) and marks the
    dispatched ambulance as active again — simulating ambulance return.
    """
    try:
        import random
        from map.models import Current_ambulance, Current_emscall, EMS_Calls, Event_feed

        # Find ambulances that are inactive (on call)
        inactive = Current_ambulance.objects.filter(AVAILABLE=0)
        if not inactive.exists():
            return

        # Randomly pick one to return (not always all of them)
        to_return = random.choice(list(inactive))

        # Move them back to their approximate home zone (add small random offset)
        import math
        offset = 0.005  # ~500m
        to_return.LAT  += random.gauss(0, offset)
        to_return.LONG += random.gauss(0, offset)
        to_return.AVAILABLE = 1
        to_return.save()

        Event_feed.objects.create(
            event_type='Return',
            event_desc=f"Amb #{to_return.amb_id} returned to service",
            unit=to_return.amb_id
        )

        # Clear the current EMS call
        calls = Current_emscall.objects.all()
        if calls.exists():
            for call in calls:
                EMS_Calls.objects.get_or_create(
                    ems_id=call.id,
                    defaults=dict(addr=call.addr, LAT=call.LAT, LONG=call.LONG, time=call.time)
                )
            calls.delete()

        logger.info(f"Auto-resolved: Amb #{to_return.amb_id} returned to service.")

    except Exception as e:
        logger.error(f"Auto-resolve job failed: {e}")
