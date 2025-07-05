DOMAIN = "f1_sensor"
PLATFORMS = ["sensor", "binary_sensor"]

# Global key for the shared flag state machine
FLAG_MACHINE = "f1_flag_state"

API_URL = "https://api.jolpi.ca/ergast/f1/current.json"
DRIVER_STANDINGS_URL = "https://api.jolpi.ca/ergast/f1/current/driverstandings.json"
CONSTRUCTOR_STANDINGS_URL = (
    "https://api.jolpi.ca/ergast/f1/current/constructorstandings.json"
)
LAST_RACE_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
SEASON_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/results.json?limit=100"

LIVETIMING_INDEX_URL = "https://livetiming.formula1.com/static/{year}/Index.json"

# Reconnection back-off settings for the SignalR client
FAST_RETRY_SEC = 5
MAX_RETRY_SEC = 60
BACK_OFF_FACTOR = 2
