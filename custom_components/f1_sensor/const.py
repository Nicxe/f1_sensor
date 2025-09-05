from homeassistant.const import Platform

DOMAIN = "f1_sensor"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

LATEST_TRACK_STATUS = "f1_latest_track_status"

API_URL = "https://api.jolpi.ca/ergast/f1/current.json"
DRIVER_STANDINGS_URL = "https://api.jolpi.ca/ergast/f1/current/driverstandings.json"
CONSTRUCTOR_STANDINGS_URL = (
    "https://api.jolpi.ca/ergast/f1/current/constructorstandings.json"
)
LAST_RACE_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
# Base URL for season results; pagination will be handled by the coordinator
SEASON_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/results.json"

LIVETIMING_INDEX_URL = "https://livetiming.formula1.com/static/{year}/Index.json"

# Reconnection back-off settings for the SignalR client
FAST_RETRY_SEC = 5
MAX_RETRY_SEC = 60
BACK_OFF_FACTOR = 2
