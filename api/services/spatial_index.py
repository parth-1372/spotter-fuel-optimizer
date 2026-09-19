import numpy as np
from scipy.spatial import KDTree
import logging
from api.models import FuelStation

logger = logging.getLogger(__name__)


class SpatialIndex:
    """
    Singleton that loads all geocoded FuelStation records from the DB into a
    scipy KDTree for sub-millisecond spatial radius queries.
    """
    _instance = None

    def __init__(self):
        self.kdtree = None
        self.stations_data = []
        self.stations_by_id = {}  # O(1) lookup by DB primary key
        self._load_data()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SpatialIndex()
        return cls._instance

    def _load_data(self):
        logger.info("Loading fuel stations into spatial index…")
        stations = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

        coords = []
        self.stations_data = []
        self.stations_by_id = {}

        for station in stations:
            record = {
                'id': station.id,
                'name': station.truckstop_name,
                'address': station.address,
                'city': station.city,
                'state': station.state,
                'price': station.retail_price,
                'lat': station.latitude,
                'lon': station.longitude,
            }
            coords.append([station.latitude, station.longitude])
            self.stations_data.append(record)
            self.stations_by_id[station.id] = record  # O(1) dict lookup

        if coords:
            self.kdtree = KDTree(np.array(coords))
            logger.info(f"Loaded {len(coords)} stations into KDTree.")
        else:
            logger.warning("No stations with coordinates found in DB. KDTree is empty.")
            self.kdtree = None

    def query_radius(self, lat, lon, radius_miles):
        """
        Return all stations within `radius_miles` of the given point.
        Uses a cosine-corrected degree approximation for better accuracy
        across different US latitudes.
        """
        if not self.kdtree:
            return []

        # Latitude degree: ~69 miles universally
        # Longitude degree varies with latitude; use cosine correction.
        lat_radius = radius_miles / 69.0
        lon_radius = radius_miles / (69.0 * max(np.cos(np.radians(lat)), 0.01))

        # KDTree uses Euclidean distance, so we query with the larger of the
        # two semi-axes (lat_radius) and then filter precisely below.
        search_radius = max(lat_radius, lon_radius)
        indices = self.kdtree.query_ball_point([lat, lon], r=search_radius)

        results = []
        for i in indices:
            s = self.stations_data[i]
            # Precise degree-to-mile filter after broad KDTree query
            dlat = abs(s['lat'] - lat) * 69.0
            dlon = abs(s['lon'] - lon) * 69.0 * np.cos(np.radians(lat))
            if np.sqrt(dlat**2 + dlon**2) <= radius_miles:
                results.append(s)

        return results
