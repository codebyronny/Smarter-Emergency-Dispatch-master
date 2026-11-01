"""
positioning.py — Chandigarh ambulance optimal positioning engine.

Replaces the SF shapefile-based model_2_funcs.py for Chandigarh.

Algorithm:
  1. Get current EMS demand per zone (from chandigarh_data.hourly_demand).
  2. Generate weighted sample points around each zone centre proportional
     to expected call volume.
  3. Run K-Means on the sample points to find k=N_active_ambulances
     optimal waiting locations.
  4. Assign each active ambulance to its nearest cluster centre (Hungarian
     greedy nearest-pair so no two ambulances go to the same spot).
  5. Update Current_ambulance DB rows for all active units.

This runs completely in-memory — no shapefile, no geopandas, no external data.
"""

import math
import random
import numpy as np
from sklearn.cluster import KMeans

from .chandigarh_data import ZONES, get_current_demand, random_point_in_zone


# ── Hyper-parameters ──────────────────────────────────────────────────────────
POINTS_PER_UNIT_DEMAND = 30   # sample points per 1.0 expected call
MIN_POINTS_PER_ZONE    = 3    # always put at least 3 points per zone
MAX_TOTAL_POINTS       = 2000 # cap so K-Means stays fast


def _generate_demand_points(demand: dict) -> np.ndarray:
    """
    Build a numpy array of (lat, lng) sample points across Chandigarh,
    with density proportional to zone demand.
    """
    points = []
    total_demand = sum(demand.values())

    for zone_id, expected_calls in demand.items():
        n_points = max(
            MIN_POINTS_PER_ZONE,
            int(expected_calls * POINTS_PER_UNIT_DEMAND)
        )
        for _ in range(n_points):
            lat, lng = random_point_in_zone(zone_id, spread=0.006)
            points.append([lat, lng])

    # Cap total for performance
    if len(points) > MAX_TOTAL_POINTS:
        random.shuffle(points)
        points = points[:MAX_TOTAL_POINTS]

    return np.array(points)


def _greedy_assign(ambulance_locs: list, cluster_centres: np.ndarray) -> dict:
    """
    Greedy nearest-pair assignment: each ambulance gets a unique cluster centre.

    ambulance_locs: list of (amb_id, lat, lng)
    cluster_centres: numpy array shape (n_clusters, 2)

    Returns {amb_id: (new_lat, new_lng)}
    """
    n = len(ambulance_locs)
    centres = list(cluster_centres)

    # Euclidean distance matrix [ambulance × centre]
    dist = np.zeros((n, n))
    for i, (_, alat, alng) in enumerate(ambulance_locs):
        for j, (clat, clng) in enumerate(centres):
            dist[i, j] = math.sqrt((alat - clat)**2 + (alng - clng)**2)

    assignments = {}
    used_centres = set()
    max_val = dist.max() + 1

    for _ in range(n):
        best_amb_idx, best_ctr_idx = np.unravel_index(dist.argmin(), dist.shape)
        amb_id = ambulance_locs[best_amb_idx][0]
        new_lat, new_lng = centres[best_ctr_idx]
        assignments[amb_id] = (float(new_lat), float(new_lng))
        dist[best_amb_idx, :] = max_val
        dist[:, best_ctr_idx] = max_val

    return assignments


def reposition_ambulances() -> dict:
    """
    Main entry point. Computes optimal waiting locations for all active
    ambulances based on current-hour EMS demand.

    Returns {amb_id: (new_lat, new_lng)} for all active ambulances.
    Raises ValueError if there are no active ambulances.

    Side effect: updates Current_ambulance rows in the DB and logs to Event_feed.
    """
    # Import here to avoid circular imports at module load time
    from .models import Current_ambulance, Event_feed

    active_ambs = list(Current_ambulance.objects.filter(AVAILABLE=1).order_by('amb_id'))
    n_active = len(active_ambs)

    if n_active == 0:
        return {}

    # 1. Get current demand
    demand = get_current_demand()

    # 2. Generate weighted sample points
    points = _generate_demand_points(demand)

    if len(points) < n_active:
        # Shouldn't happen, but safety fallback
        return {}

    # 3. K-Means clustering
    kmeans = KMeans(n_clusters=n_active, n_init=10, random_state=42)
    kmeans.fit(points)
    centres = kmeans.cluster_centers_  # shape (n_active, 2)

    # 4. Greedy assignment
    amb_locs = [(a.amb_id, a.LAT, a.LONG) for a in active_ambs]
    assignments = _greedy_assign(amb_locs, centres)

    # 5. Update DB
    for amb in active_ambs:
        if amb.amb_id in assignments:
            new_lat, new_lng = assignments[amb.amb_id]
            amb.LAT  = new_lat
            amb.LONG = new_lng
            amb.save()

    # Log the reposition event
    import datetime
    now = datetime.datetime.now()
    Event_feed.objects.create(
        event_type='AutoPos',
        event_desc=(
            f"Auto-reposition: {n_active} ambulances optimally placed "
            f"for {now.strftime('%H:%M')} demand"
        )
    )

    return assignments


def get_demand_summary() -> list:
    """
    Returns a sorted list of (zone_name, zone_id, expected_calls) for the
    current hour — used by the charts page.
    """
    from .chandigarh_data import get_current_demand, ZONE_BY_ID
    demand = get_current_demand()
    result = []
    for zone_id, calls in demand.items():
        name = ZONE_BY_ID[zone_id][1]
        result.append((name, zone_id, calls))
    result.sort(key=lambda x: x[2], reverse=True)
    return result
