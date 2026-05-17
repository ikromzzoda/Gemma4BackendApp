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

DUSHANBE_LAT = 38.5598
DUSHANBE_LON = 68.7738

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
}

AQI_LABELS = {
    1: "Good",
    2: "Fair",
    3: "Moderate",
    4: "Unhealthy for Sensitive Groups",
    5: "Very Unhealthy",
}


SENSITIVE_CONDITIONS = {"Asthma", "COPD", "Bronchitis", "Heart Condition", "Allergies"}

import random

def _aqi_level(aqi):
    ranges = {
        1: (0, 50),
        2: (51, 100),
        3: (101, 150),
        4: (151, 200),
        5: (201, 300),
    }
    low, high = ranges.get(aqi, (0, 0))
    return random.randint(low, high)


def _aqi_label(aqi):
    return AQI_LABELS.get(aqi, "Unknown")


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
            'no': components.get('no'),
            'o3': components.get('o3'),
            'so2': components.get('so2'),
            'co': components.get('co'),
            'nh3': components.get('nh3'),
            'aqi': poll_data.get('main', {}).get('aqi'),  # пока сырой
            'dt': timezone.make_aware(datetime.fromtimestamp(poll_data.get('dt', 0))),
        }

        # конвертируем перед сохранением и возвратом
        api_data['aqi'] = _aqi_level(api_data['aqi'])

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
                no2=api_data['no2'], no=api_data['no'],
                o3=api_data['o3'], so2=api_data['so2'],
                co=api_data['co'], nh3=api_data['nh3'],
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
                    'no2': record.no2, 'no': record.no,
                    'o3': record.o3, 'so2': record.so2,
                    'co': record.co, 'nh3': record.nh3,
                    'aqi': _aqi_level(record.aqi),
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
                'no2': components.get('no2'), 'no': components.get('no'),
                'o3': components.get('o3'), 'so2': components.get('so2'),
                'co': components.get('co'), 'nh3': components.get('nh3'),
                'aqi': _aqi_level(poll_data.get('main', {}).get('aqi')),
                'dt': str(timezone.make_aware(datetime.fromtimestamp(poll_data.get('dt', 0)))),
            }

            twelve_hours_ago = timezone.now() - timedelta(hours=12)
            records = AirPollution.collection.filter('lat', '==', lat).filter('lon', '==', lon).fetch()

            last_record_12h = None
            all_records_list = []
            if records:
                records_list = list(records)
                records_list.sort(key=lambda x: x.created_at, reverse=True)
                for record in records_list:
                    row = {
                        'id': record.id, 'lat': record.lat, 'lon': record.lon,
                        'pm25': record.pm25, 'pm10': record.pm10,
                        'no2': record.no2, 'no': record.no,
                        'o3': record.o3, 'so2': record.so2,
                        'co': record.co, 'nh3': record.nh3,
                        'aqi': record.aqi,
                        'dt': str(record.dt), 'created_at': str(record.created_at),
                    }
                    all_records_list.append(row)
                    if last_record_12h is None and record.created_at >= twelve_hours_ago:
                        last_record_12h = row

            return JsonResponse({
                'location': {'lat': lat, 'lon': lon},
                'fresh_data_from_api': fresh_data,
                'last_cached_record': last_record_12h,
                'all_records_history': all_records_list,
                'total_records': len(all_records_list),
            }, status=200)

        except requests.exceptions.RequestException as e:
            return JsonResponse({'error': f'API request failed: {str(e)}'}, status=500)
        except Exception as e:
            return JsonResponse({'error': f'Error fetching data: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ─── new endpoints ─────────────────────────────────────────────────────────────

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

    try:
        resp = requests.get(
            f"http://api.openweathermap.org/data/2.5/air_pollution/forecast?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}",
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return JsonResponse({"status": "error", "error": "OpenWeatherMap API unavailable"}, status=503)

    try:
        now_utc = datetime.now(tz=dt_tz.utc)
        today_date = now_utc.date()
        tomorrow_date = today_date + timedelta(days=1)
        all_items = resp.json().get("list", [])

        if period == "7days":
            daily = defaultdict(list)
            for item in all_items:
                daily[datetime.fromtimestamp(item["dt"], tz=dt_tz.utc).date()].append(item)

            forecast_points = []
            for date, items in sorted(daily.items()):
                aqis = [i["main"]["aqi"] for i in items]
                pm25_vals = [i["components"]["pm2_5"] for i in items]
                pm10_vals = [i["components"]["pm10"] for i in items]
                max_aqi_day = max(aqis)
                forecast_points.append({
                    "date": str(date),
                    "aqi": _aqi_level(max_aqi_day),
                    "aqi_label": _aqi_label(max_aqi_day),
                    "pm25": round(sum(pm25_vals) / len(pm25_vals), 2),
                    "pm10": round(sum(pm10_vals) / len(pm10_vals), 2),
                })

            max_aqi = max((p["aqi"] for p in forecast_points), default=0)
            max_pm25 = max((p["pm25"] for p in forecast_points), default=0.0)
        else:
            target_date = today_date if period == "today" else tomorrow_date
            filtered = [i for i in all_items if datetime.fromtimestamp(i["dt"], tz=dt_tz.utc).date() == target_date]

            forecast_points = []
            for item in filtered:
                dt = datetime.fromtimestamp(item["dt"], tz=dt_tz.utc)
                components = item.get("components", {})
                aqi = item["main"]["aqi"]
                forecast_points.append({
                    "time": dt.strftime("%Y-%m-%d %H:%M"),
                    "aqi": _aqi_level(aqi),
                    "aqi_label": _aqi_label(aqi),
                    "pm25": components.get("pm2_5"),
                    "pm10": components.get("pm10"),
                })

            max_aqi = max((p["aqi"] for p in forecast_points), default=0)
            max_pm25 = max((p["pm25"] for p in forecast_points if p["pm25"] is not None), default=0.0)

        return JsonResponse({
            "status": "success",
            "data": {
                "city": city,
                "period": period,
                "max_aqi": max_aqi,                    # ✅ уже конвертированный
                "max_aqi_label": _aqi_label(          # берём label из исходного значения
                    max(
                        (i["main"]["aqi"] for i in all_items),
                        default=1
                    )
                ),
                "max_pm25": max_pm25,
                "forecast_points": forecast_points,
            },
        })

    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


def get_ai_advice(request):
    if request.method != 'GET':
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    city = request.GET.get("city", "Dushanbe")
    health_condition = request.GET.get("health_condition", "None")
    activity_level = request.GET.get("activity_level", "Active")

    coords, err = _validate_city(city)
    if err:
        return err

    valid_hc = ["Asthma", "Allergies", "Bronchitis", "COPD", "Heart Condition", "None", "Others"]
    valid_al = ["Sedentary", "Lightly Active", "Active", "Very Active"]

    if health_condition not in valid_hc:
        return JsonResponse({"status": "error", "error": "Invalid health_condition", "valid_values": valid_hc}, status=400)
    if activity_level not in valid_al:
        return JsonResponse({"status": "error", "error": "Invalid activity_level", "valid_values": valid_al}, status=400)

    lat, lon = coords["lat"], coords["lon"]

    try:
        resp = requests.get(
            f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}",
            timeout=10,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return JsonResponse({"status": "error", "error": "OpenWeatherMap API unavailable"}, status=503)

    try:
        aqi_raw = resp.json()["list"][0]["main"]["aqi"]  # 1..5, без * 10
        aqi = _aqi_level(aqi_raw)                        # например 73
        aqi_label = _aqi_label(aqi_raw)                  # "Moderate"

        return JsonResponse({
            "status": "success",
            "data": {
                "city": city,
                "aqi": aqi,
                "aqi_label": aqi_label,
                "health_condition": health_condition,
                "activity_level": activity_level,
                "advice": generate_advice(aqi_raw, health_condition, activity_level),
            },
        })
    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


import logging
logger = logging.getLogger(__name__)

import re

def _extract_json(raw: str) -> dict:
    """Извлекает первый валидный JSON объект из текста любой длины."""
    
    # 1. Пробуем напрямую
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Убираем ```json ... ``` обёртки
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Берём ПОСЛЕДНИЙ {...} в тексте (модель пишет JSON в конце)
    matches = list(re.finditer(r"\{[^{}]*\}", raw, re.DOTALL))
    for match in reversed(matches):  # с конца — там финальный JSON
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue

    raise ValueError("No valid JSON found in response")


def generate_advice(aqi, health_condition, activity_level):
    prompt = (
        f"You are an air quality health advisor.\n"
        f"AQI: {_aqi_level(aqi)} ({_aqi_label(aqi)})\n"
        f"Health condition: {health_condition}\n"
        f"Activity level: {activity_level}\n\n"
        f"Return ONLY this JSON, nothing else:\n"
        f'{{"advice": ["tip 1", "tip 2", "tip 3"]}}\n'
        f"Each tip: 1 short sentence. Max 3 tips."
    )

    raw = ""
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMMA4_MODEL}:generateContent",
            params={"key": settings.GEMMA4_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 200,
                    "temperature": 0.2,  # ниже = меньше "мыслей"
                }
            },
            timeout=(10, 60),
        )
        response.raise_for_status()

        raw = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        logger.debug(f"[AI] raw={raw!r}")

        parsed = _extract_json(raw)
        tips = parsed.get("advice", [])

        if isinstance(tips, list) and tips:
            return [str(t) for t in tips[:3]]
        return [str(tips)]

    except requests.exceptions.ReadTimeout:
        logger.error("generate_advice: TIMEOUT")
    except ValueError as e:
        logger.error(f"generate_advice: {e} | raw={raw[:200]!r}")
    except Exception as e:
        logger.error(f"generate_advice: {type(e).__name__}: {e}")

    return [f"Air quality is {_aqi_label(aqi)}. Check local guidelines for your health condition."]