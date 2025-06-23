DOMAIN = "f1_sensor"
PLATFORMS = ["sensor", "binary_sensor"]

# Dispatcher signals for real-time updates
SIGNAL_FLAG_UPDATE = "f1sensor_flag_update"
SIGNAL_SC_UPDATE = "f1sensor_safety_car_update"

API_URL = "https://api.jolpi.ca/ergast/f1/current.json"
DRIVER_STANDINGS_URL = "https://api.jolpi.ca/ergast/f1/current/driverstandings.json"
CONSTRUCTOR_STANDINGS_URL = "https://api.jolpi.ca/ergast/f1/current/constructorstandings.json"
LAST_RACE_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/last/results.json"
SEASON_RESULTS_URL = "https://api.jolpi.ca/ergast/f1/current/results.json?limit=100"