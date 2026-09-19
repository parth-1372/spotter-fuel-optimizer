import json
from django.core.management.base import BaseCommand
from api.models import FuelStation
from pathlib import Path

class Command(BaseCommand):
    help = 'Export geocoded fuel stations from DB to a JSON file for deployment'

    def handle(self, *args, **kwargs):
        output_path = Path('data/fuel_stations.json')
        output_path.parent.mkdir(exist_ok=True)

        stations = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        data = []
        for s in stations:
            data.append({
                'id': s.id,
                'name': s.truckstop_name,
                'address': s.address,
                'city': s.city,
                'state': s.state,
                'price': s.retail_price,
                'lat': s.latitude,
                'lon': s.longitude,
            })

        with open(output_path, 'w') as f:
            json.dump(data, f)

        self.stdout.write(self.style.SUCCESS(f'Exported {len(data)} stations to {output_path}'))
