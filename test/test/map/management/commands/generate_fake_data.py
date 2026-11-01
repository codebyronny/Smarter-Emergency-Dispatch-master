"""
Management command: generate_fake_data

Generates realistic fake Chandigarh EMS data:
  - EMS_Calls: historical call log
  - Event_feed: past dispatch/activate/auto-position events
  - Current_predictions: today's hourly demand snapshot
  - Reseeds ambulances at correct Chandigarh coordinates
  - Runs initial K-Means auto-positioning

Usage:
    python manage.py generate_fake_data
    python manage.py generate_fake_data --days 90
"""

import random
import datetime
import pytz
from django.core.management.base import BaseCommand

from map.models import (
    Predictions, EMS_Calls, Event_feed, Ambulance,
    Current_ambulance, Current_emscall, Current_predictions
)
from map.chandigarh_data import (
    ZONES, AMBULANCES, ZONE_BY_ID,
    get_demand_for, weighted_random_zone, random_point_in_zone
)

HOUR_WEIGHTS = [
    0.3, 0.2, 0.2, 0.2, 0.25, 0.4, 0.7, 1.1, 1.5, 1.6,
    1.4, 1.3, 1.5, 1.4, 1.2,  1.2, 1.3, 1.6, 1.9, 2.0,
    1.8, 1.5, 1.0, 0.6,
]


