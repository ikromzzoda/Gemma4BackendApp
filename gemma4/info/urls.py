from django.urls import path
from . import views

urlpatterns = [
    # Fetch data from API and save to database (Dushanbe)
    path('air-pollution/', views.get_air_pollution_data, name='get_air_pollution_data'),
    
    # Get all air pollution records
    path('air-pollution/all/', views.get_all_air_pollution, name='get_all_air_pollution'),
    
    # Get air pollution records for Dushanbe
    path('air-pollution/dushanbe/', views.get_air_pollution_by_location, name='get_air_pollution_by_location'),
]
