"""@tool get_weather(location), get_forecast(location, days) — OpenWeatherMap"""

import requests
from langchain_core.tools import tool

from config import settings

BASE_URL = "https://api.openweathermap.org/data/2.5"


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a city or location.

    Args:
        location: City name, e.g. "Lahore" or "Lahore,PK"
    """
    settings.require("openweathermap_api_key")
    response = requests.get(
        f"{BASE_URL}/weather",
        params={"q": location, "appid": settings.openweathermap_api_key, "units": "metric"},
        timeout=10,
    )
    if not response.ok:
        return f"Couldn't get weather for {location}: {response.json().get('message', response.text)}"
    data = response.json()
    return (
        f"{location}: {data['weather'][0]['description']}, {data['main']['temp']}°C "
        f"(feels like {data['main']['feels_like']}°C), {data['main']['humidity']}% humidity"
    )


@tool
def get_forecast(location: str, days: int = 3) -> str:
    """Get a multi-day weather forecast for a city or location.

    Args:
        location: City name, e.g. "Lahore" or "Lahore,PK"
        days: Number of days to forecast (1-5)
    """
    settings.require("openweathermap_api_key")
    days = max(1, min(days, 5))
    response = requests.get(
        f"{BASE_URL}/forecast",
        params={"q": location, "appid": settings.openweathermap_api_key, "units": "metric", "cnt": days * 8},
        timeout=10,
    )
    if not response.ok:
        return f"Couldn't get forecast for {location}: {response.json().get('message', response.text)}"
    data = response.json()
    daily = data["list"][::8][:days]
    lines = [f"{d['dt_txt'].split()[0]}: {d['weather'][0]['description']}, {d['main']['temp']}°C" for d in daily]
    return f"{days}-day forecast for {location}:\n" + "\n".join(lines)
