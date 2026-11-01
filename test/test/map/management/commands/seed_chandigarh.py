"""
Management command: seed_chandigarh

Seeds 15 ambulances spread across the Chandigarh Tricity
(Chandigarh + Mohali + Panchkula), clearing any existing data first.

Usage:
    python manage.py seed_chandigarh
"""

from django.core.management.base import BaseCommand
from map.models import Current_ambulance, Event_feed

# 15 ambulances at distinct real locations across the tricity.
# Deliberately spread: north/south/east/west, all three cities.
# (amb_id, lat,       lng,       available, location_name)
AMBULANCES = [
    # ── Chandigarh ─────────────────────────────────────────────────────
    (1,  30.7333,  76.7794,  1, "Sector 17 Plaza — City Centre"),
    (2,  30.7230,  76.7767,  1, "Sector 32 — Govt Multi Specialty Hospital"),
    (3,  30.7651,  76.7779,  1, "PGI (PGIMER) — Sector 12"),
    (4,  30.7528,  76.7794,  1, "Sector 16 Hospital"),
    (5,  30.7472,  76.8023,  1, "Sector 26 — Grain Market area"),
    (6,  30.7680,  76.7630,  0, "Sector 8 — North Chandigarh"),
    (7,  30.7100,  76.7900,  1, "Sector 40 — South Chandigarh"),
    (8,  30.7218,  76.8231,  0, "Manimajra — East Chandigarh"),
    (9,  30.7020,  76.7580,  1, "Industrial Area Phase 1 — SW Chandigarh"),
    # ── Mohali ─────────────────────────────────────────────────────────
    (10, 30.7046,  76.7178,  1, "Mohali — Phase 7 Civil Hospital"),
    (11, 30.6770,  76.7280,  1, "Mohali — Aerocity / Phase 10"),
    (12, 30.7200,  76.7050,  0, "Mohali — Sector 70 (North Mohali)"),
    # ── Panchkula ──────────────────────────────────────────────────────
    (13, 30.7021,  76.8527,  1, "Panchkula — Sector 6 Civil Hospital"),
    (14, 30.7300,  76.8700,  1, "Panchkula — Sector 15 / MDC"),
    (15, 30.6800,  76.8400,  0, "Panchkula — Raipur Rani (South)"),
]


class Command(BaseCommand):
    help = 'Seed 15 Chandigarh tricity ambulances into the database'

    def handle(self, *args, **options):
        self.stdout.write('Clearing existing ambulance + EMS call data...')
        Current_ambulance.objects.all().delete()

        self.stdout.write(f'Seeding {len(AMBULANCES)} ambulances across Chandigarh tricity...\n')
        for amb_id, lat, lng, avail, loc in AMBULANCES:
            Current_ambulance.objects.create(
                amb_id=amb_id, LAT=lat, LONG=lng, AVAILABLE=avail
            )
            status = '🟢 Active  ' if avail else '⚫ Inactive'
            self.stdout.write(f'  Amb #{amb_id:02d} {status} — {loc}')

        Event_feed.objects.create(
            event_type='Setup',
            event_desc=f'Tricity ambulances seeded ({len(AMBULANCES)} units)'
        )

        active   = sum(1 for *_, a, _ in AMBULANCES if a)
        inactive = len(AMBULANCES) - active
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done. {len(AMBULANCES)} ambulances loaded — '
            f'{active} active, {inactive} inactive.\n'
        ))
        self.stdout.write(
            'Open http://127.0.0.1:8000/map/ to see all ambulances on the map.\n'
        )
