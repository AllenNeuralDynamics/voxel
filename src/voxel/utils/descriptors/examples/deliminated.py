from voxel.utils.descriptors.deliminated import deliminated_property
from voxel.utils.descriptors.new.annotated import PropertyInfo, annotated_property

windspeed_info = PropertyInfo("m/s", "Wind speed")


def dynamic_windspeed_max(obj) -> float:
    return 100.0 if obj.temperature < 20.0 else 50.0


class WeatherData:
    def __init__(self):
        self._temperature: float = 0.0
        self._wind_speed: float = 0.0
        self._humidity: float = 0.0

    @annotated_property(unit="°C", description="Air temperature")
    def temperature(self) -> float:
        return self._temperature

    @temperature.setter
    def temperature(self, value: float):
        self._temperature = value

    @deliminated_property(0.0, dynamic_windspeed_max, 0.1, windspeed_info)
    def wind_speed(self) -> float:
        return self._wind_speed

    @wind_speed.setter
    def wind_speed(self, value: float):
        self._wind_speed = value

    @annotated_property(unit="%", description="Relative humidity")
    def humidity(self) -> float:
        return self._humidity

    @humidity.setter
    def humidity(self, value: float):
        self._humidity = value

    def on_property_update_notice(self, msg: str) -> None:
        print(f"Property Notice: {msg}")


# Usage example
weather = WeatherData()
weather.temperature = 25.0
weather.wind_speed = 5.0
weather.humidity = 60.0

print(f"Temperature: {weather.temperature}")
print(f"Temperature info: Unit - {weather.temperature.info.unit}, Description - {weather.temperature.info.description}")
print(f"Wind speed: {weather.wind_speed} - [{weather.wind_speed.minimum} ... {weather.wind_speed.maximum}]")
print(f"Wind speed info: Unit - {weather.wind_speed.info.unit}, Description - {weather.wind_speed.info.description}")
print(f"Humidity: {weather.humidity}")
print(f"Humidity info: Unit - {weather.humidity.info.unit}, Description - {weather.humidity.info.description}")
weather.temperature = 15.0
print(f"Wind speed: {weather.wind_speed} - [{weather.wind_speed.minimum} ... {weather.wind_speed.maximum}]")
weather.wind_speed = 101.0

print(f"Temperature value: {weather.temperature.value}")
print(f"Temperature unit: {weather.temperature.info.unit}")
print(type(weather).temperature.info.unit)
print(f"Wind speed: {weather.wind_speed}")
print(f"Weather data windspeed Info: {WeatherData.wind_speed.info}")
print(f"Wind speed description: {weather.wind_speed.info.description}")
print(f"Humidity + 10: {weather.humidity + 10}")
print(f"Is temperature > 20? {weather.temperature > 20}")
