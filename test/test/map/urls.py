from django.urls import path
from . import views

urlpatterns = [
    path('', views.current_map, name='current_map'),
    path('maponly/', views.map_only, name='map_only'),
]
