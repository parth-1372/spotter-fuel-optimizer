import numpy as np
from geopy.distance import geodesic
import logging
from .spatial_index import SpatialIndex

logger = logging.getLogger(__name__)

VEHICLE_RANGE = 500   # miles – max range on a full tank
MPG = 10              # miles per gallon (fixed per requirements)
TANK_CAPACITY = VEHICLE_RANGE / MPG  # 50 gallons


def _haversine_miles(lat1, lon1, lat2, lon2):
    """
    Vectorised haversine in miles. Accepts floats or numpy arrays.
    Much faster than geopy.geodesic for hot inner loops.
    """
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def _build_route_distances(route_geometry):
    """
    Pre-compute cumulative distances along the route polyline.
    Returns a numpy array of shape (N,) where route_dist[i] is
    the total distance (miles) from route_geometry[0] to route_geometry[i].
    """
    pts = np.array(route_geometry)  # shape (N, 2) — [lat, lon]
    lats1, lons1 = pts[:-1, 0], pts[:-1, 1]
    lats2, lons2 = pts[1:, 0], pts[1:, 1]
    segment_dists = _haversine_miles(lats1, lons1, lats2, lons2)
    return np.concatenate([[0.0], np.cumsum(segment_dists)])


def optimize_fuel_stops(route_geometry, total_distance):
    """
    Greedy lookahead algorithm to find the cheapest fuel stop sequence.

    Strategy:
    - Vehicle starts with a full tank (500-mile range).
    - At each iteration we look ahead up to (current_range − 50 mi safety buffer)
      and collect all candidate stations reachable within that window.
    - We score each candidate by its fuel price plus a small penalty for detour
      distance, then pick the best one.
    - We repeat until the destination is reachable on the remaining fuel.

    One call to ORS per request — no additional external calls here.

    Returns:
        (stops: list[dict], total_cost: float)
        Returns ([], -1) on unrecoverable error.
    """
    index = SpatialIndex.get_instance()

    if not index.kdtree or not route_geometry:
        logger.error("Spatial index not ready or empty route.")
        return [], 0

    route_dist = _build_route_distances(route_geometry)  # cumulative dist array

    stops = []
    total_cost = 0.0
    current_range = VEHICLE_RANGE          # fuel remaining in miles
    current_dist = 0.0                     # distance covered so far
    current_pt_idx = 0                     # index into route_geometry
    MAX_ITER = 50                          # safety cap to prevent infinite loops

    for _ in range(MAX_ITER):
        remaining = total_distance - current_dist

        # ── Are we close enough to the destination? ──────────────────────────
        if current_range >= remaining:
            break

        # ── Window: look ahead up to (range − 50 mi buffer) ──────────────────
        SAFE_BUFFER = 50
        window_end = current_dist + max(current_range - SAFE_BUFFER, current_range * 0.5)

        # Indices of route points inside the lookahead window (after current pos)
        look_start = current_dist + current_range * 0.4  # avoid stops too close
        mask = (route_dist >= look_start) & (route_dist <= window_end)
        lookahead_indices = np.where(mask)[0]

        if len(lookahead_indices) == 0:
            # Fallback: any point we can still reach
            mask = (route_dist > current_dist) & (route_dist <= current_dist + current_range)
            lookahead_indices = np.where(mask)[0]

        if len(lookahead_indices) == 0:
            logger.error("No reachable route points found — route may exceed vehicle range.")
            return [], -1

        # ── Query stations near the lookahead corridor ─────────────────────────
        candidate_ids = set()
        # Sub-sample lookahead points to avoid redundant KDTree queries
        step = max(1, len(lookahead_indices) // 30)
        for idx in lookahead_indices[::step]:
            pt = route_geometry[idx]
            for s in index.query_radius(pt[0], pt[1], 30):
                candidate_ids.add(s['id'])

        # Fallback: widen radius if nothing found
        if not candidate_ids:
            furthest = route_geometry[lookahead_indices[-1]]
            for s in index.query_radius(furthest[0], furthest[1], 60):
                candidate_ids.add(s['id'])

        if not candidate_ids:
            logger.error("No fuel stations found near the route corridor.")
            return [], -1

        # ── Score each candidate ───────────────────────────────────────────────
        best_station = None
        best_score = float('inf')
        best_detour = 0.0
        best_closest_idx = current_pt_idx

        cur_lat = route_geometry[current_pt_idx][0]
        cur_lon = route_geometry[current_pt_idx][1]

        # Build numpy arrays for vectorised distance to all lookahead pts
        lookahead_lats = np.array([route_geometry[i][0] for i in lookahead_indices])
        lookahead_lons = np.array([route_geometry[i][1] for i in lookahead_indices])

        for sid in candidate_ids:
            station = index.stations_by_id.get(sid)  # O(1) lookup
            if station is None:
                continue

            slat, slon = station['lat'], station['lon']

            # Distance from station to each lookahead point (vectorised)
            dists_to_route = _haversine_miles(slat, slon, lookahead_lats, lookahead_lons)
            min_idx_local = int(np.argmin(dists_to_route))
            min_dist_to_route = dists_to_route[min_idx_local]
            closest_route_idx = lookahead_indices[min_idx_local]

            detour = min_dist_to_route * 2  # out-and-back detour
            dist_along_route_to_snap = route_dist[closest_route_idx] - current_dist

            # Reachability check
            if dist_along_route_to_snap + min_dist_to_route > current_range:
                continue

            # Score = fuel_price + small detour penalty (cost per detour mile at 10 mpg)
            score = station['price'] + (detour * station['price'] / VEHICLE_RANGE * 0.5)

            if score < best_score:
                best_score = score
                best_station = station
                best_detour = detour
                best_closest_idx = closest_route_idx

        if best_station is None:
            logger.error("No reachable candidate stations after scoring.")
            return [], -1

        # ── Commit to the chosen stop ──────────────────────────────────────────
        dist_driven_to_snap = route_dist[best_closest_idx] - current_dist
        dist_to_station = best_detour / 2
        total_dist_this_leg = dist_driven_to_snap + dist_to_station

        current_range -= total_dist_this_leg

        # Fill tank
        gallons_needed = (VEHICLE_RANGE - current_range) / MPG
        cost = round(gallons_needed * best_station['price'], 2)
        total_cost += cost
        current_range = VEHICLE_RANGE

        current_dist = route_dist[best_closest_idx]
        current_pt_idx = int(best_closest_idx)

        stops.append({
            'station_name': best_station['name'],
            'address': best_station['address'],
            'city': best_station['city'],
            'state': best_station['state'],
            'latitude': best_station['lat'],
            'longitude': best_station['lon'],
            'price_per_gallon': round(best_station['price'], 4),
            'gallons_added': round(gallons_needed, 2),
            'cost_usd': cost,
            'detour_miles': round(best_detour, 2),
            'distance_from_start_miles': round(current_dist, 2),
        })

        logger.info(
            f"Stop #{len(stops)}: {best_station['name']} ({best_station['city']}, {best_station['state']}) "
            f"— ${best_station['price']:.3f}/gal, {gallons_needed:.1f} gal, ${cost:.2f}"
        )

    logger.info(f"Optimization complete. {len(stops)} stops, total cost ${total_cost:.2f}")
    return stops, round(total_cost, 2)
