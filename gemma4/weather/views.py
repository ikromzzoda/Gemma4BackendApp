from django.http import JsonResponse
from django.utils import timezone
import requests
from datetime import datetime, timedelta

from info.models import AirPollution
from info.views import (
    OPENWEATHERMAP_API_KEY,
    TAJIK_CITIES,
    _aqi_label,
    _validate_city,
)
from .models import WeatherData


def get_home_data(request):
    if request.method != 'GET':
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    city = request.GET.get("city", "Dushanbe")
    coords, err = _validate_city(city)
    if err:
        return err

    lat, lon = coords["lat"], coords["lon"]

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
    except requests.exceptions.RequestException:
        return JsonResponse({"status": "error", "error": "OpenWeatherMap API unavailable"}, status=503)

    try:
        poll_json = poll_resp.json()
        weather_json = weather_resp.json()

        poll_item = poll_json["list"][0]
        components = poll_item.get("components", {})
        aqi = poll_item["main"]["aqi"]

        weather_main = weather_json.get("main", {})
        weather_wind = weather_json.get("wind", {})
        weather_desc = weather_json.get("weather", [{}])[0]

        twelve_hours_ago = timezone.now() - timedelta(hours=12)
        last_poll = list(AirPollution.collection.filter("lat", "==", lat).filter("lon", "==", lon).fetch())
        save_poll = not (last_poll and last_poll[-1].created_at >= twelve_hours_ago)

        saved_pollution = False
        if save_poll:
            AirPollution(
                lat=lat, lon=lon,
                pm25=components.get("pm2_5"), pm10=components.get("pm10"),
                no2=components.get("no2"), no=components.get("no"),
                o3=components.get("o3"), so2=components.get("so2"),
                co=components.get("co"), nh3=components.get("nh3"),
                aqi=aqi,
                dt=timezone.make_aware(datetime.fromtimestamp(poll_item.get("dt", 0))),
            ).save()
            saved_pollution = True

        one_hour_ago = timezone.now() - timedelta(hours=1)
        last_weather = list(WeatherData.collection.filter("city", "==", city).fetch())
        save_weather = not (last_weather and last_weather[-1].created_at >= one_hour_ago)

        saved_weather = False
        if save_weather:
            WeatherData(
                city=city, lat=lat, lon=lon,
                temperature=weather_main.get("temp"),
                feels_like=weather_main.get("feels_like"),
                humidity=weather_main.get("humidity"),
                wind_speed=weather_wind.get("speed"),
                description=weather_desc.get("description"),
                icon=weather_desc.get("icon"),
            ).save()
            saved_weather = True

        return JsonResponse({
            "status": "success",
            "data": {
                "city": city,
                "lat": lat,
                "lon": lon,
                "aqi": aqi,
                "aqi_label": _aqi_label(aqi),
                "pm25": components.get("pm2_5"),
                "pm10": components.get("pm10"),
                "no2": components.get("no2"),
                "o3": components.get("o3"),
                "co": components.get("co"),
                "temperature": weather_main.get("temp"),
                "feels_like": weather_main.get("feels_like"),
                "humidity": weather_main.get("humidity"),
                "wind_speed": weather_wind.get("speed"),
                "weather_description": weather_desc.get("description"),
                "weather_icon": weather_desc.get("icon"),
                "saved_pollution_to_db": saved_pollution,
                "saved_weather_to_db": saved_weather,
            },
        })

    except Exception as e:
        return JsonResponse({"status": "error", "error": "Internal server error", "detail": str(e)}, status=500)


def get_map_data(request):
    if request.method != 'GET':
        return JsonResponse({"status": "error", "error": "Method not allowed"}, status=405)

    pollutant = request.GET.get("pollutant", "AQI")
    valid_pollutants = ["AQI", "PM2.5", "PM10", "O3", "NO2"]
    if pollutant not in valid_pollutants:
        return JsonResponse({"status": "error", "error": "Invalid pollutant", "valid_pollutants": valid_pollutants}, status=400)

    cities_data = []
    for city_name, coords in TAJIK_CITIES.items():
        lat, lon = coords["lat"], coords["lon"]
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

            poll_item = poll_resp.json()["list"][0]
            components = poll_item.get("components", {})
            aqi = poll_item["main"]["aqi"]
            temperature = weather_resp.json().get("main", {}).get("temp")

            cities_data.append({
                "city": city_name,
                "lat": lat,
                "lon": lon,
                "aqi": aqi,
                "aqi_label": _aqi_label(aqi),
                "pm25": components.get("pm2_5"),
                "pm10": components.get("pm10"),
                "o3": components.get("o3"),
                "no2": components.get("no2"),
                "temperature": temperature,
            })
        except requests.exceptions.RequestException:
            cities_data.append({"city": city_name, "lat": lat, "lon": lon, "error": "Data unavailable"})
        except Exception as e:
            cities_data.append({"city": city_name, "lat": lat, "lon": lon, "error": str(e)})

    return JsonResponse({"status": "success", "data": {"pollutant": pollutant, "cities": cities_data}})
