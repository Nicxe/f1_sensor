import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN


class F1FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
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
                        "last_race_results",
                        "season_results",
                        "race_week",
                        "next_session",
                        "race_control",
                        "flag",
                        "safety_car",
                    ],
                ): cv.multi_select(
                    {
                        "next_race": "Next race",
                        "current_season": "Current season",
                        "driver_standings": "Driver standings",
                        "constructor_standings": "Constructor standings",
                        "weather": "Weather",
                        "last_race_results": "Last race results",
                        "season_results": "Season results",
                        "race_week": "Race week",
                        "next_session": "Next session",
                        "race_control": "Race control",
                        "flag": "Flag",
                        "safety_car": "Safety car",
                    }
                ),
                vol.Optional("enable_race_control", default=True): cv.boolean,
                vol.Optional("fast_poll_seconds", default=5): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        errors = {}

        if user_input is not None:
            entry = self._get_reconfigure_entry()
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
            )

        entry = self._get_reconfigure_entry()
        current = entry.data
        data_schema = vol.Schema(
            {
                vol.Required(
                    "sensor_name", default=current.get("sensor_name", "F1")
                ): cv.string,
                vol.Required(
                    "enabled_sensors",
                    default=current.get(
                        "enabled_sensors",
                        [
                            "next_race",
                            "current_season",
                            "driver_standings",
                            "constructor_standings",
                            "weather",
                            "last_race_results",
                            "season_results",
                            "race_week",
                            "next_session",
                            "race_control",
                            "flag",
                            "safety_car",
                        ],
                    ),
                ): cv.multi_select(
                    {
                        "next_race": "Next race",
                        "current_season": "Current season",
                        "driver_standings": "Driver standings",
                        "constructor_standings": "Constructor standings",
                        "weather": "Weather",
                        "last_race_results": "Last race results",
                        "season_results": "Season results",
                        "race_week": "Race week",
                        "next_session": "Next session",
                        "race_control": "Race control",
                        "flag": "Flag",
                        "safety_car": "Safety car",
                    }
                ),
                vol.Optional(
                    "enable_race_control",
                    default=current.get("enable_race_control", True),
                ): cv.boolean,
                vol.Optional(
                    "fast_poll_seconds", default=current.get("fast_poll_seconds", 5)
                ): cv.positive_int,
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
