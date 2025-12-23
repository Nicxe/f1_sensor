from pathlib import Path

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_OPERATION_MODE,
    CONF_REPLAY_FILE,
    DEFAULT_OPERATION_MODE,
    DOMAIN,
    ENABLE_DEVELOPMENT_MODE_UI,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
)


class F1FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        current = user_input or {}

        if user_input is not None:
            # Resolve and validate operation mode
            mode = user_input.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
            if mode not in (OPERATION_MODE_LIVE, OPERATION_MODE_DEVELOPMENT):
                mode = DEFAULT_OPERATION_MODE
            user_input[CONF_OPERATION_MODE] = mode

            replay_file = str(user_input.get(CONF_REPLAY_FILE, "") or "").strip()
            user_input[CONF_REPLAY_FILE] = replay_file
            if mode == OPERATION_MODE_DEVELOPMENT:
                if not replay_file:
                    errors[CONF_REPLAY_FILE] = "replay_required"
                else:
                    is_file = await self._validate_replay_file(replay_file)
                    if not is_file:
                        errors[CONF_REPLAY_FILE] = "replay_missing"
            else:
                user_input[CONF_REPLAY_FILE] = ""

            if not errors:
                return self.async_create_entry(
                    title=user_input["sensor_name"], data=user_input
                )

        default_enabled = [
            "next_race",
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
            "race_week",
            "track_status",
            "session_status",
            "race_control",
            "current_session",
            "safety_car",
            "live_timing_diagnostics",
        ]
        sensor_options = {
            "next_race": "Next race",
            "current_season": "Current season",
            "driver_standings": "Driver standings",
            "constructor_standings": "Constructor standings",
            "weather": "Weather",
            "track_weather": "Track weather (live)",
            "race_lap_count": "Race lap count (live)",
            "driver_list": "Driver list (live)",
            "current_tyres": "Current tyres (live)",
            "top_three": "Top three (leader, live)",
            "pitstops": "Pit stops (live)",
            "championship_prediction": "Championship prediction (live)",
            "last_race_results": "Last race results",
            "season_results": "Season results",
            "sprint_results": "Sprint results",
            "driver_points_progression": "Driver points progression",
            "constructor_points_progression": "Constructor points progression",
            "race_week": "Race week",
            "track_status": "Track status (live)",
            "session_status": "Session status (live)",
            "race_control": "Race control (live)",
            "current_session": "Current session (live)",
            "safety_car": "Safety car (live)",
            "fia_documents": "FIA decisions",
            "team_radio": "Team radio (latest clip)",
            "live_timing_diagnostics": "Live timing diagnostics (online/mode)",
        }

        # Build base schema
        schema_fields: dict = {
            vol.Required(
                "sensor_name", default=current.get("sensor_name", "F1")
            ): cv.string,
            vol.Required(
                "enabled_sensors",
                default=current.get("enabled_sensors", default_enabled),
            ): cv.multi_select(sensor_options),
            vol.Optional("enable_race_control", default=False): cv.boolean,
        }

        # Only expose development-related controls when explicitly enabled.
        # This keeps the main setup simple for normal users.
        if ENABLE_DEVELOPMENT_MODE_UI:
            schema_fields.update(
                {
                    vol.Required(
                        CONF_OPERATION_MODE,
                        default=current.get(
                            CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                        ),
                    ): vol.In([OPERATION_MODE_LIVE, OPERATION_MODE_DEVELOPMENT]),
                    vol.Optional(
                        CONF_REPLAY_FILE,
                        default=current.get(CONF_REPLAY_FILE, ""),
                    ): cv.string,
                }
            )
        else:
            # In normal installations we always run in LIVE mode.
            current.setdefault(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)

        data_schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        errors = {}

        entry = self._get_reconfigure_entry()
        current = entry.data

        if user_input is not None:
            mode = user_input.get(
                CONF_OPERATION_MODE, current.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
            )
            if mode not in (OPERATION_MODE_LIVE, OPERATION_MODE_DEVELOPMENT):
                mode = DEFAULT_OPERATION_MODE
            user_input[CONF_OPERATION_MODE] = mode

            replay_file = str(user_input.get(CONF_REPLAY_FILE, "") or "").strip()
            user_input[CONF_REPLAY_FILE] = replay_file
            if mode == OPERATION_MODE_DEVELOPMENT:
                if not replay_file:
                    errors[CONF_REPLAY_FILE] = "replay_required"
                else:
                    valid = await self._validate_replay_file(replay_file)
                    if not valid:
                        errors[CONF_REPLAY_FILE] = "replay_missing"
            else:
                user_input[CONF_REPLAY_FILE] = ""

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                )

        # Normalize/clean any stale enabled_sensors keys (e.g. legacy 'next_session')
        allowed = {
            "next_race": "Next race",
            "current_season": "Current season",
            "driver_standings": "Driver standings",
            "constructor_standings": "Constructor standings",
            "weather": "Weather",
            "track_weather": "Track weather (live)",
            "race_lap_count": "Race lap count (live)",
            "driver_list": "Driver list (live)",
            "current_tyres": "Current tyres (live)",
            "top_three": "Top three (leader, live)",
            "pitstops": "Pit stops (live)",
            "championship_prediction": "Championship prediction (live)",
            "last_race_results": "Last race results",
            "season_results": "Season results",
            "sprint_results": "Sprint results",
            "driver_points_progression": "Driver points progression",
            "constructor_points_progression": "Constructor points progression",
            "race_week": "Race week",
            "track_status": "Track status (live)",
            "session_status": "Session status (live)",
            "race_control": "Race control (live)",
            "current_session": "Current session (live)",
            "safety_car": "Safety car (live)",
            "fia_documents": "FIA decisions",
            "team_radio": "Team radio (latest clip)",
            "live_timing_diagnostics": "Live timing diagnostics (online/mode)",
        }
        default_enabled = [
            "next_race",
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
            "race_control",
            "current_session",
            "safety_car",
            "live_timing_diagnostics",
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
        schema_fields: dict = {
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
        }

        # For reconfigure we show dev controls either when explicitly enabled
        # or when the existing entry is already in development mode (so it
        # remains editable even if the flag is later turned off).
        show_dev_controls = ENABLE_DEVELOPMENT_MODE_UI or current.get(
            CONF_OPERATION_MODE
        ) == OPERATION_MODE_DEVELOPMENT

        if show_dev_controls:
            schema_fields.update(
                {
                    vol.Required(
                        CONF_OPERATION_MODE,
                        default=current.get(
                            CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                        ),
                    ): vol.In([OPERATION_MODE_LIVE, OPERATION_MODE_DEVELOPMENT]),
                    vol.Optional(
                        CONF_REPLAY_FILE,
                        default=current.get(CONF_REPLAY_FILE, ""),
                    ): cv.string,
                }
            )

        data_schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )

    def _get_reconfigure_entry(self):
        """Return the config entry for this domain."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        return entries[0] if entries else None

    async def _validate_replay_file(self, path: str) -> bool:
        """Return True if the provided path points to a readable file."""
        def _check() -> bool:
            try:
                candidate = Path(path).expanduser()
                return candidate.is_file()
            except Exception:
                return False

        try:
            return await self.hass.async_add_executor_job(_check)
        except Exception:
            return False
