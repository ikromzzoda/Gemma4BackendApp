from django.urls import path
from . import views

urlpatterns = [
    # path("users/", views.get_all_users, name="get_all_users"),
    path("users/<str:username>/", views.get_user_by_username, name="get_user_by_username"),
]