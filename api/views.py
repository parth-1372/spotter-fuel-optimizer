from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RouteRequestSerializer, RouteResponseSerializer
from .services.routing import get_coordinates, fetch_route
from .services.optimizer import optimize_fuel_stops
import logging

logger = logging.getLogger(__name__)

class OptimizeRouteView(APIView):
    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_loc = serializer.validated_data['start_location']
        finish_loc = serializer.validated_data['finish_location']

        # 1. Geocode
        start_coords = get_coordinates(start_loc)
        finish_coords = get_coordinates(finish_loc)

        if not start_coords or not finish_coords:
            return Response(
                {"error": "Could not geocode one or both locations."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Get Route
        route_geometry, total_distance = fetch_route(start_coords, finish_coords)
        if not route_geometry:
            return Response(
                {"error": "Failed to fetch route. Ensure ORS_API_KEY is valid and locations are routable."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 3. Optimize Fuel Stops
        stops, total_cost = optimize_fuel_stops(route_geometry, total_distance)
        if total_cost == -1:
            return Response(
                {"error": "Could not find a valid fueling strategy for this route. Might be out of range of stations."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 4. Return
        resp_data = {
            'route_geometry': route_geometry,
            'total_distance_miles': round(total_distance, 2),
            'optimal_fuel_stops': stops,
            'total_fuel_cost': round(total_cost, 2)
        }
        
        resp_serializer = RouteResponseSerializer(resp_data)
        return Response(resp_serializer.data, status=status.HTTP_200_OK)

