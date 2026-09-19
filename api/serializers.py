from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start_location = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Starting location within the USA. e.g., 'New York, NY'",
    )
    finish_location = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Destination within the USA. e.g., 'Los Angeles, CA'",
    )


class FuelStopSerializer(serializers.Serializer):
    station_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    price_per_gallon = serializers.FloatField()
    gallons_added = serializers.FloatField()
    cost_usd = serializers.FloatField()
    detour_miles = serializers.FloatField()
    distance_from_start_miles = serializers.FloatField()


class RouteResponseSerializer(serializers.Serializer):
    start_location = serializers.CharField()
    finish_location = serializers.CharField()
    start_coords = serializers.ListField(child=serializers.FloatField())
    finish_coords = serializers.ListField(child=serializers.FloatField())
    total_distance_miles = serializers.FloatField()
    total_fuel_cost_usd = serializers.FloatField()
    total_stops = serializers.IntegerField()
    vehicle_range_miles = serializers.IntegerField()
    vehicle_mpg = serializers.IntegerField()
    optimal_fuel_stops = FuelStopSerializer(many=True)
    route_geometry = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        help_text="Decoded polyline as [[lat, lon], ...]. Use with Leaflet/Google Maps.",
    )
