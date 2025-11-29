from homeassistant.const import Platform

DOMAIN = "f1_sensor"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

LATEST_TRACK_STATUS = "f1_latest_track_status"
BASE_URL = "https://api.jolpi.ca/ergast/f1/current/"
EXT = ".json"

API_URL = f"{BASE_URL}current{EXT}"
DRIVER_STANDINGS_URL = f"{BASE_URL}driverstandings{EXT}"
CONSTRUCTOR_STANDINGS_URL = f"{BASE_URL}constructorstandings{EXT}"
LAST_RACE_RESULTS_URL = f"{BASE_URL}last/results{EXT}"

# Season-wide results (the coordinator handles pagination)
SEASON_RESULTS_URL = f"{BASE_URL}results{EXT}"

# Sprint results for the current season
SPRINT_RESULTS_URL = f"{BASE_URL}sprint{EXT}"

LIVETIMING_INDEX_URL = "https://livetiming.formula1.com/static/{year}/Index.json"

# Reconnection back-off settings for the SignalR client
FAST_RETRY_SEC = 5
MAX_RETRY_SEC = 60
BACK_OFF_FACTOR = 2

# FIA document scraping defaults (best effort, update slug each season if FIA changes structure)
FIA_DOCUMENTS_BASE_URL = "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14"
FIA_SEASON_LIST_URL = f"{FIA_DOCUMENTS_BASE_URL}/season"
FIA_SEASON_FALLBACK_URL = f"{FIA_DOCUMENTS_BASE_URL}/season/season-2025-2071"

FIA_DOCS_POLL_INTERVAL = 900  # seconds
FIA_DOCS_FETCH_TIMEOUT = 15
