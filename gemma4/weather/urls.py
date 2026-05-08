from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.get_home_data, name='get_home_data'),
    path('map/', views.get_map_data, name='get_map_data'),
]
