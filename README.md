# Fuel Route Optimizer API

A Django REST API that calculates the optimal fuel stops along a driving route within the USA, minimizing fuel cost based on real truck stop prices.

## Features

- Accepts any two US city/state locations
- Returns the driving route polyline (from OpenRouteService — **one API call per request**)
- Finds optimal fuel stops using a greedy lookahead algorithm with in-memory KDTree spatial indexing
- Assumes 500-mile max vehicle range, 10 MPG
- Returns total fuel cost in USD

## Tech Stack

- **Django 4.2** + Django REST Framework
- **OpenRouteService** — free routing API (1 call per request)
- **Nominatim (OpenStreetMap)** — free geocoding
- **scipy KDTree** — in-memory spatial indexing for fast station lookups
- **numpy** — vectorised haversine distance calculations

## Setup

### 1. Clone and create virtual environment

```bash
git clone <your-repo-url>
cd Spotter-backend
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows PowerShell
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
copy .env.example .env
```

Then edit `.env`:
```
ORS_API_KEY=your-openrouteservice-api-key-here   # free at openrouteservice.org
DJANGO_SECRET_KEY=your-secret-key
DEBUG=True
```

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Load and geocode fuel stations (one-time setup, takes ~2-3 hours)

```bash
python manage.py setup_stations
```

This reads `fuel-prices-for-be-assessment.csv`, creates all fuel station records, and geocodes each unique city/state pair using Nominatim. Results are cached per city so duplicate cities are only geocoded once.

### 6. Start the server

```bash
python manage.py runserver
```

## API Usage

### `POST /api/optimize-route/`

**Request Body:**
```json
{
    "start_location": "New York, NY",
    "finish_location": "Los Angeles, CA"
}
```

**Response:**
```json
{
    "start_location": "New York, NY",
    "finish_location": "Los Angeles, CA",
    "start_coords": [40.7127281, -74.0060152],
    "finish_coords": [34.0536909, -118.2427666],
    "total_distance_miles": 2789.5,
    "total_fuel_cost_usd": 82.45,
    "total_stops": 5,
    "vehicle_range_miles": 500,
    "vehicle_mpg": 10,
    "optimal_fuel_stops": [
        {
            "station_name": "PILOT TRAVEL CENTER",
            "address": "I-80, EXIT 284",
            "city": "Gary",
            "state": "IN",
            "latitude": 41.5931,
            "longitude": -87.3464,
            "price_per_gallon": 2.9990,
            "gallons_added": 47.5,
            "cost_usd": 14.25,
            "detour_miles": 0.8,
            "distance_from_start_miles": 743.2
        }
    ],
    "route_geometry": [[40.71, -74.00], [40.65, -74.12], ...]
}
```

### Error Responses

| Status | Meaning |
|--------|---------|
| `400` | Bad request — missing fields or unresolvable location |
| `502` | OpenRouteService API failure |
| `422` | No valid fueling strategy found (no stations in range) |

## Architecture

```
api/
├── services/
│   ├── spatial_index.py   # Singleton KDTree loaded once at startup
│   ├── routing.py         # ORS client singleton + geocoding
│   └── optimizer.py       # Greedy lookahead fuel algorithm
├── management/commands/
│   └── setup_stations.py  # One-time CSV import + geocoding script
├── models.py              # FuelStation model
├── serializers.py         # DRF serializers
├── views.py               # API endpoint
└── urls.py                # URL routing
```
