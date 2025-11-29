from homeassistant.const import Platform

DOMAIN = "f1_sensor"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

LATEST_TRACK_STATUS = "f1_latest_track_status"
BASE_URL = "https://api.jolpi.ca/ergast/f1/current/"

API_URL = BASE_URL + "current.json"
DRIVER_STANDINGS_URL = BASE_URL + "driverstandings.json"
CONSTRUCTOR_STANDINGS_URL = BASE_URL + "constructorstandings.json"
LAST_RACE_RESULTS_URL = BASE_URL + "last/results.json"

# Base URL for season results; pagination will be handled by the coordinator
SEASON_RESULTS_URL = BASE_URL + "results.json"

# Sprint results across the current season
SPRINT_RESULTS_URL = BASE_URL + "sprint.json"

LIVETIMING_INDEX_URL = "https://livetiming.formula1.com/static/{year}/Index.json"

# Reconnection back-off settings for the SignalR client
FAST_RETRY_SEC = 5
MAX_RETRY_SEC = 60
BACK_OFF_FACTOR = 2
