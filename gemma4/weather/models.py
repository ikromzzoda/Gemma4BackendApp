from fireo import models


class WeatherData(models.Model):
    """Current weather data from OpenWeatherMap"""
    city = models.TextField(required=True)
    lat = models.NumberField(required=True)
    lon = models.NumberField(required=True)
    temperature = models.NumberField(required=False)   # °C
    feels_like = models.NumberField(required=False)    # °C
    humidity = models.NumberField(required=False)      # %
    wind_speed = models.NumberField(required=False)    # m/s
    description = models.TextField(required=False)
    icon = models.TextField(required=False)
    created_at = models.DateTime(auto=True)

    class Meta:
        collection_name = "weather_data"
