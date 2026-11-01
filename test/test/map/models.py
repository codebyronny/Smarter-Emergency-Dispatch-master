"""
SmartDispatch map models — Chandigarh edition.

Architecture change from original SF version:
  - create_map() generates a LIVE map directly from the DB on every call.
    No shapefile, no predictions data required.
  - The map is returned as an HTML string, not saved to a file.
    The view passes it to the template via context.
  - update_amb_locs() does NOT reposition ambulances (no Chandigarh prediction
    data exists). It only logs the event. Positions stay as-is until a dispatcher
    manually moves them.
  - Active ambulances  → blue pin with + icon
  - Inactive ambulances → grey pin with + icon
  - Current EMS call   → red pulsing circle
  - Alert zones        → orange circle around EMS call (500 m radius)
"""

from django.db import models
from django.conf import settings

import folium
import googlemaps
import datetime


# ── Map constants ──────────────────────────────────────────────────────────────
CHANDIGARH_LAT = 30.7333
CHANDIGARH_LNG = 76.7794
MAP_ZOOM       = 13

ESRI_TILES = (
    'https://server.arcgisonline.com/ArcGIS/rest/services/'
    'World_Street_Map/MapServer/tile/{z}/{y}/{x}'
)
ESRI_ATTR = (
    'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; '
    'Source: Esri, DeLorme, NAVTEQ, USGS'
)


# ── Database models ────────────────────────────────────────────────────────────

class Event_feed(models.Model):
    event_type = models.CharField(max_length=20)
    event_desc = models.CharField(max_length=120)
    unit       = models.IntegerField(null=True, blank=True)
    LAT        = models.FloatField(null=True, blank=True)
    LONG       = models.FloatField(null=True, blank=True)
    time       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-time']

    def __str__(self):
        return f"[{self.event_type}] {self.event_desc}"


class Predictions(models.Model):
    zcta         = models.CharField(max_length=10)
    year         = models.IntegerField()
    month        = models.IntegerField()
    day_of_month = models.IntegerField()
    hour_of_day  = models.IntegerField()
    day_of_year  = models.IntegerField()
    week_of_year = models.IntegerField()
    day_of_week  = models.IntegerField()
    is_weekend   = models.BooleanField()
    call_counts  = models.FloatField()


class Ambulance(models.Model):
    """Historical log of ambulance positions."""
    amb_id    = models.IntegerField()
    LAT       = models.FloatField()
    LONG      = models.FloatField()
    AVAILABLE = models.IntegerField()
    time      = models.DateTimeField(auto_now_add=True)


class EMS_Calls(models.Model):
    """Historical log of all EMS calls."""
    ems_id = models.IntegerField(primary_key=True)
    addr   = models.CharField(max_length=200)
    LAT    = models.FloatField()
    LONG   = models.FloatField()
    time   = models.DateTimeField()


class Current_predictions(models.Model):
    zcta         = models.CharField(max_length=10)
    year         = models.IntegerField()
    month        = models.IntegerField()
    day_of_month = models.IntegerField()
    hour_of_day  = models.IntegerField()
    day_of_year  = models.IntegerField()
    week_of_year = models.IntegerField()
    day_of_week  = models.IntegerField()
    is_weekend   = models.BooleanField()
    call_counts  = models.FloatField()

    def __str__(self):
        return f"{self.zcta}_{self.call_counts}"


