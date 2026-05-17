from celery import shared_task
from users.models import User
from info.views import OPENWEATHERMAP_API_KEY, TAJIK_CITIES, _aqi_label, _validate_city
from django.conf import settings
import requests
import logging
import firebase_admin.messaging as fcm_messaging

logger = logging.getLogger(__name__)

FALLBACK_ADVICE = {
    1: "Air quality is excellent in {city} today. Great time to go outside!",
    2: "Air quality is fair in {city}. Safe to go outside, enjoy your day!",
    3: "Air quality is moderate in {city}. Sensitive groups should limit outdoor time.",
    4: "Air quality is unhealthy in {city}. Consider wearing a mask outdoors.",
    5: "Air quality is very unhealthy in {city}. Avoid going outside if possible.",
}

NOTIFICATION_SYSTEM_PROMPT = (
    "You are Airi, an air quality assistant. Give short, "
    "friendly outdoor air quality advice. Be concise — max 2 sentences."
)


def _get_ai_advice(city, aqi, aqi_label, temp, description, pm25, pm10, age_group, health_condition, activity_level):
    user_message = (
        f"Current conditions in {city}: AQI {aqi} ({aqi_label}), "
        f"temperature {temp}°C, weather: {description}, PM2.5: {pm25} µg/m³, "
        f"PM10: {pm10} µg/m³. User profile: age group {age_group}, health condition "
        f"{health_condition}, activity level {activity_level}. "
        f"Give a short friendly advice about going outside right now."
    )
    payload = {
        "systemInstruction": {"parts": [{"text": NOTIFICATION_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {
            "maxOutputTokens": 150,
            "temperature": 0.7,
        },
    }
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMMA4_MODEL}:generateContent",
            params={"key": settings.GEMMA4_API_KEY},
            json=payload,
            timeout=(10, 30),
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"_get_ai_advice: {type(e).__name__}: {e}")
        return None


@shared_task
def send_weather_advice_notifications():
    logger.info("send_weather_advice_notifications: starting")

    try:
        all_users = list(User.collection.fetch())
    except Exception as e:
        logger.error(f"send_weather_advice_notifications: failed to fetch users: {e}")
        return

    notified = 0
    failed = 0

    for user in all_users:
        if not getattr(user, 'notificationsEnabled', False):
            continue
        fcm_token = getattr(user, 'fcmToken', '') or ''
        if not fcm_token:
            continue

        city = getattr(user, 'location', 'Dushanbe') or 'Dushanbe'
        age_group = getattr(user, 'ageGroup', 'Unknown')
        health_condition = getattr(user, 'healthCondition', 'None')
        activity_level = getattr(user, 'activityLevel', 'Active')

        coords, err = _validate_city(city)
        if err:
            city = 'Dushanbe'
            coords = TAJIK_CITIES['Dushanbe']

        lat, lon = coords['lat'], coords['lon']

        try:
            poll_resp = requests.get(
                f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}",
                timeout=10,
            )
            poll_resp.raise_for_status()
            weather_resp = requests.get(
                f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}&units=metric",
                timeout=10,
            )
            weather_resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"send_weather_advice_notifications: weather fetch failed for {city}: {e}")
            failed += 1
            continue

        try:
            poll_item = poll_resp.json()["list"][0]
            components = poll_item.get("components", {})
            aqi_raw = poll_item["main"]["aqi"]
            aqi = aqi_raw * 10
            pm25 = components.get("pm2_5", 0)
            pm10 = components.get("pm10", 0)

            weather_json = weather_resp.json()
            weather_main = weather_json.get("main", {})
            weather_desc = weather_json.get("weather", [{}])[0]
            temperature = weather_main.get("temp", 0)
            description = weather_desc.get("description", "")
        except Exception as e:
            logger.error(f"send_weather_advice_notifications: data parse failed for {city}: {e}")
            failed += 1
            continue

        aqi_label = _aqi_label(aqi_raw)

        ai_advice = _get_ai_advice(
            city, aqi, aqi_label, temperature, description,
            pm25, pm10, age_group, health_condition, activity_level,
        )
        if not ai_advice:
            fallback_template = FALLBACK_ADVICE.get(aqi_raw, FALLBACK_ADVICE[5])
            ai_advice = fallback_template.format(city=city)

        try:
            message = fcm_messaging.Message(
                notification=fcm_messaging.Notification(
                    title="🌤 Air Quality Update",
                    body=ai_advice,
                ),
                data={
                    "type": "weather_advice",
                    "city": city,
                    "aqi": str(aqi),
                    "aqi_label": aqi_label,
                    "temperature": str(temperature),
                },
                token=fcm_token,
            )
            fcm_messaging.send(message)
            notified += 1
        except Exception as e:
            logger.error(
                f"send_weather_advice_notifications: FCM send failed for user "
                f"{getattr(user, 'uid', '?')}: {e}"
            )
            failed += 1

    logger.info(f"send_weather_advice_notifications: done — notified={notified}, failed={failed}")
