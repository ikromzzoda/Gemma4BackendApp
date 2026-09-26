from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
import requests
from datetime import datetime, timedelta, timezone as dt_tz
from collections import defaultdict
from .models import AirPollution
import os
from dotenv import load_dotenv
from pathlib import Path
import json

env_path = Path(__file__).resolve().parent.parent.parent / '.env.local'
load_dotenv(dotenv_path=env_path)

OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
AIRVISUAL_API_KEY = os.getenv('AIRVISUAL_API_KEY', '')

DUSHANBE_LAT = 38.5598
DUSHANBE_LON = 68.7738

AQI_LABELS = {
    1: "Good",
    2: "Moderate",
    3: "Unhealthy for Sensitive Groups",
    4: "Unhealthy",
    5: "Very Unhealthy",
}


SENSITIVE_CONDITIONS = {"Asthma", "COPD", "Bronchitis", "Heart Condition", "Allergies"}

TAJIK_CITIES = {
    "Dushanbe":    {"lat": 38.5598, "lon": 68.7738},
    "Khujand":     {"lat": 40.2827, "lon": 69.6223},
    "Bokhtar":     {"lat": 37.8298, "lon": 68.7792},
    "Kulob":       {"lat": 37.9113, "lon": 69.7836},
    "Istaravshan": {"lat": 39.9138, "lon": 69.0047},
    "Panjakent":   {"lat": 39.4942, "lon": 67.6106},
    "Khorugh":     {"lat": 37.4897, "lon": 71.5528},
    "Tursunzoda":  {"lat": 38.5595, "lon": 68.2228},
    "Hisor":       {"lat": 38.5260, "lon": 68.5428},
    "Dangara":     {"lat": 38.0958, "lon": 69.3400},
    "Baljuvon":    {"lat": 38.1900, "lon": 69.6600},
}

def get_aqi_by_coords(lat, lon):
    if not AIRVISUAL_API_KEY:
        return None
    try:
        url = f"https://api.airvisual.com/v2/nearest_city?lat={lat}&lon={lon}&key={AIRVISUAL_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "success":
            return data["data"]["current"]["pollution"]["aqius"]
        return None
    except requests.exceptions.RequestException:
        return None


def _aqi_label(aqi):
    return AQI_LABELS.get(aqi, "Unknown")


def _aqi_label_us(aqi):
    if aqi is None:
        return "Unknown"
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"



def _owm_aqi_label(aqi):
    if aqi is None:
        return "Unknown"
    if aqi == 1:
        return "Good"
    elif aqi == 2:
        return "Moderate"
    elif aqi == 3:
        return "Unhealthy for Sensitive Groups"
    elif aqi == 4:
        return "Unhealthy"
    elif aqi == 5:
        return "Very Unhealthy"
    return _aqi_label_us(aqi)
    

def _validate_city(city):
    if city not in TAJIK_CITIES:
        return None, JsonResponse({
            "status": "error",
            "error": "Invalid city",
            "valid_cities": list(TAJIK_CITIES.keys()),
        }, status=400)
    return TAJIK_CITIES[city], None


# ─── existing helper (used by Celery task) ────────────────────────────────────

def fetch_and_save_air_pollution(lat=None, lon=None):
    if lat is None:
        lat = DUSHANBE_LAT
    if lon is None:
        lon = DUSHANBE_LON

    try:
        url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get('list') or len(data['list']) == 0:
            return {'error': 'No data received from API'}, 400

        poll_data = data['list'][0]
        components = poll_data.get('components', {})

        api_data = {
            'lat': data.get('coord', {}).get('lat', lat),
            'lon': data.get('coord', {}).get('lon', lon),
            'pm25': components.get('pm2_5'),
            'pm10': components.get('pm10'),
            'no2': components.get('no2'),
            'o3': components.get('o3'),
            'so2': components.get('so2'),
            'co': components.get('co'),
            'aqi': get_aqi_by_coords(lat, lon),
            'dt': timezone.make_aware(datetime.fromtimestamp(poll_data.get('dt', 0))),
        }

        # конвертируем перед сохранением и возвратом
        api_data['aqi'] = get_aqi_by_coords(lat, lon) #_aqi_level(api_data['aqi'])

        twelve_hours_ago = timezone.now() - timedelta(hours=12)
        last_record = AirPollution.collection.filter('lat', '==', lat).filter('lon', '==', lon).fetch()

        should_save = True
        if last_record:
            last_list = list(last_record)
            if last_list and last_list[-1].created_at >= twelve_hours_ago:
                should_save = False

        if should_save:
            air_pollution = AirPollution(
                lat=api_data['lat'], lon=api_data['lon'],
                pm25=api_data['pm25'], pm10=api_data['pm10'],
                no2=api_data['no2'],
                o3=api_data['o3'], so2=api_data['so2'],
                co=api_data['co'],
                aqi=api_data['aqi'], dt=api_data['dt'],
            )
            air_pollution.save()
            return {'message': 'Saved to DB', 'saved_to_db': True, 'data': {k: str(v) if isinstance(v, datetime) else v for k, v in api_data.items()}}, 201
        else:
            return {'message': 'Not saved (less than 12 hours)', 'saved_to_db': False, 'data': {k: str(v) if isinstance(v, datetime) else v for k, v in api_data.items()}}, 200

    except requests.exceptions.RequestException as e:
        return {'error': f'API request failed: {str(e)}'}, 500
    except Exception as e:
        return {'error': f'Error processing data: {str(e)}'}, 500


