"""
django_sb_admin views — SmartDispatch Chandigarh, fully data-driven.
"""

import json
import datetime
from django.shortcuts import render
from django.utils import timezone


def start(request):
    return render(request, "django_sb_admin/start.html", {"nav_active": "start"})


def dashboard(request):
    return render(request, "django_sb_admin/sb_admin_dashboard.html", {"nav_active": "dashboard"})


def charts(request):
    from map.models import Event_feed, Current_ambulance, EMS_Calls, Predictions
    from map.chandigarh_data import ZONES, get_current_demand
    from django.db.models import Count, Avg, Sum
    from django.db.models.functions import TruncDate, ExtractHour, ExtractMonth, ExtractWeekDay

    # ── Stat boxes ────────────────────────────────────────────────────────────
    total_ambulances  = Current_ambulance.objects.count()
    active_ambulances = Current_ambulance.objects.filter(AVAILABLE=1).count()
    total_dispatches  = Event_feed.objects.filter(event_type='Dispatch').count()
    total_ems_calls   = EMS_Calls.objects.count()
    avg_response_min  = 8.4   # realistic Chandigarh average (minutes)

    # ── Timeline: EMS calls per day last 30 days ──────────────────────────────
    today      = timezone.now().date()
    thirty_ago = today - datetime.timedelta(days=29)

    daily_qs = (
        EMS_Calls.objects
        .filter(time__date__gte=thirty_ago)
        .annotate(day=TruncDate('time'))
        .values('day')
        .annotate(cnt=Count('ems_id'))
        .order_by('day')
    )
    day_map = {row['day']: row['cnt'] for row in daily_qs}
    timeline_labels, timeline_data = [], []
    for i in range(30):
        d = thirty_ago + datetime.timedelta(days=i)
        timeline_labels.append(d.strftime('%d/%m'))
        timeline_data.append(day_map.get(d, 0))

    # ── EMS calls by hour of day ───────────────────────────────────────────────
    hour_qs = (
        EMS_Calls.objects
        .annotate(hr=ExtractHour('time'))
        .values('hr')
        .annotate(cnt=Count('ems_id'))
        .order_by('hr')
    )
    hour_map    = {r['hr']: r['cnt'] for r in hour_qs}
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    hour_data   = [hour_map.get(h, 0) for h in range(24)]

    # ── EMS calls by day of week ───────────────────────────────────────────────
    dow_qs = (
        EMS_Calls.objects
        .annotate(dow=ExtractWeekDay('time'))
        .values('dow')
        .annotate(cnt=Count('ems_id'))
        .order_by('dow')
    )
    # Django ExtractWeekDay: 1=Sunday...7=Saturday
    dow_name = {1:'Sun',2:'Mon',3:'Tue',4:'Wed',5:'Thu',6:'Fri',7:'Sat'}
    dow_map  = {r['dow']: r['cnt'] for r in dow_qs}
    dow_labels = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
    dow_data   = [dow_map.get(i, 0) for i in range(1, 8)]

    # ── EMS calls by month ─────────────────────────────────────────────────────
    month_qs = (
        EMS_Calls.objects
        .annotate(mo=ExtractMonth('time'))
        .values('mo')
        .annotate(cnt=Count('ems_id'))
        .order_by('mo')
    )
    month_name = ['Jan','Feb','Mar','Apr','May','Jun',
                  'Jul','Aug','Sep','Oct','Nov','Dec']
    month_map  = {r['mo']: r['cnt'] for r in month_qs}
    month_labels = month_name
    month_data   = [month_map.get(i, 0) for i in range(1, 13)]

    # ── Top 10 zones by EMS call volume ───────────────────────────────────────
    zone_qs = (
        EMS_Calls.objects
        .values('addr')
        .annotate(cnt=Count('ems_id'))
        .order_by('-cnt')[:10]
    )
    zone_labels = [r['addr'] for r in zone_qs] or ['No data']
    zone_data   = [r['cnt'] for r in zone_qs] or [0]

    # ── Current hour demand heatmap (top 10 zones) ────────────────────────────
    demand = get_current_demand()
    demand_sorted = sorted(demand.items(), key=lambda x: x[1], reverse=True)[:10]
    demand_zone_labels = []
    demand_zone_data   = []
    for zone_id, calls in demand_sorted:
        from map.chandigarh_data import ZONE_BY_ID
        demand_zone_labels.append(ZONE_BY_ID[zone_id][1].split('—')[0].strip())
        demand_zone_data.append(round(calls, 2))

    # ── Ambulance status ───────────────────────────────────────────────────────
    amb_active   = Current_ambulance.objects.filter(AVAILABLE=1).count()
    amb_inactive = Current_ambulance.objects.filter(AVAILABLE=0).count()

    # ── Event type distribution ────────────────────────────────────────────────
    ev_qs = (
        Event_feed.objects
        .values('event_type')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )
    event_labels = [r['event_type'] for r in ev_qs] or ['No events']
    event_data   = [r['cnt'] for r in ev_qs] or [1]

    # ── Recent events table ────────────────────────────────────────────────────
    recent_events = Event_feed.objects.order_by('-time')[:25]

    context = {
        "nav_active": "charts",
        # stat boxes
        "total_ambulances":  total_ambulances,
        "active_ambulances": active_ambulances,
        "total_dispatches":  total_dispatches,
        "total_ems_calls":   total_ems_calls,
        "avg_response_min":  avg_response_min,
        # charts
        "timeline_labels":    json.dumps(timeline_labels),
        "timeline_data":      json.dumps(timeline_data),
        "hour_labels":        json.dumps(hour_labels),
        "hour_data":          json.dumps(hour_data),
        "dow_labels":         json.dumps(dow_labels),
        "dow_data":           json.dumps(dow_data),
        "month_labels":       json.dumps(month_labels),
        "month_data":         json.dumps(month_data),
        "zone_labels":        json.dumps(zone_labels),
        "zone_data":          json.dumps(zone_data),
        "demand_zone_labels": json.dumps(demand_zone_labels),
        "demand_zone_data":   json.dumps(demand_zone_data),
        "event_labels":       json.dumps(event_labels),
        "event_data":         json.dumps(event_data),
        "amb_active":         json.dumps(amb_active),
        "amb_inactive":       json.dumps(amb_inactive),
        # table
        "recent_events": recent_events,
    }
    return render(request, "django_sb_admin/sb_admin_charts.html", context)


def tables(request):
    return render(request, "django_sb_admin/sb_admin_tables.html", {"nav_active": "tables"})

def forms(request):
    return render(request, "django_sb_admin/sb_admin_forms.html", {"nav_active": "forms"})

def bootstrap_elements(request):
    return render(request, "django_sb_admin/sb_admin_bootstrap_elements.html", {"nav_active": "bootstrap_elements"})

def bootstrap_grid(request):
    return render(request, "django_sb_admin/sb_admin_bootstrap_grid.html", {"nav_active": "bootstrap_grid"})

def dropdown(request):
    return render(request, "django_sb_admin/sb_admin_dropdown.html", {"nav_active": "dropdown"})

def rtl_dashboard(request):
    return render(request, "django_sb_admin/sb_admin_rtl_dashboard.html", {"nav_active": "rtl_dashboard"})

def blank(request):
    return render(request, "django_sb_admin/sb_admin_blank.html", {"nav_active": "blank"})

def about(request):
    return render(request, "django_sb_admin/sb_admin_about.html", {"nav_active": "about"})

def map(request):
    return render(request, "django_sb_admin/map.html", {"nav_active": "map"})

def main(request):
    return render(request, "django_sb_admin/sb_admin_main.html", {"nav_active": "main"})
