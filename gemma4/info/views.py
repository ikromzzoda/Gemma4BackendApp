from django.http import JsonResponse
from django.utils import timezone
import requests
from datetime import datetime, timedelta
from .models import AirPollution
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env file from project root
env_path = Path(__file__).resolve().parent.parent.parent / '.env.local'
load_dotenv(dotenv_path=env_path)

# OpenWeatherMap API Key
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')

# Dushanbe coordinates
DUSHANBE_LAT = 38.5598
DUSHANBE_LON = 68.7738


def fetch_and_save_air_pollution(lat=None, lon=None):
    """
    Fetch air pollution data from OpenWeatherMap API
    Save to database only if the last record is older than 12 hours
    Always returns fresh data from API
    
    Args:
        lat (float, optional): Latitude. Defaults to Dushanbe
        lon (float, optional): Longitude. Defaults to Dushanbe
    
    Returns:
        dict: Fresh data from API with save status
    """
    # Use Dushanbe coordinates if not provided
    if lat is None:
        lat = DUSHANBE_LAT
    if lon is None:
        lon = DUSHANBE_LON
    
    try:
        # Always fetch from API
        url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract the main pollution list item (current data)
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
            'aqi': poll_data.get('main', {}).get('aqi'),
            'dt': timezone.make_aware(datetime.fromtimestamp(poll_data.get('dt', 0)))
        }
        
        # Check if last record is older than 12 hours
        twelve_hours_ago = timezone.now() - timedelta(hours=12)
        last_record = AirPollution.collection.filter('lat', '==', lat).filter('lon', '==', lon).fetch()
        
        should_save = True
        if last_record:
            last_list = list(last_record)
            if last_list:
                last = last_list[-1]
                if last.created_at >= twelve_hours_ago:
                    should_save = False
        
        # Save to Firestore only if needed
        if should_save:
            air_pollution = AirPollution(
                lat=api_data['lat'],
                lon=api_data['lon'],
                pm25=api_data['pm25'],
                pm10=api_data['pm10'],
                no2=api_data['no2'],
                no=api_data['no'],
                o3=api_data['o3'],
                so2=api_data['so2'],
                co=api_data['co'],
                nh3=api_data['nh3'],
                aqi=api_data['aqi'],
                dt=api_data['dt']
            )
            air_pollution.save()
            
            return {
                'message': 'Fresh data from API (saved to DB - 12+ hours passed)',
                'saved_to_db': True,
                'data': {
                    'lat': api_data['lat'],
                    'lon': api_data['lon'],
                    'pm25': api_data['pm25'],
                    'pm10': api_data['pm10'],
                    'no2': api_data['no2'],
                    'no': api_data['no'],
                    'o3': api_data['o3'],
                    'so2': api_data['so2'],
                    'co': api_data['co'],
                    'nh3': api_data['nh3'],
                    'aqi': api_data['aqi'],
                    'dt': str(api_data['dt']),
                }
            }, 201
        else:
            return {
                'message': 'Fresh data from API (not saved - less than 12 hours)',
                'saved_to_db': False,
                'data': {
                    'lat': api_data['lat'],
                    'lon': api_data['lon'],
                    'pm25': api_data['pm25'],
                    'pm10': api_data['pm10'],
                    'no2': api_data['no2'],
                    'no': api_data['no'],
                    'o3': api_data['o3'],
                    'so2': api_data['so2'],
                    'co': api_data['co'],
                    'nh3': api_data['nh3'],
                    'aqi': api_data['aqi'],
                    'dt': str(api_data['dt']),
                }
            }, 200
        
    except requests.exceptions.RequestException as e:
        return {'error': f'API request failed: {str(e)}'}, 500
    except Exception as e:
        return {'error': f'Error processing data: {str(e)}'}, 500

