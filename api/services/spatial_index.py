import json
import numpy as np
from scipy.spatial import KDTree
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the pre-geocoded stations file committed to the repo.
# This means zero DB dependency and zero geocoding wait on deployment.
DATA_FILE = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'fuel_stations.json'


class SpatialIndex:
    """
    Singleton that loads all pre-geocoded FuelStation records from a bundled
    JSON file into a scipy KDTree for sub-millisecond spatial radius queries.

    Loading from a JSON file (instead of the DB) means:
    - No database required for station data
    - Works immediately on any deployment (Render, Railway, etc.)
    - No 2-3 hour geocoding step needed on the server
    """
    _instance = None

    def __init__(self):
        self.kdtree = None
        self.stations_data = []
        self.stations_by_id = {}
        self._load_data()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SpatialIndex()
        return cls._instance

    def _load_data(self):
        if not DATA_FILE.exists():
            logger.error(
                f"Fuel station data file not found at {DATA_FILE}. "
                "Run: python manage.py export_stations"
            )
            return

        logger.info(f"Loading fuel stations from {DATA_FILE}…")
        with open(DATA_FILE, 'r') as f:
            raw = json.load(f)

        coords = []
        self.stations_data = []
        self.stations_by_id = {}

        for record in raw:
            coords.append([record['lat'], record['lon']])
            self.stations_data.append(record)
            self.stations_by_id[record['id']] = record

        if coords:
            self.kdtree = KDTree(np.array(coords))
            logger.info(f"Loaded {len(coords)} stations into KDTree from JSON file.")
        else:
            logger.warning("No station data found in JSON file.")
            self.kdtree = None

    def query_radius(self, lat, lon, radius_miles):
        """
        Return all stations within radius_miles of (lat, lon).
        Uses cosine-corrected longitude approximation for accuracy across US latitudes.
        """
        if not self.kdtree:
            return []

        lat_radius = radius_miles / 69.0
        lon_radius = radius_miles / (69.0 * max(np.cos(np.radians(lat)), 0.01))
        search_radius = max(lat_radius, lon_radius)

        indices = self.kdtree.query_ball_point([lat, lon], r=search_radius)

        results = []
        for i in indices:
            s = self.stations_data[i]
            dlat = abs(s['lat'] - lat) * 69.0
            dlon = abs(s['lon'] - lon) * 69.0 * np.cos(np.radians(lat))
            if np.sqrt(dlat**2 + dlon**2) <= radius_miles:
                results.append(s)

        return results
