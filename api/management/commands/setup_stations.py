import csv
import logging
from django.core.management.base import BaseCommand
from api.models import FuelStation
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Load fuel stations from CSV and geocode them'

    def handle(self, *args, **kwargs):
        self.stdout.write("Loading fuel stations from CSV...")
        
        # Initialize geocoder
        geolocator = Nominatim(user_agent="fuel_optimizer_setup")
        
        # Read CSV
        csv_file = 'fuel-prices-for-be-assessment.csv'
        stations_to_create = []
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse retail price safely
                    try:
                        price = float(row['Retail Price'])
                    except ValueError:
                        continue
                        
                    stations_to_create.append(FuelStation(
                        opis_truckstop_id=row['OPIS Truckstop ID'],
                        truckstop_name=row['Truckstop Name'],
                        address=row['Address'],
                        city=row['City'],
                        state=row['State'],
                        rack_id=row['Rack ID'] if row['Rack ID'] else None,
                        retail_price=price
                    ))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File {csv_file} not found!"))
            return

        self.stdout.write(f"Found {len(stations_to_create)} valid stations. Bulk creating...")
        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(stations_to_create)
        self.stdout.write(self.style.SUCCESS("Database populated! Now geocoding..."))
        
        # Geocoding - Nominatim limits to 1 req/sec. 
        # Geocoding 8000 rows will take hours, so we'll just geocode city/state to save some API calls 
        # by caching city coords if possible, or fallback.
        # Actually, let's cache coordinates for identical cities.
        
        city_cache = {}
        stations = FuelStation.objects.filter(latitude__isnull=True)
        count = 0
        total = stations.count()
        
        for station in stations:
            query = f"{station.city}, {station.state}, USA"
            
            if query in city_cache:
                station.latitude, station.longitude = city_cache[query]
                station.save()
            else:
                try:
                    location = geolocator.geocode(query, timeout=5)
                    if location:
                        station.latitude = location.latitude
                        station.longitude = location.longitude
                        station.save()
                        city_cache[query] = (location.latitude, location.longitude)
                    time.sleep(1.1)  # Respect Nominatim's 1 req/sec limit
                except (GeocoderTimedOut, GeocoderServiceError) as e:
                    self.stdout.write(self.style.WARNING(f"Geocoding failed for {query}: {e}"))
                    time.sleep(2)
            
            count += 1
            if count % 100 == 0:
                self.stdout.write(f"Geocoded {count}/{total} stations...")

        self.stdout.write(self.style.SUCCESS('Successfully loaded and geocoded fuel stations!'))
