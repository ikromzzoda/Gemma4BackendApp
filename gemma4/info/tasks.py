# tasks.py
from celery import shared_task
from .views import fetch_and_save_air_pollution
import logging

logger = logging.getLogger(__name__)


@shared_task
def fetch_air_pollution_periodic():
    """
    Celery periodic task - запускается каждые 12 часов автоматически
    Сохраняет свежие данные загрязнения воздуха в БД
    """
    logger.info('Starting periodic air pollution fetch...')
    result, status_code = fetch_and_save_air_pollution()
    
    if status_code in [201, 200]:
        logger.info(f'Periodic fetch success: {result.get("message")}')
    else:
        logger.error(f'Periodic fetch failed: {result}')