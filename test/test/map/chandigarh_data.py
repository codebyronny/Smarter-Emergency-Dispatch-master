"""
chandigarh_data.py

Chandigarh Tricity EMS Data — Zone definitions and call-demand model.

This module defines:
  1. ZONES — 20 real sectors/areas across Chandigarh, Mohali, Panchkula
     with their centre coordinates and base demand weights.
  2. AMBULANCES — 15 ambulance starting positions.
  3. hourly_demand(zone_id, hour, day_of_week) — realistic hourly EMS call
     rate per zone based on:
       - Time of day (peaks at rush hours 8-10am, 12-2pm, 6-10pm)
       - Day of week (higher weekdays)
       - Zone type (hospital zones, market zones, residential, etc.)
  4. get_current_demand() — returns a dict {zone_id: expected_calls} for
     the current hour, used by the K-Means repositioner.
"""

import math
import datetime
import random

# ── Zone definitions ──────────────────────────────────────────────────────────
# (zone_id, name, lat, lng, zone_type, base_weight)
# zone_type: 'hospital', 'market', 'residential', 'industrial', 'highway', 'university'
# base_weight: relative EMS demand multiplier (1.0 = average)

ZONES = [
    # ── Chandigarh ──────────────────────────────────────────────────
    ('CHD-S17',  'Sector 17 — City Centre',        30.7402, 76.7849, 'market',      2.5),
    ('CHD-S22',  'Sector 22 — Commercial',          30.7404, 76.7974, 'market',      2.3),
    ('CHD-S32',  'Sector 32 — GMSH Hospital',       30.7230, 76.7767, 'hospital',    3.0),
    ('CHD-PGI',  'PGI / PGIMER Sector 12',          30.7651, 76.7779, 'hospital',    3.5),
    ('CHD-S16',  'Sector 16 — Civil Hospital',      30.7528, 76.7794, 'hospital',    2.8),
    ('CHD-S26',  'Sector 26 — Grain Market',        30.7472, 76.8023, 'market',      1.8),
    ('CHD-S08',  'Sector 8 — North Residential',    30.7680, 76.7630, 'residential', 1.2),
    ('CHD-S43',  'Sector 43 / IT Park',             30.7090, 76.8020, 'industrial',  1.5),
    ('CHD-S40',  'Sector 40 — South Residential',   30.7100, 76.7900, 'residential', 1.3),
    ('CHD-MNM',  'Manimajra — East',                30.7218, 76.8231, 'residential', 1.6),
    ('CHD-IA1',  'Industrial Area Phase 1',          30.7020, 76.7580, 'industrial',  1.4),
    ('CHD-S35',  'Sector 35 — Business District',   30.7340, 76.7850, 'market',      2.0),
    # ── Mohali ──────────────────────────────────────────────────────
    ('MOH-PH7',  'Mohali Phase 7 — Civil Hospital', 30.7046, 76.7178, 'hospital',    2.6),
    ('MOH-AER',  'Mohali Aerocity / Phase 10',       30.6770, 76.7280, 'industrial',  1.4),
    ('MOH-S70',  'Mohali Sector 70 — North',        30.7200, 76.7050, 'residential', 1.2),
    ('MOH-IT',   'Mohali IT City / Phase 8',        30.7100, 76.7150, 'industrial',  1.6),
    # ── Panchkula ───────────────────────────────────────────────────
    ('PKL-S06',  'Panchkula Sector 6 — Civil Hosp', 30.7021, 76.8527, 'hospital',    2.4),
    ('PKL-S15',  'Panchkula Sector 15 / MDC',       30.7300, 76.8700, 'market',      1.7),
    ('PKL-S05',  'Panchkula Sector 5 — Residential',30.6980, 76.8490, 'residential', 1.1),
    ('PKL-RRP',  'Panchkula — Raipur Rani South',   30.6800, 76.8400, 'residential', 0.9),
]

# Index for fast lookup
ZONE_BY_ID = {z[0]: z for z in ZONES}

