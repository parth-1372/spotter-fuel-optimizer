from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RouteRequestSerializer, RouteResponseSerializer
from .services.routing import get_coordinates, fetch_route
from .services.optimizer import optimize_fuel_stops, VEHICLE_RANGE, MPG
import logging

logger = logging.getLogger(__name__)


class OptimizeRouteView(APIView):
    """
    POST /api/optimize-route/

    Takes a start and finish location within the USA and returns:
    - The driving route geometry (decoded polyline)
    - Optimal fuel stops based on cheapest price within 500-mile range
    - Total fuel cost at 10 MPG

    One external API call (OpenRouteService) is made per request.
    """

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_loc = serializer.validated_data['start_location']
        finish_loc = serializer.validated_data['finish_location']

        # ── Step 1: Geocode both locations ────────────────────────────────────
        start_coords = get_coordinates(start_loc)
        if not start_coords:
            return Response(
                {"error": f"Could not resolve start location: '{start_loc}'. "
                           "Please use a city/state format e.g. 'Chicago, IL'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        finish_coords = get_coordinates(finish_loc)
        if not finish_coords:
            return Response(
                {"error": f"Could not resolve finish location: '{finish_loc}'. "
                           "Please use a city/state format e.g. 'Miami, FL'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(f"Route request: '{start_loc}' → '{finish_loc}'")

        # ── Step 2: ONE call to ORS to fetch route ────────────────────────────
        try:
            route_geometry, total_distance = fetch_route(start_coords, finish_coords)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not route_geometry:
            return Response(
                {"error": "Could not retrieve a driving route between the provided locations. "
                           "Ensure both locations are within the USA and reachable by road."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ── Step 3: Optimize fuel stops (no external calls) ───────────────────
        stops, total_cost = optimize_fuel_stops(route_geometry, total_distance)

        if total_cost == -1:
            return Response(
                {"error": "Could not find a valid fueling strategy. "
                           "The route may pass through an area with no nearby truck stops."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # ── Step 4: Build and return response ────────────────────────────────
        response_payload = {
            'start_location': start_loc,
            'finish_location': finish_loc,
            'start_coords': list(start_coords),
            'finish_coords': list(finish_coords),
            'total_distance_miles': round(total_distance, 2),
            'total_fuel_cost_usd': total_cost,
            'total_stops': len(stops),
            'vehicle_range_miles': VEHICLE_RANGE,
            'vehicle_mpg': MPG,
            'optimal_fuel_stops': stops,
            'route_geometry': route_geometry,
        }

        out = RouteResponseSerializer(response_payload)
        return Response(out.data, status=status.HTTP_200_OK)
