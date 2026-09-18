from rest_framework import serializers

class RouteRequestSerializer(serializers.Serializer):
    start_location = serializers.CharField(max_length=255, required=True, help_text="e.g., 'New York, NY'")
    finish_location = serializers.CharField(max_length=255, required=True, help_text="e.g., 'Los Angeles, CA'")

class FuelStopSerializer(serializers.Serializer):
    station = serializers.DictField()
    gallons = serializers.FloatField()
    cost = serializers.FloatField()
    detour_miles = serializers.FloatField()
    distance_from_start = serializers.FloatField()

class RouteResponseSerializer(serializers.Serializer):
    route_geometry = serializers.ListField(child=serializers.ListField(child=serializers.FloatField()))
    total_distance_miles = serializers.FloatField()
    optimal_fuel_stops = FuelStopSerializer(many=True)
    total_fuel_cost = serializers.FloatField()
