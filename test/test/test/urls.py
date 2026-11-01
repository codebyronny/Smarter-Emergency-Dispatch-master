from django.urls import path, include
from django.contrib import admin
from map.views import map_only, map_state_api

urlpatterns = [
    # SB Admin shell (home, about, charts, map wrapper)
    path('', include('django_sb_admin.urls')),
    path('admin/', admin.site.urls),
    # /rawmap/ → dispatch sidebar (current_map view)
    path('rawmap/', include('map.urls')),
    # /maponly/ → pure Folium HTML served into the sidebar iframe
    path('maponly/', map_only, name='map_only'),
    # /map-state/ → JSON API for live sidebar polling
    path('map-state/', map_state_api, name='map_state_api'),
]
