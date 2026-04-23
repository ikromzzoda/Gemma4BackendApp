from django.http import JsonResponse
from .models import User


# Получить ВСЕХ пользователей
def get_all_users(request):
    users = User.collection.fetch()  # автоматически тянет из Firestore
    users_list = []
    for user in users:
        users_list.append({
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "email": user.email,
            "date_of_birth": str(user.date_of_birth),
            "location": user.location,
        })
    return JsonResponse({"users": users_list})


# Получить одного пользователя по username
def get_user_by_username(request, username):
    user = User.collection.filter("username", "==", username).get()
    if not user:
        return JsonResponse({"error": "User not found"}, status=404)
    return JsonResponse({
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "email": user.email,
        "date_of_birth": str(user.date_of_birth),
        "location": user.location,
    })