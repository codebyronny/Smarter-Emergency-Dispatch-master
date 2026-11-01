"""
SmartDispatch map views — Chandigarh edition.

  /rawmap/     → sidebar + iframe that loads /maponly/
  /maponly/    → pure Folium HTML (map iframe source, auto-refreshes every 10s)
  /map-state/  → JSON API polled by sidebar JS every 5s for live status counts
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.clickjacking import xframe_options_exempt
from django.http import HttpResponse, JsonResponse

from .models import Current_emscall, Current_ambulance, Event_feed
from .forms import CurrentCallForm, CurrentAmbulanceForm


@xframe_options_exempt
def current_map(request):
    """Dispatch sidebar — rendered inside the outer sb_admin iframe."""
    if request.method == 'POST':
        form  = CurrentCallForm(request.POST, prefix='call')
        form2 = CurrentAmbulanceForm(request.POST, prefix='amb')

        if 'call_submit' in request.POST and form.is_valid():
            address = form.cleaned_data.get('addr', '').strip()
            if address:
                try:
                    call_obj = Current_emscall()
                    lat, lng = call_obj.update_current_ems(address)
                    amb = Current_ambulance()
                    amb.dispatch_ambulance(lat, lng)
                    amb.update_amb_locs()
                    messages.success(request, f"✅ Dispatched ambulance to: {address}")
                except ValueError as e:
                    messages.error(request, f"⚠️ {e}")
                except Exception as e:
                    messages.error(request, f"❌ Error: {e}")
            else:
                messages.warning(request, "Please enter an address.")

        elif 'amb_submit' in request.POST and form2.is_valid():
            input_id = form2['amb_id'].value()
            try:
                amb = Current_ambulance()
                amb.update_amb_status_only(input_id, 1)
                amb.update_amb_locs()
                messages.success(request, f"✅ Ambulance #{input_id} is now active.")
            except Exception as e:
                messages.error(request, f"❌ Error: {e}")

        return redirect('current_map')

    # GET
    form           = CurrentCallForm(prefix='call')
    form2          = CurrentAmbulanceForm(prefix='amb')
    recent_events  = Event_feed.objects.order_by('-time')[:10]
    active_count   = Current_ambulance.objects.filter(AVAILABLE=1).count()
    inactive_count = Current_ambulance.objects.filter(AVAILABLE=0).count()
    call_count     = Current_emscall.objects.count()

    return render(request, 'map/dispatch.html', {
        'form':                form,
        'form2':               form2,
        'recent_events_query': recent_events,
        'active_count':        active_count,
        'inactive_count':      inactive_count,
        'call_count':          call_count,
    })


@xframe_options_exempt
def map_only(request):
    """
    Pure Folium map HTML — the iframe src inside dispatch.html.
    Generated fresh from DB on every request so it always reflects
    the live ambulance positions and EMS calls.
    """
    html = Current_emscall.build_map()
    # Prevent browser from caching the map so auto-refresh always gets new data
    response = HttpResponse(html, content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response['Pragma'] = 'no-cache'
    return response


def map_state_api(request):
    """
    JSON endpoint polled every 5 s by sidebar JS.
    Returns live ambulance positions, EMS calls, status counts and events feed.
    No auth needed — local dev only.
    """
    ambulances = list(
        Current_ambulance.objects.order_by('amb_id').values(
            'amb_id', 'LAT', 'LONG', 'AVAILABLE'
        )
    )
    calls = list(
        Current_emscall.objects.values('id', 'addr', 'LAT', 'LONG')
    )
    events = []
    for ev in Event_feed.objects.order_by('-time')[:10]:
        events.append({
            'type': ev.event_type,
            'desc': ev.event_desc,
            'unit': ev.unit,
            'time': ev.time.strftime('%d/%m %H:%M'),
        })

    return JsonResponse({
        'ambulances':    ambulances,
        'calls':         calls,
        'events':        events,
        'active_count':  sum(1 for a in ambulances if a['AVAILABLE'] == 1),
        'inactive_count':sum(1 for a in ambulances if a['AVAILABLE'] == 0),
        'call_count':    len(calls),
    })
