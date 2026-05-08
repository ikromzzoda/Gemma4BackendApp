from django.urls import path
from . import views

urlpatterns = [
    path('air-pollution/', views.get_air_pollution_data, name='get_air_pollution_data'),
    path('air-pollution/all/', views.get_all_air_pollution, name='get_all_air_pollution'),
    path('air-pollution/location/', views.get_air_pollution_by_location, name='get_air_pollution_by_location'),
    path('forecast/', views.get_forecast_data, name='get_forecast_data'),
    path('advice/', views.get_ai_advice, name='get_ai_advice'),
]
