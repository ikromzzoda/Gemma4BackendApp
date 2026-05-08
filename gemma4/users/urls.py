from django.urls import path
from . import views

urlpatterns = [
    path("users/create/", views.create_user, name="create_user"),
    path("users/<str:uid>/update/", views.update_user, name="update_user"),
    path("users/<str:uid>/", views.get_user_by_uid, name="get_user"),
]
