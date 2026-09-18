import openrouteservice
from geopy.geocoders import Nominatim
import polyline
import logging
from django.conf import settings
import os

logger = logging.getLogger(__name__)

# Use a default fallback key or environment variable. 
# NOTE: User should ideally set ORS_API_KEY in environment variables.
ORS_API_KEY = os.environ.get('ORS_API_KEY', '5b3ce3597851110001cf62489c72e2cf38f9464e83c21a1f0a2d5345') # Demo key for testing purposes, replace in prod

def get_coordinates(location_name):
    """Geocode a location string to (lat, lon)"""
    geolocator = Nominatim(user_agent="fuel_optimizer_api")
    try:
        location = geolocator.geocode(f"{location_name}, USA", timeout=5)
        if location:
            return (location.latitude, location.longitude)
    except Exception as e:
        logger.error(f"Failed to geocode {location_name}: {e}")
    return None

def fetch_route(start_coords, end_coords):
    """
    Fetch route geometry from OpenRouteService.
    start_coords, end_coords: (lat, lon)
    Returns: list of [lat, lon] points, total_distance_miles
    """
    try:
        client = openrouteservice.Client(key=ORS_API_KEY)
        # ORS takes coords as [lon, lat]
        coords = [
            (start_coords[1], start_coords[0]),
            (end_coords[1], end_coords[0])
        ]
        
        routes = client.directions(
            coordinates=coords,
            profile='driving-car',
            format='json',
            units='mi',
            geometry=True,
            instructions=False
        )
        
        if not routes or 'routes' not in routes or len(routes['routes']) == 0:
            return None, 0
            
        route_summary = routes['routes'][0]
        geometry_encoded = route_summary['geometry']
        distance_miles = route_summary['summary']['distance']
        
        # Decode polyline (returns list of (lat, lon))
        decoded = polyline.decode(geometry_encoded)
        # Convert to list of lists [lat, lon]
        route_geometry = [[pt[0], pt[1]] for pt in decoded]
        
        return route_geometry, distance_miles
        
    except Exception as e:
        logger.error(f"Routing error: {e}")
        return None, 0
