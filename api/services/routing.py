import openrouteservice
from geopy.geocoders import Nominatim
import polyline
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ORS_API_KEY = os.environ.get('ORS_API_KEY', '')

# Module-level singletons — created once per process, not per request
_ors_client = None
_geolocator = Nominatim(user_agent="fuel_optimizer_api_v1")


def _get_ors_client():
    """Lazy singleton for the ORS client — avoids re-creating on every request."""
    global _ors_client
    if _ors_client is None:
        if not ORS_API_KEY:
            raise ValueError("ORS_API_KEY is not set. Please add it to the .env file.")
        _ors_client = openrouteservice.Client(key=ORS_API_KEY, timeout=30)
    return _ors_client


# Approximate bounding boxes for USA (continental + Alaska + Hawaii)
_USA_BOUNDS = [
    (24.0, 50.0, -125.0, -66.0),   # Continental US
    (51.0, 72.0, -170.0, -129.0),  # Alaska
    (18.0, 23.0, -161.0, -154.0),  # Hawaii
]

def _is_within_usa(lat, lon):
    """Return True if (lat, lon) falls within any USA bounding box."""
    return any(
        min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
        for min_lat, max_lat, min_lon, max_lon in _USA_BOUNDS
    )


def get_coordinates(location_name: str):
    """
    Geocode a US city/address string to (lat, lon).
    Returns None if:
    - Location cannot be resolved
    - Result falls outside USA bounding boxes
    - Result has low Nominatim importance score (< 0.4) — catches gibberish/partial matches
    """
    try:
        results = _geolocator.geocode(
            f"{location_name}, USA",
            timeout=8,
            country_codes='us',
            exactly_one=True,
        )
        if not results:
            return None

        lat, lon = results.latitude, results.longitude

        # Reject if outside USA territory
        if not _is_within_usa(lat, lon):
            logger.warning(f"'{location_name}' geocoded outside USA — rejecting.")
            return None

        # Nominatim's importance score: real cities score ~0.5–1.0
        # Street/partial/fuzzy matches score < 0.4 — reject them
        importance = results.raw.get('importance', 0)
        if importance < 0.4:
            logger.warning(
                f"'{location_name}' resolved with low importance ({importance:.3f}) "
                f"— likely a fuzzy match, rejecting."
            )
            return None

        logger.debug(f"Geocoded '{location_name}' -> ({lat}, {lon}) importance={importance:.3f}")
        return (lat, lon)

    except Exception as e:
        logger.error(f"Geocoding failed for '{location_name}': {e}")
    return None



def fetch_route(start_coords: tuple, end_coords: tuple):
    """
    Make exactly ONE call to OpenRouteService to fetch the driving route.

    Args:
        start_coords: (lat, lon)
        end_coords:   (lat, lon)

    Returns:
        route_geometry : list of [lat, lon] — decoded polyline
        distance_miles : float — total route distance
    """
    try:
        client = _get_ors_client()
        # ORS requires [lon, lat] ordering
        coordinates = [
            (start_coords[1], start_coords[0]),
            (end_coords[1], end_coords[0]),
        ]

        response = client.directions(
            coordinates=coordinates,
            profile='driving-car',
            format='json',
            units='mi',
            geometry=True,
            instructions=False,
        )

        if not response or not response.get('routes'):
            logger.warning("ORS returned an empty routes list.")
            return None, 0

        route = response['routes'][0]
        distance_miles = route['summary']['distance']
        decoded = polyline.decode(route['geometry'])          # list of (lat, lon) tuples
        route_geometry = [[pt[0], pt[1]] for pt in decoded]  # convert to list of lists

        logger.info(f"Route fetched: {len(route_geometry)} points, {distance_miles:.1f} mi")
        return route_geometry, distance_miles

    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
        raise
    except openrouteservice.exceptions.ApiError as ae:
        logger.error(f"ORS API error: {ae}")
        return None, 0
    except Exception as e:
        logger.error(f"Unexpected routing error: {e}")
        return None, 0