def get_air_pollution_data(request):
    """
    API endpoint to fetch and save air pollution data for Dushanbe
    """
    if request.method == 'GET':
        result, status_code = fetch_and_save_air_pollution()
        return JsonResponse(result, status=status_code)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def get_all_air_pollution(request):
    """
    Get all air pollution records from database
    """
    if request.method == 'GET':
        try:
            pollution_records = AirPollution.collection.fetch()
            records_list = []
            
            for record in pollution_records:
                records_list.append({
                    'id': record.id,
                    'lat': record.lat,
                    'lon': record.lon,
                    'pm25': record.pm25,
                    'pm10': record.pm10,
                    'no2': record.no2,
                    'no': record.no,
                    'o3': record.o3,
                    'so2': record.so2,
                    'co': record.co,
                    'nh3': record.nh3,
                    'aqi': record.aqi,
                    'dt': str(record.dt),
                    'created_at': str(record.created_at),
                })
            
            return JsonResponse({
                'count': len(records_list),
                'data': records_list
            }, status=200)
            
        except Exception as e:
            return JsonResponse({
                'error': f'Error fetching data: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_air_pollution_by_location(request):
    """
    Get air pollution records for Dushanbe
    Returns both fresh data from API and last cached record (within 12 hours)
    """
    if request.method == 'GET':
        try:
            # 1. Get fresh data from API
            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={DUSHANBE_LAT}&lon={DUSHANBE_LON}&appid={OPENWEATHERMAP_API_KEY}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get('list') or len(data['list']) == 0:
                return JsonResponse({'error': 'No data received from API'}, status=400)
            
            poll_data = data['list'][0]
            components = poll_data.get('components', {})
            
            fresh_data = {
                'lat': data.get('coord', {}).get('lat', DUSHANBE_LAT),
                'lon': data.get('coord', {}).get('lon', DUSHANBE_LON),
                'pm25': components.get('pm2_5'),
                'pm10': components.get('pm10'),
                'no2': components.get('no2'),
                'no': components.get('no'),
                'o3': components.get('o3'),
                'so2': components.get('so2'),
                'co': components.get('co'),
                'nh3': components.get('nh3'),
                'aqi': poll_data.get('main', {}).get('aqi'),
                'dt': str(timezone.make_aware(datetime.fromtimestamp(poll_data.get('dt', 0)))),
            }
            
            # 2. Get last record from DB (within 12 hours)
            twelve_hours_ago = timezone.now() - timedelta(hours=12)
            records = AirPollution.collection.filter('lat', '==', DUSHANBE_LAT).filter('lon', '==', DUSHANBE_LON).fetch()
            
            last_record_12h = None
            if records:
                records_list = list(records)
                # Find the most recent record within 12 hours
                for record in reversed(records_list):
                    if record.created_at >= twelve_hours_ago:
                        last_record_12h = {
                            'id': record.id,
                            'lat': record.lat,
                            'lon': record.lon,
                            'pm25': record.pm25,
                            'pm10': record.pm10,
                            'no2': record.no2,
                            'no': record.no,
                            'o3': record.o3,
                            'so2': record.so2,
                            'co': record.co,
                            'nh3': record.nh3,
                            'aqi': record.aqi,
                            'dt': str(record.dt),
                            'created_at': str(record.created_at),
                        }
                        break
            
            # 3. Get all records for reference
            all_records_list = []
            if records:
                records_list = list(records)
                records_list.sort(key=lambda x: x.created_at, reverse=True)
                for record in records_list:
                    all_records_list.append({
                        'id': record.id,
                        'lat': record.lat,
                        'lon': record.lon,
                        'pm25': record.pm25,
                        'pm10': record.pm10,
                        'no2': record.no2,
                        'no': record.no,
                        'o3': record.o3,
                        'so2': record.so2,
                        'co': record.co,
                        'nh3': record.nh3,
                        'aqi': record.aqi,
                        'dt': str(record.dt),
                        'created_at': str(record.created_at),
                    })
            
            return JsonResponse({
                'location': {'lat': DUSHANBE_LAT, 'lon': DUSHANBE_LON, 'city': 'Dushanbe'},
                'fresh_data_from_api': fresh_data,
                'last_cached_record': last_record_12h,
                'all_records_history': all_records_list,
                'total_records': len(all_records_list),
                'recent_records_count_12h': sum(1 for r in all_records_list if timezone.datetime.fromisoformat(r['created_at']) >= twelve_hours_ago)
            }, status=200)
            
        except requests.exceptions.RequestException as e:
            return JsonResponse({
                'error': f'API request failed: {str(e)}'
            }, status=500)
        except Exception as e:
            return JsonResponse({
                'error': f'Error fetching data: {str(e)}'
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)
