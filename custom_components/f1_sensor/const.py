from homeassistant.const import Platform

DOMAIN = "f1_sensor"
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SWITCH,
]

CONF_OPERATION_MODE = "operation_mode"
CONF_REPLAY_FILE = "replay_file"

OPERATION_MODE_LIVE = "live"
OPERATION_MODE_DEVELOPMENT = "development"
DEFAULT_OPERATION_MODE = OPERATION_MODE_LIVE

# Gate for exposing development mode controls in the UI.
# Keep this False in released versions to avoid confusing users;
# flip to True locally when you want to work with replay/development mode.
ENABLE_DEVELOPMENT_MODE_UI = True

LATEST_TRACK_STATUS = "f1_latest_track_status"

API_URL = "https://api.jolpi.ca/ergast/f1/current.json"
DRIVER_STANDINGS_URL = "https://api.jolpi.ca/ergast/f1/current/driverstandings.json"
CONSTRUCTOR_STANDINGS_URL = (
    "https://api.jolpi.ca/ergast/f1/current/constructorstandings.json"
)
LAST_RACE_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
# Base URL for season results; pagination will be handled by the coordinator
SEASON_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/results.json"

# Sprint results across the current season
SPRINT_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/sprint.json"

LIVETIMING_INDEX_URL = "https://livetiming.formula1.com/static/{year}/Index.json"

# Reconnection back-off settings for the SignalR client
FAST_RETRY_SEC = 5
MAX_RETRY_SEC = 60
BACK_OFF_FACTOR = 2

# FIA document scraping defaults (best effort, update slug each season if FIA changes structure)
FIA_DOCUMENTS_BASE_URL = "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14"
FIA_SEASON_LIST_URL = f"{FIA_DOCUMENTS_BASE_URL}/season"
FIA_SEASON_FALLBACK_URL = (
    f"{FIA_DOCUMENTS_BASE_URL}/season/season-2025-2071"
)
FIA_DOCS_POLL_INTERVAL = 900  # seconds
FIA_DOCS_FETCH_TIMEOUT = 15
