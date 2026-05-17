# myproject/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gemma4.settings')

app = Celery('gemma4')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Celery Beat schedule для периодических задач
app.conf.beat_schedule = {
    'fetch-air-pollution-every-12-hours': {
        'task': 'info.tasks.fetch_air_pollution_periodic',
        'schedule': 12 * 60 * 60,  # 12 часов в секундах (43200)
    },
    'send-weather-advice-07': {
        'task': 'weather.tasks.send_weather_advice_notifications',
        'schedule': crontab(hour=7, minute=0),
        'options': {'timezone': 'Asia/Dushanbe'},
    },
    'send-weather-advice-10': {
        'task': 'weather.tasks.send_weather_advice_notifications',
        'schedule': crontab(hour=10, minute=0),
        'options': {'timezone': 'Asia/Dushanbe'},
    },
    'send-weather-advice-13': {
        'task': 'weather.tasks.send_weather_advice_notifications',
        'schedule': crontab(hour=13, minute=0),
        'options': {'timezone': 'Asia/Dushanbe'},
    },
    'send-weather-advice-16': {
        'task': 'weather.tasks.send_weather_advice_notifications',
        'schedule': crontab(hour=16, minute=0),
        'options': {'timezone': 'Asia/Dushanbe'},
    },
    'send-weather-advice-19': {
        'task': 'weather.tasks.send_weather_advice_notifications',
        'schedule': crontab(hour=19, minute=0),
        'options': {'timezone': 'Asia/Dushanbe'},
    },
}