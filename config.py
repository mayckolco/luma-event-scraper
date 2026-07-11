"""Configuración del scraper — editable sin tocar la lógica central (RF-10)."""

CATEGORIES = ["tech", "ai"]

CITIES = [
    {"name": "San Francisco", "lat": 37.7749, "lon": -122.4194},
    {"name": "New York", "lat": 40.7128, "lon": -74.0060},
    {"name": "London", "lat": 51.5074, "lon": -0.1278},
    {"name": "Berlin", "lat": 52.5200, "lon": 13.4050},
    {"name": "Lima", "lat": -12.0464, "lon": -77.0428},
    {"name": "Austin", "lat": 30.2672, "lon": -97.7431},
]

MAX_PAGES = 50
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 3.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
REQUEST_TIMEOUT = 30

API_BASE_URL = "https://api.luma.com/discover/get-paginated-events"
USER_AGENT = "luma-event-scraper/0.1"

SEEN_EVENTS_FILE = "seen_events.json"
EVENTS_MASTER_FILE = "events_master.csv"
NEW_EVENTS_FILE_PREFIX = "new_events_"

CSV_FIELDNAMES = ["name", "url", "start_date", "city", "category", "first_seen"]