# ── Ambulance home stations ───────────────────────────────────────────────────
# (amb_id, lat, lng, available, home_zone_id, label)
AMBULANCES = [
    # Chandigarh city ambulances
    (1,  30.7402, 76.7849, 1, 'CHD-S17', 'Sector 17 Plaza'),
    (2,  30.7230, 76.7767, 1, 'CHD-S32', 'GMSH Sector 32'),
    (3,  30.7651, 76.7779, 1, 'CHD-PGI', 'PGI Sector 12'),
    (4,  30.7528, 76.7794, 1, 'CHD-S16', 'Civil Hospital Sec 16'),
    (5,  30.7472, 76.8023, 1, 'CHD-S26', 'Sector 26 Market'),
    (6,  30.7680, 76.7630, 0, 'CHD-S08', 'Sector 8 North'),
    (7,  30.7100, 76.7900, 1, 'CHD-S43', 'IT Park Sec 43'),
    (8,  30.7218, 76.8231, 0, 'CHD-MNM', 'Manimajra East'),
    (9,  30.7020, 76.7580, 1, 'CHD-IA1', 'Industrial Area Ph1'),
    (10, 30.7340, 76.7850, 1, 'CHD-S35', 'Sector 35 Business'),
    # Mohali ambulances
    (11, 30.7046, 76.7178, 1, 'MOH-PH7', 'Mohali Civil Hospital'),
    (12, 30.6770, 76.7280, 1, 'MOH-AER', 'Mohali Aerocity'),
    (13, 30.7200, 76.7050, 0, 'MOH-S70', 'Mohali Sector 70'),
    # Panchkula ambulances
    (14, 30.7021, 76.8527, 1, 'PKL-S06', 'Panchkula Civil Hosp'),
    (15, 30.7300, 76.8700, 1, 'PKL-S15', 'Panchkula Sector 15'),
]


# ── Hourly demand model ───────────────────────────────────────────────────────

# Time-of-day multiplier (0-23h) — peaks at commute + evening hours
HOUR_MULTIPLIER = {
    0: 0.3,  1: 0.2,  2: 0.2,  3: 0.2,  4: 0.25,
    5: 0.4,  6: 0.7,  7: 1.1,  8: 1.5,  9: 1.6,
   10: 1.4, 11: 1.3, 12: 1.5, 13: 1.4, 14: 1.2,
   15: 1.2, 16: 1.3, 17: 1.6, 18: 1.9, 19: 2.0,
   20: 1.8, 21: 1.5, 22: 1.0, 23: 0.6,
}

# Day-of-week multiplier (0=Mon...6=Sun)
DAY_MULTIPLIER = {0: 1.1, 1: 1.1, 2: 1.0, 3: 1.0, 4: 1.2, 5: 1.3, 6: 0.9}

# Zone-type time-of-day adjustments
ZONE_TYPE_HOUR_BOOST = {
    'hospital':    {8: 0.5, 9: 0.5, 10: 0.4, 14: 0.3, 15: 0.3},
    'market':      {10: 0.4, 11: 0.5, 12: 0.4, 17: 0.5, 18: 0.6, 19: 0.5},
    'industrial':  {7: 0.3, 8: 0.5, 17: 0.6, 18: 0.4},
    'university':  {9: 0.4, 10: 0.4, 13: 0.3, 14: 0.3},
    'highway':     {7: 0.4, 8: 0.4, 17: 0.5, 18: 0.5, 20: 0.3},
    'residential': {22: 0.2, 23: 0.2, 0: 0.1},
}


def hourly_demand(zone_id: str, hour: int, day_of_week: int) -> float:
    """
    Return expected EMS calls for zone_id at hour (0-23) on day_of_week (0-6 Mon-Sun).

    Uses:
      base_weight × hour_multiplier × day_multiplier + zone_type_boost
    """
    if zone_id not in ZONE_BY_ID:
        return 0.5

    _, _, _, _, zone_type, base_weight = ZONE_BY_ID[zone_id]

    h_mult  = HOUR_MULTIPLIER.get(hour, 1.0)
    d_mult  = DAY_MULTIPLIER.get(day_of_week, 1.0)
    boost   = ZONE_TYPE_HOUR_BOOST.get(zone_type, {}).get(hour, 0.0)

    return round(base_weight * h_mult * d_mult + boost, 3)


def get_current_demand() -> dict:
    """
    Returns {zone_id: expected_calls} for the current hour and day.
    Used by the K-Means repositioner every hour.
    """
    now = datetime.datetime.now()
    return {
        z[0]: hourly_demand(z[0], now.hour, now.weekday())
        for z in ZONES
    }


def get_demand_for(hour: int, day_of_week: int) -> dict:
    """Returns demand dict for a specific hour and day (for data generation)."""
    return {
        z[0]: hourly_demand(z[0], hour, day_of_week)
        for z in ZONES
    }


def weighted_random_zone(demand: dict) -> str:
    """
    Pick a random zone weighted by current demand.
    Used by the simulation to generate realistic EMS call locations.
    """
    zones   = list(demand.keys())
    weights = [demand[z] for z in zones]
    total   = sum(weights)
    r       = random.uniform(0, total)
    cumulative = 0.0
    for z, w in zip(zones, weights):
        cumulative += w
        if r <= cumulative:
            return z
    return zones[-1]


def random_point_in_zone(zone_id: str, spread: float = 0.008) -> tuple:
    """
    Returns a (lat, lng) randomly scattered around a zone centre.
    spread controls how far from centre (default ≈ 0.8 km).
    """
    _, _, lat, lng, _, _ = ZONE_BY_ID[zone_id]
    lat += random.gauss(0, spread)
    lng += random.gauss(0, spread)
    return round(lat, 6), round(lng, 6)