class Current_ambulance(models.Model):
    """Live positions of all ambulances."""
    amb_id    = models.IntegerField(primary_key=True)
    LAT       = models.FloatField()
    LONG      = models.FloatField()
    AVAILABLE = models.IntegerField()  # 1=active, 0=inactive/dispatched

    def __str__(self):
        return f"Amb #{self.amb_id} ({'Active' if self.AVAILABLE else 'Inactive'})"

    # ── History helpers ────────────────────────────────────────────────────────

    def _log_position(self):
        """Save a snapshot of this ambulance to the history table."""
        Ambulance.objects.create(
            amb_id=self.amb_id, LAT=self.LAT,
            LONG=self.LONG, AVAILABLE=self.AVAILABLE
        )

    # ── Status helpers ─────────────────────────────────────────────────────────

    def update_amb_status_only(self, id_, avail_):
        """Change AVAILABLE flag for one ambulance and log the event."""
        amb = Current_ambulance.objects.get(amb_id=id_)
        amb.AVAILABLE = avail_
        amb.save()
        status = 'active' if avail_ else 'inactive'
        Event_feed.objects.create(
            event_type='Activate',
            event_desc=f"Amb #{id_} status updated to {status}",
            unit=id_
        )

    def update_amb_locs(self):
        """
        Reposition active ambulances to K-Means optimal waiting locations
        based on current-hour demand model.
        Replaces the stub that just logged an event.
        """
        try:
            from .positioning import reposition_ambulances
            reposition_ambulances()
        except Exception as e:
            # Never crash the dispatch flow — just log
            import logging
            logging.getLogger(__name__).warning(f"update_amb_locs failed: {e}")
            Event_feed.objects.create(
                event_type='Positions',
                event_desc='Active ambulance positions have been updated'
            )

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def _find_nearest_ambulance(self, available_amb_qs, call_lat, call_lng):
        """
        Use Google Maps Distance Matrix to find the fastest ambulance to a call.
        Falls back to straight-line distance if the API call fails.
        """
        api_key = getattr(settings, 'GGL_API_KEY', '').strip()
        origins = [(amb.LAT, amb.LONG) for amb in available_amb_qs]
        dest    = [(call_lat, call_lng)]

        if api_key:
            try:
                gmaps  = googlemaps.Client(key=api_key)
                result = gmaps.distance_matrix(
                    origins, dest,
                    mode="driving",
                    units="metric",
                    departure_time=datetime.datetime.now()
                )
                best_idx, best_val = 0, float('inf')
                for idx, row in enumerate(result['rows']):
                    el = row['elements'][0]
                    if el.get('status') == 'OK':
                        dur = el.get('duration_in_traffic', el.get('duration', {}))
                        val = dur.get('value', float('inf'))
                        if val < best_val:
                            best_val, best_idx = val, idx
                return list(available_amb_qs)[best_idx].amb_id
            except Exception:
                pass  # fall through to straight-line

        # Straight-line fallback (Pythagorean approx, fine for city scale)
        import math
        best_idx, best_dist = 0, float('inf')
        for idx, amb in enumerate(available_amb_qs):
            d = math.sqrt((amb.LAT - call_lat)**2 + (amb.LONG - call_lng)**2)
            if d < best_dist:
                best_dist, best_idx = d, idx
        return list(available_amb_qs)[best_idx].amb_id

    def dispatch_ambulance(self, call_lat, call_lng):
        """
        Dispatch the nearest available ambulance to (call_lat, call_lng).
        Sets that ambulance to AVAILABLE=0 and moves it to the call location.
        """
        available = Current_ambulance.objects.filter(AVAILABLE=1)
        if not available.exists():
            raise ValueError("No available ambulances to dispatch.")

        chosen_id = self._find_nearest_ambulance(available, call_lat, call_lng)
        chosen    = Current_ambulance.objects.get(amb_id=chosen_id)

        # Archive position before moving
        Ambulance.objects.create(
            amb_id=chosen.amb_id, LAT=chosen.LAT,
            LONG=chosen.LONG, AVAILABLE=chosen.AVAILABLE
        )

        # Move to call location and mark unavailable
        chosen.LAT, chosen.LONG, chosen.AVAILABLE = call_lat, call_lng, 0
        chosen.save()

        Event_feed.objects.create(
            event_type='Dispatch',
            event_desc=(
                f"Amb #{chosen_id} dispatched to "
                f"{call_lat:.4f}, {call_lng:.4f}"
            ),
            unit=chosen_id, LAT=call_lat, LONG=call_lng
        )
        return chosen_id


