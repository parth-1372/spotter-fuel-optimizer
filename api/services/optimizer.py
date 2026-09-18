from geopy.distance import geodesic
import logging
from .spatial_index import SpatialIndex

logger = logging.getLogger(__name__)

VEHICLE_RANGE = 500  # miles
MPG = 10
SAFE_BUFFER = 50  # look for gas when range drops to 50 miles

def optimize_fuel_stops(route_geometry, total_distance):
    """
    Calculate optimal fuel stops along the route.
    Assumes starting with a full tank (500 miles range).
    """
    index = SpatialIndex.get_instance()
    
    if not index.kdtree or not route_geometry:
        return [], 0
        
    stops = []
    current_range = VEHICLE_RANGE
    total_cost = 0.0
    
    # Pre-calculate distance along route for each point
    route_distances = [0.0]
    for i in range(1, len(route_geometry)):
        dist = geodesic(route_geometry[i-1], route_geometry[i]).miles
        route_distances.append(route_distances[-1] + dist)
        
    current_point_idx = 0
    distance_traveled = 0.0
    
    while True:
        distance_remaining = total_distance - distance_traveled
        if current_range >= distance_remaining:
            # Can reach destination
            break
            
        # We need to fuel up. Look ahead up to (current_range - SAFE_BUFFER) miles.
        max_lookahead_dist = distance_traveled + (current_range - SAFE_BUFFER)
        
        # Find route points in the lookahead window
        lookahead_points = []
        for i in range(current_point_idx, len(route_geometry)):
            if route_distances[i] > max_lookahead_dist:
                break
            # Only consider points that are reasonably far ahead, to minimize stops
            if route_distances[i] > distance_traveled + (current_range * 0.5):
                lookahead_points.append(i)
                
        # If we couldn't find points far ahead, just use whatever we can reach
        if not lookahead_points:
            for i in range(current_point_idx, len(route_geometry)):
                if route_distances[i] > distance_traveled + current_range:
                    break
                lookahead_points.append(i)
                
        if not lookahead_points:
            # Cannot reach next point
            return [], -1
            
        # Find candidate stations near the lookahead points
        candidates = set()
        for idx in lookahead_points:
            pt = route_geometry[idx]
            # Search radius 30 miles
            nearby = index.query_radius(pt[0], pt[1], 30)
            for station in nearby:
                candidates.add(station['id'])
                
        if not candidates:
            # Try a larger radius near the furthest point we can reach
            pt = route_geometry[lookahead_points[-1]]
            nearby = index.query_radius(pt[0], pt[1], 60)
            for station in nearby:
                candidates.add(station['id'])
                
        if not candidates:
            logger.error("No stations found in range.")
            return [], -1
            
        # Evaluate candidates: minimize (fuel_price) as primary, with a small penalty for detour
        best_station = None
        best_score = float('inf')
        best_detour = 0
        best_route_idx = 0
        
        for station_id in candidates:
            # Get full station data
            station = next(s for s in index.stations_data if s['id'] == station_id)
            
            # Find closest route point to station
            min_dist_to_route = float('inf')
            closest_idx = current_point_idx
            
            for idx in lookahead_points:
                dist = geodesic((station['lat'], station['lon']), route_geometry[idx]).miles
                if dist < min_dist_to_route:
                    min_dist_to_route = dist
                    closest_idx = idx
                    
            detour_dist = min_dist_to_route * 2 # there and back
            
            # Can we reach it?
            dist_to_route_point = route_distances[closest_idx] - distance_traveled
            if dist_to_route_point + min_dist_to_route > current_range:
                continue
                
            # Score: price per gallon + small penalty for detour
            score = station['price'] + (detour_dist * 0.05)
            
            if score < best_score:
                best_score = score
                best_station = station
                best_detour = detour_dist
                best_route_idx = closest_idx
                
        if not best_station:
            logger.error("No reachable stations.")
            return [], -1
            
        # Make the stop
        # Distance to stop
        dist_driven = (route_distances[best_route_idx] - distance_traveled) + (best_detour / 2)
        current_range -= dist_driven
        
        # Calculate fuel needed to fill tank
        gallons_needed = (VEHICLE_RANGE - current_range) / MPG
        cost = gallons_needed * best_station['price']
        total_cost += cost
        
        # Refill
        current_range = VEHICLE_RANGE
        distance_traveled = route_distances[best_route_idx]
        current_point_idx = best_route_idx
        
        stops.append({
            'station': best_station,
            'gallons': round(gallons_needed, 2),
            'cost': round(cost, 2),
            'detour_miles': round(best_detour, 2),
            'distance_from_start': round(distance_traveled, 2)
        })
        
    return stops, total_cost
