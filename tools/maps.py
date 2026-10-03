"""@tool geocode, get_directions.

Uses free OpenStreetMap/Nominatim by default (geopy) — no API key
needed. If you specifically need richer place/business data, swap in
Google Maps Platform using GOOGLE_MAPS_API_KEY (see the Tech Stack
Guide for the current free-tier terms since Google restructured this
in March 2025).
"""

from geopy.geocoders import Nominatim
from langchain_core.tools import tool

# geopy's default timeout is 1 second, which Nominatim often exceeds (-> GeocoderTimedOut).
_geolocator = Nominatim(user_agent="jarvis-personal-assistant", timeout=10)


@tool
def geocode(address: str) -> str:
    """Look up the coordinates and full address for a place.

    Args:
        address: A place name or partial address, e.g. "Lahore" or "Eiffel Tower"
    """
    location = _geolocator.geocode(address)
    if location is None:
        return f"Couldn't find a location for '{address}'."
    return f"{location.address} ({location.latitude}, {location.longitude})"


@tool
def get_directions(origin: str, destination: str) -> str:
    """Get straight-line distance between two places. (For real turn-by-turn
    directions, add an OpenRouteService or Google Directions call here —
    Nominatim itself only geocodes, it doesn't route.)

    Args:
        origin: Starting place name or address
        destination: Destination place name or address
    """
    from geopy.distance import geodesic

    start = _geolocator.geocode(origin)
    end = _geolocator.geocode(destination)
    if start is None or end is None:
        return "Couldn't find one or both locations."

    distance_km = geodesic((start.latitude, start.longitude), (end.latitude, end.longitude)).km
    return f"{origin} to {destination}: {distance_km:.1f} km in a straight line (not driving distance)."
