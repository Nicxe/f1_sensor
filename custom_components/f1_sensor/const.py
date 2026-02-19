from datetime import timedelta

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
    Platform.CALENDAR,
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

# Race schedule grace period: keep a session "current" briefly after start.
RACE_SWITCH_GRACE = timedelta(hours=3)

# Live delay calibration reference
CONF_LIVE_DELAY_REFERENCE = "live_delay_reference"
LIVE_DELAY_REFERENCE_SESSION = "session_live"
LIVE_DELAY_REFERENCE_FORMATION = "formation_start"
LIVE_DELAY_REFERENCE_LAP_SYNC = "lap_sync"
DEFAULT_LIVE_DELAY_REFERENCE = LIVE_DELAY_REFERENCE_SESSION

# Replay start reference
CONF_REPLAY_START_REFERENCE = "replay_start_reference"
REPLAY_START_REFERENCE_SESSION = LIVE_DELAY_REFERENCE_SESSION
REPLAY_START_REFERENCE_FORMATION = LIVE_DELAY_REFERENCE_FORMATION
DEFAULT_REPLAY_START_REFERENCE = REPLAY_START_REFERENCE_FORMATION

# Gate for exposing development mode controls in the UI.
# Keep this False in released versions to avoid confusing users;
# flip to True locally when you want to work with replay/development mode.
ENABLE_DEVELOPMENT_MODE_UI = False

LATEST_TRACK_STATUS = "f1_latest_track_status"

# All supported sensor keys (used for normalization and config entry filtering).
SUPPORTED_SENSOR_KEYS = frozenset(
    {
        "next_race",
        "track_time",
        "current_season",
        "driver_standings",
        "constructor_standings",
        "weather",
        "track_weather",
        "race_lap_count",
        "driver_list",
        "current_tyres",
        "last_race_results",
        "season_results",
        "sprint_results",
        "driver_points_progression",
        "constructor_points_progression",
        "race_week",
        "track_status",
        "session_status",
        "current_session",
        "session_time_remaining",
        "session_time_elapsed",
        "race_time_to_three_hour_limit",
        "safety_car",
        "formation_start",
        "fia_documents",
        "race_control",
        "top_three",
        "team_radio",
        "pitstops",
        "championship_prediction",
        "live_timing_diagnostics",
        "tyre_statistics",
        "driver_positions",
        "track_limits",
        "investigations",
        "calendar",
    }
)

API_URL = "https://api.jolpi.ca/ergast/f1/current.json"
DRIVER_STANDINGS_URL = (
    "https://api.jolpi.ca/ergast/f1/current/driverstandings.json?limit=100"
)
CONSTRUCTOR_STANDINGS_URL = (
    "https://api.jolpi.ca/ergast/f1/current/constructorstandings.json?limit=100"
)
LAST_RACE_RESULTS_URL = (
    "https://api.jolpi.ca/ergast/f1/current/last/results.json?limit=100"
)
# Base URL for season results; pagination will be handled by the coordinator
SEASON_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/results.json"

# Sprint results across the current season
SPRINT_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/sprint.json?limit=100"

LIVETIMING_INDEX_URL = "https://livetiming.formula1.com/static/{year}/Index.json"

# Secondary live schedule source (fallback only when Index.json is unavailable/invalid)
EVENT_TRACKER_FALLBACK_ENABLED = True
EVENT_TRACKER_ENV_SOURCE_URL = "https://www.formula1.com/en/timing/f1-live-lite"
EVENT_TRACKER_API_BASE_URL = "https://api.formula1.com"
EVENT_TRACKER_ENDPOINT = "/v1/event-tracker"
EVENT_TRACKER_MEETING_ENDPOINT_PREFIX = "/v1/event-tracker/meeting/"
# Public key used by the official F1 live-lite frontend; refreshed dynamically from processEnv.
EVENT_TRACKER_DEFAULT_API_KEY = "lfjBG5SiokAAND3ucpnE9BcPjO74SpUz"
EVENT_TRACKER_DEFAULT_LOCALE = "en"
EVENT_TRACKER_REQUEST_TIMEOUT = 10
EVENT_TRACKER_ACTIVE_CACHE_TTL = 60
EVENT_TRACKER_IDLE_CACHE_TTL = 900
EVENT_TRACKER_ENV_REFRESH_TTL = 6 * 3600

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

# Circuit map image support (official F1 track maps with DRS zones)
CIRCUIT_MAP_CDN_BASE_URL = "https://media.formula1.com/image/upload/f_auto,q_auto/content/dam/fom-website/2018-redesign-assets/Circuit%20maps%2016x9"

# Map from Ergast circuitId to F1 CDN filename (without _Circuit.webp suffix)
# Verified against F1 calendars 2020-2026
F1_CIRCUIT_MAP_NAMES: dict[str, str] = {
    # Current calendar (2024-2026)
    "bahrain": "Bahrain",
    "jeddah": "Saudi_Arabia",
    "albert_park": "Australia",
    "suzuka": "Japan",
    "shanghai": "China",
    "miami": "Miami",
    "imola": "Emilia_Romagna",
    "monaco": "Monaco",
    "villeneuve": "Canada",
    "catalunya": "Spain",
    "red_bull_ring": "Austria",
    "silverstone": "Great_Britain",
    "hungaroring": "Hungary",
    "spa": "Belgium",
    "zandvoort": "Netherlands",
    "monza": "Italy",
    "baku": "Baku",
    "marina_bay": "Singapore",
    "americas": "USA",
    "rodriguez": "Mexico",
    "interlagos": "Brazil",
    "vegas": "Las_Vegas",
    "losail": "Qatar",
    "yas_marina": "Abu_Dhabi",
    # Historic circuits (2020-2022)
    "portimao": "Portugal",
    "istanbul": "Turkey",
    "sochi": "Russia",
    "ricard": "France",
    "mugello": "Tuscany",
    "nurburgring": "Eifel",
}

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
