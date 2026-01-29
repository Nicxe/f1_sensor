from homeassistant.const import Platform

DOMAIN = "f1_sensor"
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.MEDIA_PLAYER,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
]

# Replay Mode
REPLAY_CACHE_DIR = "f1_replay_cache"
REPLAY_CACHE_RETENTION_DAYS = (
    1  # Short retention - cache is deleted on stop, this is just backup
)

CONF_OPERATION_MODE = "operation_mode"
CONF_REPLAY_FILE = "replay_file"
CONF_RACE_WEEK_SUNDAY_START = "race_week_sunday_start"
CONF_RACE_WEEK_START_DAY = "race_week_start_day"
RACE_WEEK_START_MONDAY = "monday"
RACE_WEEK_START_SATURDAY = "saturday"
RACE_WEEK_START_SUNDAY = "sunday"
DEFAULT_RACE_WEEK_START_DAY = RACE_WEEK_START_MONDAY

OPERATION_MODE_LIVE = "live"
OPERATION_MODE_DEVELOPMENT = "development"
DEFAULT_OPERATION_MODE = OPERATION_MODE_LIVE

# Live delay calibration reference
CONF_LIVE_DELAY_REFERENCE = "live_delay_reference"
LIVE_DELAY_REFERENCE_SESSION = "session_live"
LIVE_DELAY_REFERENCE_FORMATION = "formation_start"
DEFAULT_LIVE_DELAY_REFERENCE = LIVE_DELAY_REFERENCE_SESSION

# Replay start reference
CONF_REPLAY_START_REFERENCE = "replay_start_reference"
REPLAY_START_REFERENCE_SESSION = LIVE_DELAY_REFERENCE_SESSION
REPLAY_START_REFERENCE_FORMATION = LIVE_DELAY_REFERENCE_FORMATION
DEFAULT_REPLAY_START_REFERENCE = REPLAY_START_REFERENCE_FORMATION

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
FIA_DOCUMENTS_BASE_URL = (
    "https://www.fia.com/documents/championships/fia-formula-one-world-championship-14"
)
FIA_SEASON_LIST_URL = f"{FIA_DOCUMENTS_BASE_URL}/season"
FIA_SEASON_FALLBACK_URL = f"{FIA_DOCUMENTS_BASE_URL}/season/season-2025-2071"
FIA_DOCS_POLL_INTERVAL = 900  # seconds
FIA_DOCS_FETCH_TIMEOUT = 15

# Country flag support
FLAG_CDN_BASE_URL = "https://flagcdn.com/w80"

F1_COUNTRY_CODES: dict[str, str] = {
    "Bahrain": "bh",
    "Saudi Arabia": "sa",
    "Australia": "au",
    "Japan": "jp",
    "China": "cn",
    "USA": "us",
    "Monaco": "mc",
    "Canada": "ca",
    "Spain": "es",
    "Austria": "at",
    "UK": "gb",
    "Hungary": "hu",
    "Belgium": "be",
    "Netherlands": "nl",
    "Italy": "it",
    "Azerbaijan": "az",
    "Singapore": "sg",
    "Mexico": "mx",
    "Brazil": "br",
    "Qatar": "qa",
    "UAE": "ae",
    # Variants used by API
    "United States": "us",
    "United Arab Emirates": "ae",
    "United Kingdom": "gb",
    "Great Britain": "gb",
}
