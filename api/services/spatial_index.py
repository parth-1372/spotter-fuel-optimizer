import json
import numpy as np
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Pre-geocoded stations bundled with the repo — no DB needed on deployment.
# Resolves to: <project_root>/data/fuel_stations.json
DATA_FILE = Path(__file__).resolve().parents[2] / 'data' / 'fuel_stations.json'


class SpatialIndex:
    """
    Singleton spatial index using pure numpy vectorised haversine.
    No scipy/gfortran dependency — works on any platform including Render free tier.

    With ~8,000 stations, a full vectorised haversine sweep takes ~1ms,
    which is faster than KDTree overhead for datasets of this size.
    """
    _instance = None

    def __init__(self):
        self.stations_data = []
        self.stations_by_id = {}
        self._lats = None   # numpy array of all latitudes
        self._lons = None   # numpy array of all longitudes
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

        self.stations_data = raw
        self.stations_by_id = {s['id']: s for s in raw}
        self._lats = np.array([s['lat'] for s in raw], dtype=np.float64)
        self._lons = np.array([s['lon'] for s in raw], dtype=np.float64)

        logger.info(f"Loaded {len(raw)} stations into numpy spatial index.")

    @staticmethod
    def _haversine_miles_vectorised(lat, lon, lats, lons):
        """
        Compute distance in miles from point (lat, lon) to all points in
        arrays (lats, lons) using vectorised numpy haversine.
        """
        R = 3958.8
        phi1 = np.radians(lat)
        phi2 = np.radians(lats)
        dphi = phi2 - phi1
        dlambda = np.radians(lons - lon)
        a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
        return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

    def query_radius(self, lat, lon, radius_miles):
        """
        Return all stations within radius_miles of (lat, lon).
        Pure numpy — no scipy dependency.
        """
        if self._lats is None or len(self._lats) == 0:
            return []

        distances = self._haversine_miles_vectorised(lat, lon, self._lats, self._lons)
        indices = np.where(distances <= radius_miles)[0]
        return [self.stations_data[i] for i in indices]