class Command(BaseCommand):
    help = 'Generate fake Chandigarh EMS data for the SmartDispatch system'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90,
                            help='Days of historical data (default 90)')

    def handle(self, *args, **options):
        days = options['days']
        IST = pytz.timezone('Asia/Kolkata')
        now  = datetime.datetime.now(tz=IST)
        start = now - datetime.timedelta(days=days)

        # ── Clear old generated data ──────────────────────────────────────────
        self.stdout.write('Clearing old data...')
        EMS_Calls.objects.all().delete()
        Event_feed.objects.all().delete()
        Ambulance.objects.all().delete()
        Current_predictions.objects.all().delete()
        Current_emscall.objects.all().delete()
        self.stdout.write('  Done.\n')

        # ── 1. Historical EMS calls ───────────────────────────────────────────
        self.stdout.write(f'Generating EMS calls ({days} days)...')
        call_batch = []
        ems_id = 1
        for day_off in range(days):
            d   = start + datetime.timedelta(days=day_off)
            dow = d.weekday()
            for hour in range(24):
                demand = get_demand_for(hour, dow)
                total  = sum(demand.values())
                n_calls = max(0, int(random.gauss(total * 0.35, 1.2)))
                for _ in range(n_calls):
                    zone_id   = weighted_random_zone(demand)
                    lat, lng  = random_point_in_zone(zone_id)
                    zone_name = ZONE_BY_ID[zone_id][1]
                    call_time = IST.localize(datetime.datetime(
                        d.year, d.month, d.day, hour,
                        random.randint(0, 59), random.randint(0, 59)
                    ))
                    call_batch.append(EMS_Calls(
                        ems_id=ems_id, addr=zone_name,
                        LAT=lat, LONG=lng, time=call_time,
                    ))
                    ems_id += 1
            if len(call_batch) >= 2000:
                EMS_Calls.objects.bulk_create(call_batch)
                call_batch = []
                self.stdout.write(f'  Day {day_off+1}/{days}...')

        if call_batch:
            EMS_Calls.objects.bulk_create(call_batch)
        total_calls = EMS_Calls.objects.count()
        self.stdout.write(f'  EMS calls created: {total_calls:,}\n')

        # ── 2. Event feed history ─────────────────────────────────────────────
        self.stdout.write('Generating event history...')
        amb_ids = [a[0] for a in AMBULANCES]
        ev_batch = []
        event_days = min(days, 60)

        for day_off in range(event_days):
            d   = start + datetime.timedelta(days=day_off)
            dow = d.weekday()
            for _ in range(random.randint(6, 20)):
                hour   = random.choices(range(24), weights=HOUR_WEIGHTS)[0]
                ev_time = IST.localize(datetime.datetime(d.year, d.month, d.day, hour,
                                            random.randint(0, 59)))
                amb_id = random.choice(amb_ids)
                r = random.random()
                if r < 0.40:
                    ev_type = 'Dispatch'
                    zone_id = weighted_random_zone(get_demand_for(hour, dow))
                    zname   = ZONE_BY_ID[zone_id][1]
                    desc    = f"Amb #{amb_id} dispatched to {zname}"
                    lat, lng = random_point_in_zone(zone_id)
                elif r < 0.65:
                    ev_type = 'Activate'
                    desc    = f"Amb #{amb_id} status updated to active"
                    lat, lng = None, None
                elif r < 0.80:
                    ev_type = 'Return'
                    desc    = f"Amb #{amb_id} returned to service"
                    lat, lng = None, None
                elif r < 0.90:
                    ev_type = 'AutoPos'
                    n_a     = random.randint(8, 11)
                    desc    = f"Auto-reposition: {n_a} ambulances optimally placed"
                    lat, lng = None, None
                else:
                    ev_type = 'Event'
                    zone_id = weighted_random_zone(get_demand_for(hour, dow))
                    zname   = ZONE_BY_ID[zone_id][1]
                    desc    = f"EMS incoming: {zname}"
                    lat, lng = random_point_in_zone(zone_id)

                ev_batch.append(Event_feed(
                    event_type=ev_type, event_desc=desc,
                    unit=amb_id if ev_type in ('Dispatch', 'Activate', 'Return') else None,
                    LAT=lat, LONG=lng, time=ev_time,
                ))

        Event_feed.objects.bulk_create(ev_batch)
        self.stdout.write(f'  Events created: {Event_feed.objects.count():,}\n')

        # ── 3. Current_predictions — today's 24-hour snapshot ────────────────
        self.stdout.write('Populating current predictions...')
        dow_now  = now.weekday()
        doy_now  = now.timetuple().tm_yday
        week_now = now.isocalendar()[1]
        is_wkend = dow_now >= 5
        cp_batch = []
        for hour in range(24):
            demand = get_demand_for(hour, dow_now)
            for zone_id, calls in demand.items():
                cp_batch.append(Current_predictions(
                    zcta=zone_id,
                    year=now.year, month=now.month, day_of_month=now.day,
                    hour_of_day=hour, day_of_year=doy_now,
                    week_of_year=week_now, day_of_week=dow_now,
                    is_weekend=is_wkend, call_counts=round(calls, 4),
                ))
        Current_predictions.objects.bulk_create(cp_batch)
        self.stdout.write(f'  Current predictions: {Current_predictions.objects.count()}\n')

        # ── 4. Reseed ambulances at correct Chandigarh coords ─────────────────
        self.stdout.write('Seeding 15 ambulances...')
        Current_ambulance.objects.all().delete()
        for amb_id, lat, lng, avail, home_zone, label in AMBULANCES:
            Current_ambulance.objects.create(
                amb_id=amb_id, LAT=lat, LONG=lng, AVAILABLE=avail
            )

        # Run initial K-Means auto-positioning
        from map.positioning import reposition_ambulances
        reposition_ambulances()
        self.stdout.write(
            f'  Ambulances: {Current_ambulance.objects.count()} '
            f'(active: {Current_ambulance.objects.filter(AVAILABLE=1).count()})\n'
        )

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f'\nAll done!\n'
            f'  Predictions:          {Predictions.objects.count():,}\n'
            f'  Historical EMS calls: {total_calls:,}\n'
            f'  Event feed entries:   {Event_feed.objects.count():,}\n'
            f'  Ambulances:           {Current_ambulance.objects.count()}\n'
            f'\nOpen http://127.0.0.1:8000/ to view the live dashboard.\n'
        ))
