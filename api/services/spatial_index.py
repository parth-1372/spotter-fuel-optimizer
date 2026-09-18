import numpy as np
from scipy.spatial import KDTree
import logging
from api.models import FuelStation

logger = logging.getLogger(__name__)

class SpatialIndex:
    _instance = None
    
    def __init__(self):
        self.kdtree = None
        self.stations_data = []
        self._load_data()
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SpatialIndex()
        return cls._instance
        
    def _load_data(self):
        logger.info("Loading fuel stations into spatial index...")
        stations = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        
        coords = []
        self.stations_data = []
        
        for station in stations:
            coords.append([station.latitude, station.longitude])
            self.stations_data.append({
                'id': station.id,
                'name': station.truckstop_name,
                'address': station.address,
                'city': station.city,
                'state': station.state,
                'price': station.retail_price,
                'lat': station.latitude,
                'lon': station.longitude
            })
            
        if coords:
            self.kdtree = KDTree(np.array(coords))
            logger.info(f"Loaded {len(coords)} stations into KDTree.")
        else:
            logger.warning("No stations with coordinates found in DB. KDTree is empty.")
            self.kdtree = None

    def query_radius(self, lat, lon, radius_miles):
        """Find stations within radius_miles of (lat, lon)"""
        if not self.kdtree:
            return []
            
        # Approximation: 1 degree latitude is approx 69 miles
        radius_degrees = radius_miles / 69.0
        
        indices = self.kdtree.query_ball_point([lat, lon], r=radius_degrees)
        return [self.stations_data[i] for i in indices]
