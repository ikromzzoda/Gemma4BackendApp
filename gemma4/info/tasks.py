# tasks.py
from celery import shared_task
from django.core.cache import cache
from django.conf import settings
from .views import fetch_and_save_air_pollution
import logging

logger = logging.getLogger(__name__)

LAST_REQUEST_KEY = 'last_frontend_request_time'  # ключ в кэше
ONE_HOUR = 3600  # секунды


@shared_task
def auto_fetch_if_idle():
    """
    Запускается каждые N минут.
    Если с момента последнего запроса прошёл час — делает запрос сам.
    """
    last_request = cache.get(LAST_REQUEST_KEY)

    if last_request is None:
        # Фронтенд не делал запросов вообще — запускаем автоматически
        logger.info('No frontend request detected. Auto-fetching...')
        _do_auto_fetch()
    else:
        from django.utils import timezone
        elapsed = (timezone.now() - last_request).total_seconds()

        if elapsed >= ONE_HOUR:
            logger.info(f'No request for {elapsed:.0f}s. Auto-fetching...')
            _do_auto_fetch()
        else:
            logger.info(f'Last request was {elapsed:.0f}s ago. Skipping.')


def _do_auto_fetch():
    """Выполняет сам запрос с дефолтными координатами"""
    lat = settings.AUTO_FETCH_LAT
    lon = settings.AUTO_FETCH_LON
    api_key = settings.OPENWEATHER_API_KEY

    result, status_code = fetch_and_save_air_pollution(lat, lon, api_key)

    if status_code == 201:
        logger.info(f'Auto-fetch success: {result}')
    else:
        logger.error(f'Auto-fetch failed: {result}')