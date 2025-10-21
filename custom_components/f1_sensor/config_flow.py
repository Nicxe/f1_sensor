import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN


class F1FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            # Backwards-compat: migrate favorite_drivers -> favorite_tlas storage key
            fav = user_input.pop("favorite_drivers", None)
            if fav is not None:
                user_input["favorite_tlas"] = fav
            # Enforce max 3 favorites
            try:
                fav_str = str(user_input.get("favorite_tlas", "") or "").strip()
                items = [t.strip().upper() for t in fav_str.split(",") if t.strip()]
                # Deduplicate preserving order and cap to 3
                seen = set()
                capped = []
                for t in items:
                    if t not in seen:
                        seen.add(t)
                        capped.append(t)
                    if len(capped) >= 3:
                        break
                user_input["favorite_tlas"] = ",".join(capped)
            except Exception:
                pass
            return self.async_create_entry(
                title=user_input["sensor_name"], data=user_input
            )

        data_schema = vol.Schema(
            {
                vol.Required("sensor_name", default="F1"): cv.string,
                vol.Required(
                    "enabled_sensors",
                    default=[
                        "next_race",
                        "current_season",
                        "driver_standings",
                        "constructor_standings",
                        "weather",
                        "track_weather",
                        "race_lap_count",
                        # TEMP_DISABLED: favorite drivers (live)
                        "last_race_results",
                        "season_results",
                        "race_week",
                        "track_status",
                        "session_status",
                        "current_session",
                        "safety_car",
                        # TEMP_DISABLED: race order (live)
                    ],
                ): cv.multi_select(
                    {
                        "next_race": "Next race",
                        "current_season": "Current season",
                        "driver_standings": "Driver standings",
                        "constructor_standings": "Constructor standings",
                        "weather": "Weather",
                        "track_weather": "Track weather (live)",
                        "race_lap_count": "Race lap count (live)",
                        # TEMP_DISABLED: Favorite drivers (live)
                        "driver_list": "Driver list (live)",
                        "last_race_results": "Last race results",
                        "season_results": "Season results",
                        "driver_points_progression": "Driver points progression",
                        "constructor_points_progression": "Constructor points progression",
                        "race_week": "Race week",
                        "track_status": "Track status (live)",
                        "session_status": "Session status (live)",
                        "current_session": "Current session (live)",
                        "safety_car": "Safety car (live)",
                        # TEMP_DISABLED: Race driver order (live)
                    }
                ),
                vol.Optional("enable_race_control", default=False): cv.boolean,
                vol.Optional(
                    "live_delay_seconds", default=0
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                # TEMP_DISABLED: favorite_drivers field hidden for this release
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        errors = {}

        if user_input is not None:
            entry = self._get_reconfigure_entry()
            # Normalize favorites and cap to 3
            fav = user_input.pop("favorite_drivers", None)
            if fav is not None:
                user_input["favorite_tlas"] = fav
            try:
                fav_str = str(user_input.get("favorite_tlas", "") or "").strip()
                items = [t.strip().upper() for t in fav_str.split(",") if t.strip()]
                seen = set()
                capped = []
                for t in items:
                    if t not in seen:
                        seen.add(t)
                        capped.append(t)
                    if len(capped) >= 3:
                        break
                user_input["favorite_tlas"] = ",".join(capped)
            except Exception:
                pass
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
            )

        entry = self._get_reconfigure_entry()
        current = entry.data
        # Normalize/clean any stale enabled_sensors keys (e.g. legacy 'next_session')
        allowed = {
            "next_race": "Next race",
            "current_season": "Current season",
            "driver_standings": "Driver standings",
            "constructor_standings": "Constructor standings",
            "weather": "Weather",
            "track_weather": "Track weather (live)",
            "race_lap_count": "Race lap count (live)",
            # TEMP_DISABLED: Favorite drivers (live)
            "driver_list": "Driver list (live)",
            "last_race_results": "Last race results",
            "season_results": "Season results",
            "driver_points_progression": "Driver points progression",
            "constructor_points_progression": "Constructor points progression",
            "race_week": "Race week",
            "track_status": "Track status (live)",
            "session_status": "Session status (live)",
            "current_session": "Current session (live)",
            "safety_car": "Safety car (live)",
            # TEMP_DISABLED: Race driver order (live)
        }
        default_enabled = [
            "next_race",
            "current_season",
            "driver_standings",
            "constructor_standings",
            "weather",
            "track_weather",
            "race_lap_count",
            # TEMP_DISABLED: favorite drivers (live)
            "driver_list",
            "last_race_results",
            "season_results",
            "driver_points_progression",
            "constructor_points_progression",
            "race_week",
            "track_status",
            "session_status",
            "current_session",
            "safety_car",
            # TEMP_DISABLED: race order (live)
        ]
        raw_enabled = current.get("enabled_sensors", default_enabled)
        normalized_enabled = []
        seen = set()
        for key in raw_enabled:
            # Legacy alias support
            if key == "next_session":
                key = "next_race"
            if key in allowed and key not in seen:
                normalized_enabled.append(key)
                seen.add(key)
        data_schema = vol.Schema(
            {
                vol.Required(
                    "sensor_name", default=current.get("sensor_name", "F1")
                ): cv.string,
                vol.Required(
                    "enabled_sensors",
                    default=normalized_enabled,
                ): cv.multi_select(allowed),
                vol.Optional(
                    "enable_race_control",
                    default=current.get("enable_race_control", False),
                ): cv.boolean,
                vol.Optional(
                    "live_delay_seconds",
                    default=current.get("live_delay_seconds", 0),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=300)),
                # TEMP_DISABLED: favorite_drivers field hidden for this release
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )

    def _get_reconfigure_entry(self):
        """Return the config entry for this domain."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        return entries[0] if entries else None
