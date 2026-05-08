import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User

VALID_AGE_GROUPS = ["Under 18", "18 - 24", "25 - 34", "35 - 44", "45 - 54", "55 - 64", "65+"]
VALID_HEALTH_CONDITIONS = ["Asthma", "Allergies", "Bronchitis", "COPD", "Heart Condition", "None", "Others"]
VALID_ACTIVITY_LEVELS = ["Sedentary", "Lightly Active", "Active", "Very Active"]
VALID_LOCATIONS = [
    "Dushanbe", "Khujand", "Bokhtar", "Kulob", "Istaravshan",
    "Panjakent", "Khorugh", "Tursunzoda", "Hisor",
]
UPDATABLE_FIELDS = [
    "location", "ageGroup", "healthCondition", "activityLevel",
    "notificationsEnabled", "dailyForecastEnabled", "healthTipsEnabled", "profilePicUrl",
]


def _user_to_dict(user):
    return {
        "uid": user.uid,
        "firstName": user.firstName,
        "surname": user.surname,
        "email": user.email,
        "location": user.location,
        "ageGroup": user.ageGroup,
        "healthCondition": user.healthCondition,
        "activityLevel": user.activityLevel,
        "notificationsEnabled": user.notificationsEnabled,
        "dailyForecastEnabled": user.dailyForecastEnabled,
        "healthTipsEnabled": user.healthTipsEnabled,
        "profilePicUrl": user.profilePicUrl,
    }


def get_user_by_uid(request, uid):
    if request.method != "GET":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        user = User.collection.filter("uid", "==", uid).get()
        if not user:
            return JsonResponse({"status": "error", "error": "User not found"}, status=404)
        return JsonResponse({"status": "success", "data": _user_to_dict(user)})
    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


@csrf_exempt
def update_user(request, uid):
    if request.method != "PUT":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"status": "error", "error": "Invalid JSON body"}, status=400)
    try:
        user = User.collection.filter("uid", "==", uid).get()
        if not user:
            return JsonResponse({"status": "error", "error": "User not found"}, status=404)

        if "ageGroup" in body and body["ageGroup"] not in VALID_AGE_GROUPS:
            return JsonResponse({"status": "error", "error": "Invalid ageGroup", "valid_values": VALID_AGE_GROUPS}, status=400)
        if "healthCondition" in body and body["healthCondition"] not in VALID_HEALTH_CONDITIONS:
            return JsonResponse({"status": "error", "error": "Invalid healthCondition", "valid_values": VALID_HEALTH_CONDITIONS}, status=400)
        if "activityLevel" in body and body["activityLevel"] not in VALID_ACTIVITY_LEVELS:
            return JsonResponse({"status": "error", "error": "Invalid activityLevel", "valid_values": VALID_ACTIVITY_LEVELS}, status=400)
        if "location" in body and body["location"] not in VALID_LOCATIONS:
            return JsonResponse({"status": "error", "error": "Invalid location", "valid_values": VALID_LOCATIONS}, status=400)

        for field in UPDATABLE_FIELDS:
            if field in body:
                setattr(user, field, body[field])
        user.update()

        return JsonResponse({"status": "success", "data": _user_to_dict(user)})
    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


@csrf_exempt
def create_user(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({"status": "error", "error": "Invalid JSON body"}, status=400)
    try:
        for field in ["uid", "firstName", "surname", "email"]:
            if field not in body:
                return JsonResponse({"status": "error", "error": f"Missing required field: {field}"}, status=400)

        user = User(
            uid=body["uid"],
            firstName=body["firstName"],
            surname=body["surname"],
            email=body["email"],
            location=body.get("location", "Dushanbe"),
            ageGroup=body.get("ageGroup", "18 - 24"),
            healthCondition=body.get("healthCondition", "None"),
            activityLevel=body.get("activityLevel", "Active"),
            notificationsEnabled=body.get("notificationsEnabled", True),
            dailyForecastEnabled=body.get("dailyForecastEnabled", True),
            healthTipsEnabled=body.get("healthTipsEnabled", False),
            profilePicUrl=body.get("profilePicUrl", ""),
        )
        user.save()
        return JsonResponse({"status": "success", "data": _user_to_dict(user)}, status=201)
    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)