# ─── existing endpoints ────────────────────────────────────────────────────────

def get_air_pollution_data(request):
    if request.method == 'GET':
        city = request.GET.get('city', 'Dushanbe')
        coords, err = _validate_city(city)
        
        if err:
            return err
        result, status_code = fetch_and_save_air_pollution(lat=coords['lat'], lon=coords['lon'])
        if isinstance(result, dict):
            result['city'] = city
        return JsonResponse(result, status=status_code)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_all_air_pollution(request):
    if request.method == 'GET':
        try:
            pollution_records = AirPollution.collection.fetch()
            records_list = []
            for record in pollution_records:
                records_list.append({
                    'id': record.id,
                    'lat': record.lat, 'lon': record.lon,
                    'pm25': record.pm25, 'pm10': record.pm10,   
                    'no2': record.no2, 
                    'o3': record.o3, 'so2': record.so2,
                    'co': record.co,
                    'aqi': record.aqi,
                    'dt': str(record.dt),
                    'created_at': str(record.created_at),
                })
            return JsonResponse({'count': len(records_list), 'data': records_list}, status=200)
        except Exception as e:
            return JsonResponse({'error': f'Error fetching data: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)



def get_air_pollution_by_location(request):
    if request.method == 'GET':
        try:
            lat_param = request.GET.get('lat')
            lon_param = request.GET.get('lon')

            if lat_param is None or lon_param is None:
                return JsonResponse({'error': 'Missing required parameters: lat and lon'}, status=400)

            try:
                lat = float(lat_param)
                lon = float(lon_param)
            except ValueError:
                return JsonResponse({'error': 'Invalid lat/lon values: must be numbers'}, status=400)

            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                return JsonResponse({'error': 'lat must be between -90 and 90, lon between -180 and 180'}, status=400)

            # Проверяем — есть ли запись за последний час
            one_hour_ago = timezone.now() - timedelta(hours=1)
            records = AirPollution.collection.filter('lat', '==', lat).filter('lon', '==', lon).fetch()

            recent_record = None
            if records:
                records_list = sorted(list(records), key=lambda r: r.created_at, reverse=True)
                if records_list and records_list[0].created_at >= one_hour_ago:
                    recent_record = records_list[0]

            # Если есть свежая запись в БД — возвращаем её
            if recent_record:
                return JsonResponse({
                    'location': {'lat': lat, 'lon': lon},
                    'data': {
                        'lat': recent_record.lat,
                        'lon': recent_record.lon,
                        'pm25': recent_record.pm25,
                        'pm10': recent_record.pm10,
                        'no2': recent_record.no2,
                        # 'no': recent_record.no,
                        'o3': recent_record.o3,
                        'so2': recent_record.so2,
                        'co': recent_record.co,
                        # 'nh3': recent_record.nh3,
                        'aqi': recent_record.aqi,
                        'dt': str(recent_record.dt),
                    },
                }, status=200)

            # Нет свежей записи — получаем из API
            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get('list') or len(data['list']) == 0:
                return JsonResponse({'error': 'No data received from API'}, status=400)

            poll_data = data['list'][0]
            components = poll_data.get('components', {})
            fresh_data = {
                'lat': data.get('coord', {}).get('lat', lat),
                'lon': data.get('coord', {}).get('lon', lon),
                'pm25': components.get('pm2_5'), 'pm10': components.get('pm10'),
                'no2': components.get('no2'), 
                # 'no': components.get('no'),
                'o3': components.get('o3'), 'so2': components.get('so2'),
                'co': components.get('co'), 
                # 'nh3': components.get('nh3'),
                'aqi': get_aqi_by_coords(lat, lon),
                'dt': timezone.make_aware(datetime.fromtimestamp(poll_data.get('dt', 0))),
            }

            # Сохраняем в БД
            air_pollution = AirPollution(
                lat=fresh_data['lat'], lon=fresh_data['lon'],
                pm25=fresh_data['pm25'], pm10=fresh_data['pm10'],
                no2=fresh_data['no2'], no=fresh_data['no'],
                o3=fresh_data['o3'], so2=fresh_data['so2'],
                co=fresh_data['co'], nh3=fresh_data['nh3'],
                aqi=fresh_data['aqi'], dt=fresh_data['dt'],
            )
            air_pollution.save()

            return JsonResponse({
                'location': {'lat': lat, 'lon': lon},
                'data': {**fresh_data, 'dt': str(fresh_data['dt'])},
            }, status=200)

        except requests.exceptions.RequestException as e:
            return JsonResponse({'error': f'API request failed: {str(e)}'}, status=500)
        except Exception as e:
            return JsonResponse({'error': f'Error fetching data: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


from concurrent.futures import ThreadPoolExecutor

def get_forecast_data(request):
    if request.method != 'GET':
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    city = request.GET.get("city", "Dushanbe")
    period = request.GET.get("period", "today")

    coords, err = _validate_city(city)
    if err:
        return err

    if period not in ("today", "tomorrow", "7days"):
        return JsonResponse({"status": "error", "error": "Invalid period", "valid_periods": ["today", "tomorrow", "7days"]}, status=400)

    lat, lon = coords["lat"], coords["lon"]
    now_utc = datetime.now(tz=dt_tz.utc)
    current_hour = now_utc.strftime("%Y-%m-%d %H:00")


    def fetch_current_aqi():
        return get_aqi_by_coords(lat, lon)

    def fetch_owm_forecast():
        return requests.get(
            f"http://api.openweathermap.org/data/2.5/air_pollution/forecast?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}",
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        aqi_future = executor.submit(fetch_current_aqi)
        owm_future = executor.submit(fetch_owm_forecast)
        current_aqi = aqi_future.result()
        owm_resp = owm_future.result()

    try:
        owm_resp.raise_for_status()
    except requests.exceptions.RequestException:
        return JsonResponse({"status": "error", "error": "OpenWeatherMap API unavailable"}, status=503)

    try:
        today_date = now_utc.date()
        tomorrow_date = today_date + timedelta(days=1)
        all_items = owm_resp.json().get("list", [])

        if period == "7days":
            daily = defaultdict(list)
            for item in all_items:
                daily[datetime.fromtimestamp(item["dt"], tz=dt_tz.utc).date()].append(item)

            forecast_points = []
            for date, items in sorted(daily.items()):
                pm25_vals = [i["components"]["pm2_5"] for i in items]
                pm10_vals = [i["components"]["pm10"] for i in items]
                avg_pm25 = round(sum(pm25_vals) / len(pm25_vals), 2)
                avg_pm10 = round(sum(pm10_vals) / len(pm10_vals), 2)

                aqi_value = get_aqi_by_coords(lat, lon)

                forecast_points.append({
                    "date": str(date),
                    "aqi": aqi_value,
                    "aqi_label": _aqi_label_us(aqi_value),
                    "pm25": avg_pm25,
                    "pm10": avg_pm10,
                })

            max_aqi = max((p["aqi"] for p in forecast_points if p["aqi"]), default=0)
            max_pm25 = max((p["pm25"] for p in forecast_points), default=0.0)

        else:
            target_date = today_date if period == "today" else tomorrow_date
            filtered = [i for i in all_items if datetime.fromtimestamp(i["dt"], tz=dt_tz.utc).date() == target_date]

            forecast_points = []
            for item in filtered:
                dt = datetime.fromtimestamp(item["dt"], tz=dt_tz.utc)
                components = item.get("components", {})
                pm25 = components.get("pm2_5")
                item_hour = dt.strftime("%Y-%m-%d %H:00")

                aqi_value = get_aqi_by_coords(lat, lon)

                forecast_points.append({
                    "time": dt.strftime("%Y-%m-%d %H:%M"),
                    "aqi": aqi_value,
                    "aqi_label": _aqi_label_us(aqi_value),
                    "pm25": pm25,
                    "pm10": components.get("pm10"),
                })

            max_aqi = max((p["aqi"] for p in forecast_points if p["aqi"]), default=0)
            max_pm25 = max((p["pm25"] for p in forecast_points if p["pm25"] is not None), default=0.0)

        return JsonResponse({
            "status": "success",
            "data": {
                "city": city,
                "period": period,
                "max_aqi": max_aqi,
                "max_aqi_label": _aqi_label_us(max_aqi),
                "max_pm25": max_pm25,
                "forecast_points": forecast_points,
            },
        })

    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


def _normalize_optional_param(value, valid_values=None, default=None):
    if value is None:
        return default

    value = str(value).strip()
    if not value:
        return default

    if valid_values is not None:
        allowed = {item.strip() for item in str(valid_values).split('|') if item.strip()}
        if value not in allowed:
            return default

    return value


def get_ai_advice(request):
    if request.method != 'GET':
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    city = _normalize_optional_param(request.GET.get("city"), default="Dushanbe")
    health_condition = request.GET.get("health_condition") or "Not specified"
    activity_level = request.GET.get("activity_level") or "General"

    coords = TAJIK_CITIES.get(city)
    if coords is None:
        city = "Dushanbe"
        coords = TAJIK_CITIES[city]

    lat, lon = coords["lat"], coords["lon"]

    try:
        owm_resp = requests.get(
            f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}",
            timeout=10,
        )
        owm_resp.raise_for_status()

        owm_data = owm_resp.json()
        owm_item = (owm_data.get("list") or [{}])[0]
        aqi_value = owm_item.get("main", {}).get("aqi")
        aqi_label = _owm_aqi_label(aqi_value)

        advice = generate_advice(aqi_label=aqi_label, health_condition=health_condition, activity_level=activity_level)

        return JsonResponse({
            "status": "success",
            "data": {
                "city": city,
                "aqi_label": aqi_label,
                "health_condition": health_condition,
                "activity_level": activity_level,
                "advice": advice,
            },
        })
    except requests.exceptions.RequestException as e:
        logger.error(f"get_ai_advice: OpenWeather request failed: {e}")
        return JsonResponse({
            "status": "error",
            "error": "OpenWeather API unavailable",
            "detail": str(e),
        }, status=503)
    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


def generate_advice(aqi=None, health_condition=None, activity_level=None, aqi_label=None):
    health_condition = health_condition or "Not specified"
    activity_level = activity_level or "General"
    aqi_label = aqi_label or "Unknown"

    api_key = (getattr(settings, "GEMMA4_API_KEY", "") or os.getenv("GEMMA4_API_KEY", "") or "").strip()
    if not api_key:
        logger.error("generate_advice: GEMMA4_API_KEY is missing or empty")
        return []

    prompt = (
        "You are a concise air quality health advisor for a city in Tajikistan.\n"
        f"Air quality level: {aqi_label}\n"
        f"Health condition: {health_condition}\n"
        f"Activity level: {activity_level}\n\n"
        "Give exactly 2 short advice sentences in English.\n"
        "Each sentence must be one sentence, under 15 words, clear, practical, and tailored to the air quality level and condition.\n"
        "Do not use placeholder words, labels, or example text like 'tip 1', 'tip 2', 'sentence 1', 'sentence 2', 'example', or 'placeholder'.\n"
        "Output must be plain JSON only, with a top-level key named 'advice' and exactly two strings.\n"
        "No markdown, no code fences, no bullets, no explanations, no extra text.\n"
        "Return only this structure: {\"advice\": [\"short sentence 1\", \"short sentence 2\"]}."
    )

    raw = ""
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMMA4_MODEL}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 400,
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                }
            },
            timeout=(20, 60),
        )
        response.raise_for_status()

        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        logger.debug(f"[AI] raw={raw!r}")

        parsed = _extract_json(raw)
        tips = parsed.get("advice", [])

        if isinstance(tips, list):
            clean_tips = []
            for item in tips[:2]:
                text = str(item).strip()
                lowered = text.lower()
                blocked = (
                    "tip 1" in lowered or "tip 2" in lowered or
                    "sentence 1" in lowered or "sentence 2" in lowered or
                    "example" in lowered or "placeholder" in lowered or
                    "real advice" in lowered
                )
                if text and not blocked:
                    clean_tips.append(text)
            if clean_tips:
                return clean_tips[:2]

        return []

    except requests.exceptions.ReadTimeout:
        logger.error("generate_advice: TIMEOUT")
    except requests.exceptions.HTTPError as e:
        logger.error(f"generate_advice: HTTPError: {e}")
    except ValueError as e:
        logger.error(f"generate_advice: {e} | raw={raw[:200]!r}")
    except Exception as e:
        logger.error(f"generate_advice: {type(e).__name__}: {e}")

    return []


import logging
logger = logging.getLogger(__name__)

import re

def _extract_json(raw: str) -> dict:
    """Извлекает первый валидный JSON объект из текста любой длины."""
    if raw is None:
        raise ValueError("No valid JSON found in response")

    text = raw.strip()
    if not text:
        raise ValueError("No valid JSON found in response")

    # 1. Пробуем напрямую
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Убираем ```json ... ``` обёртки
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Ищем JSON внутри текста, даже если перед ним есть markdown/bullets
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 4. Берём последний {...} в тексте
    matches = list(re.finditer(r"\{[^{}]*\}", text, re.DOTALL))
    for match in reversed(matches):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue

    raise ValueError("No valid JSON found in response")