class Current_emscall(models.Model):
    """The currently active incoming EMS call."""
    addr = models.CharField(max_length=200)
    LAT  = models.FloatField()
    LONG = models.FloatField()
    time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.addr

    # ── Geocoding ──────────────────────────────────────────────────────────────

    def geocode(self, address):
        """
        Geocode an address biased to Chandigarh tricity.
        Uses Google Maps API if GGL_API_KEY is set, otherwise raises a clear error.

        Location bias: bounding box around Chandigarh/Mohali/Panchkula tricity
        (30.60–30.82 N, 76.65–76.92 E) ensures "Punjab University" returns
        Panjab University Chandigarh, not Punjab University Lahore.
        """
        api_key = getattr(settings, 'GGL_API_KEY', '').strip()
        if not api_key:
            raise ValueError(
                "Google Maps API key is not set. "
                "Run the server with: $env:GGL_API_KEY='your_key_here'"
            )
        gmaps = googlemaps.Client(key=api_key)

        # Chandigarh tricity bounding box — biases results to the region
        # bounds format: (sw_lat, sw_lng, ne_lat, ne_lng)
        TRICITY_BOUNDS = {
            'southwest': {'lat': 30.60, 'lng': 76.65},
            'northeast': {'lat': 30.85, 'lng': 76.95},
        }

        result = gmaps.geocode(address, bounds=TRICITY_BOUNDS)

        # If biased result is outside tricity, try appending "Chandigarh" to the query
        if result:
            loc = result[0]['geometry']['location']
            in_tricity = (30.55 <= loc['lat'] <= 30.90 and 76.60 <= loc['lng'] <= 77.00)
            if not in_tricity:
                result2 = gmaps.geocode(address + ', Chandigarh, India', bounds=TRICITY_BOUNDS)
                if result2:
                    loc2 = result2[0]['geometry']['location']
                    in_tricity2 = (30.55 <= loc2['lat'] <= 30.90 and 76.60 <= loc2['lng'] <= 77.00)
                    if in_tricity2:
                        result = result2

        if not result:
            raise ValueError(f"Could not geocode: '{address}'. Try adding 'Chandigarh' to the address.")

        loc = result[0]['geometry']['location']
        address_found = result[0].get('formatted_address', '')

        # Final safety check — warn if still outside tricity
        if not (30.55 <= loc['lat'] <= 30.90 and 76.60 <= loc['lng'] <= 77.00):
            raise ValueError(
                f"Address '{address}' resolved to {address_found} which is outside "
                f"Chandigarh tricity. Please be more specific, e.g. add 'Chandigarh' or 'Mohali'."
            )

        return loc['lat'], loc['lng']

    def update_current_ems(self, address):
        """Archive current call, geocode new address, save."""
        # Archive
        for call in Current_emscall.objects.all():
            EMS_Calls.objects.get_or_create(
                ems_id=call.id,
                defaults=dict(addr=call.addr, LAT=call.LAT, LONG=call.LONG, time=call.time)
            )
        Current_emscall.objects.all().delete()

        lat, lng = self.geocode(address)
        new_call = Current_emscall.objects.create(addr=address, LAT=lat, LONG=lng)

        Event_feed.objects.create(
            event_type='Event',
            event_desc=f"EMS #{new_call.id} incoming: {address}",
            unit=new_call.id, LAT=lat, LONG=lng
        )
        return lat, lng

    # ── Map generation ─────────────────────────────────────────────────────────

    @staticmethod
    def build_map():
        """
        Build and return a Folium map as an HTML string.
        Shows ALL ambulances and current EMS calls from the DB.
        Uses fit_bounds so ALL markers are always visible, regardless of
        where the EMS call was geocoded.
        """
        ambulances = list(Current_ambulance.objects.all())
        calls      = list(Current_emscall.objects.all())

        # ── Collect all coordinates to compute bounds ─────────────────────────
        all_lats = [a.LAT  for a in ambulances] + [c.LAT  for c in calls]
        all_lngs = [a.LONG for a in ambulances] + [c.LONG for c in calls]

        # Fall back to Chandigarh centre if DB is empty
        if all_lats:
            min_lat, max_lat = min(all_lats), max(all_lats)
            min_lng, max_lng = min(all_lngs), max(all_lngs)
            centre_lat = (min_lat + max_lat) / 2
            centre_lng = (min_lng + max_lng) / 2
        else:
            centre_lat, centre_lng = CHANDIGARH_LAT, CHANDIGARH_LNG
            min_lat, max_lat = CHANDIGARH_LAT - 0.05, CHANDIGARH_LAT + 0.05
            min_lng, max_lng = CHANDIGARH_LNG - 0.05, CHANDIGARH_LNG + 0.05

        smap = folium.Map(
            location=[centre_lat, centre_lng],
            zoom_start=MAP_ZOOM,
            tiles=ESRI_TILES,
            attr=ESRI_ATTR
        )

        # Fit the map so all markers are visible
        smap.fit_bounds(
            [[min_lat - 0.01, min_lng - 0.01],
             [max_lat + 0.01, max_lng + 0.01]]
        )

        # ── Ambulance markers ─────────────────────────────────────────────────
        for amb in ambulances:
            if amb.AVAILABLE == 1:
                folium.Marker(
                    location=[amb.LAT, amb.LONG],
                    icon=folium.Icon(icon='plus', color='blue', prefix='fa'),
                    popup=folium.Popup(
                        f"<b>🚑 Ambulance #{amb.amb_id}</b><br>"
                        f"<span style='color:#2b6abe;font-weight:600;'>● Active</span><br>"
                        f"<small>Lat: {amb.LAT:.4f}, Lng: {amb.LONG:.4f}</small>",
                        max_width=220
                    ),
                    tooltip=f"Amb #{amb.amb_id} — Active"
                ).add_to(smap)
            else:
                folium.Marker(
                    location=[amb.LAT, amb.LONG],
                    icon=folium.Icon(icon='plus', color='gray', prefix='fa'),
                    popup=folium.Popup(
                        f"<b>🚑 Ambulance #{amb.amb_id}</b><br>"
                        f"<span style='color:#888;font-weight:600;'>⚫ Inactive / On Call</span><br>"
                        f"<small>Lat: {amb.LAT:.4f}, Lng: {amb.LONG:.4f}</small>",
                        max_width=220
                    ),
                    tooltip=f"Amb #{amb.amb_id} — Inactive"
                ).add_to(smap)

        # ── EMS call markers ──────────────────────────────────────────────────
        for call in calls:
            # Pulsing red circle
            folium.CircleMarker(
                location=[call.LAT, call.LONG],
                radius=14,
                color='#cc0000',
                weight=3,
                fill=True,
                fill_color='#ff0000',
                fill_opacity=0.7,
                popup=folium.Popup(
                    f"<b>🚨 EMS Call #{call.id}</b><br>"
                    f"{call.addr}<br>"
                    f"<small>Lat: {call.LAT:.4f}, Lng: {call.LONG:.4f}</small>",
                    max_width=260
                ),
                tooltip=f"🚨 EMS: {call.addr}"
            ).add_to(smap)

            # Orange 500 m alert zone
            folium.Circle(
                location=[call.LAT, call.LONG],
                radius=500,
                color='#ff6600',
                weight=2,
                fill=True,
                fill_color='#ff6600',
                fill_opacity=0.15,
                tooltip="⚠️ Alert zone (500 m radius)"
            ).add_to(smap)

        # ── Live legend ───────────────────────────────────────────────────────
        active_count   = sum(1 for a in ambulances if a.AVAILABLE == 1)
        inactive_count = sum(1 for a in ambulances if a.AVAILABLE == 0)
        call_count     = len(calls)

        import datetime as _dt
        ts = _dt.datetime.now().strftime('%H:%M:%S')

        legend_html = f"""
        <div style="position:fixed;bottom:24px;left:24px;z-index:9999;
                    background:rgba(255,255,255,0.96);padding:10px 16px;
                    border-radius:8px;border:2px solid #ccc;font-size:12px;
                    line-height:1.9;box-shadow:2px 2px 8px rgba(0,0,0,0.2);
                    min-width:200px;">
          <b style="font-size:13px;color:#1a1a2e;">🏥 SmartDispatch</b>
          <div style="font-size:9px;color:#999;margin-bottom:4px;">
            Updated: {ts}
          </div>
          <span style="color:#2b6abe;font-size:16px;">●</span>
          Active &nbsp;<b style="color:#2b6abe;">{active_count}</b><br>
          <span style="color:#888;font-size:16px;">●</span>
          Inactive &nbsp;<b style="color:#888;">{inactive_count}</b><br>
          <span style="color:#cc0000;font-size:16px;">●</span>
          EMS Call &nbsp;<b style="color:#cc0000;">{call_count}</b><br>
          <span style="color:#ff6600;font-size:16px;">○</span>
          Alert Zone (500 m)
        </div>
        """
        smap.get_root().html.add_child(folium.Element(legend_html))

        return smap.get_root().render()
