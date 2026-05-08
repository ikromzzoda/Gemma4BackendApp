from fireo import models


class AirPollution(models.Model):
    """Model to store air pollution data from OpenWeatherMap API"""
    lat = models.NumberField(required=True)
    lon = models.NumberField(required=True)

    # Main pollutants (µg/m³)
    pm25 = models.NumberField(required=False)  # PM2.5
    pm10 = models.NumberField(required=False)  # PM10
    no2 = models.NumberField(required=False)   # Nitrogen Dioxide
    no = models.NumberField(required=False)    # Nitrogen Monoxide
    o3 = models.NumberField(required=False)    # Ozone
    so2 = models.NumberField(required=False)   # Sulfur Dioxide
    co = models.NumberField(required=False)    # Carbon Monoxide
    nh3 = models.NumberField(required=False)   # Ammonia

    # AQI (Air Quality Index, OpenWeatherMap scale 1-5)
    aqi = models.NumberField(required=False)

    dt = models.DateTime(required=True)
    created_at = models.DateTime(auto=True)

    class Meta:
        collection_name = "air_pollution"
