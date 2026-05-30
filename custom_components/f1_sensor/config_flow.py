from pathlib import Path

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from . import const
from .auth import is_auth_feature_enabled
from .auth_http import (
    async_create_f1tv_pairing_session,
    async_pop_f1tv_pairing_session_result,
    async_setup_f1tv_auth_http,
)
from .const import (
    CONF_CLEAR_LIVE_TIMING_AUTH_HEADER,
    CONF_ENTITY_NAME_LANGUAGE,
    CONF_ENTITY_NAME_MODE,
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    CONF_RACE_WEEK_START_DAY,
    CONF_RACE_WEEK_SUNDAY_START,
    CONF_REPLAY_FILE,
    CONF_START_F1TV_PAIRING,
    DEFAULT_ENTITY_NAME_LANGUAGE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_RACE_WEEK_START_DAY,
    DOMAIN,
    ENTITY_NAME_MODE_LOCALIZED,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
    RACE_WEEK_START_MONDAY,
    RACE_WEEK_START_SATURDAY,
    RACE_WEEK_START_SUNDAY,
)
from .helpers import normalize_live_timing_auth_header

_AUTH_HEADER_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)

RACE_WEEK_START_OPTIONS = {
    RACE_WEEK_START_MONDAY: "Monday",
    RACE_WEEK_START_SUNDAY: "Sunday",
    RACE_WEEK_START_SATURDAY: "Saturday",
}

SENSOR_OPTIONS = {
    # Jolpica / schedule / standings / results (non-live)
    "next_race": "Next race",
    "track_time": "Track time",
    "race_week": "Race week",
    "current_season": "Current season",
    "driver_standings": "Driver standings",
    "constructor_standings": "Constructor standings",
    "weather": "Weather",
    "last_race_results": "Last race results",
    "season_results": "Season results",
    "sprint_results": "Sprint results",
    "lap_position_progression": "Lap position progression",
    "driver_points_progression": "Driver points progression",
    "constructor_points_progression": "Constructor points progression",
    "fia_documents": "FIA decisions",
    "calendar": "Season calendar",
    # Live timing / SignalR backed.
    "current_session": "Current session (live)",
    "track_weather": "Track weather (live)",
    "race_lap_count": "Race lap count (live)",
    "driver_list": "Driver list (live)",
    "current_tyres": "Current tyres (live)",
    "tyre_statistics": "Tyre statistics (live)",
    "track_status": "Track status (live)",
    "session_status": "Session status (live)",
    "session_time_remaining": "Session time remaining (live)",
    "session_time_elapsed": "Session time elapsed (live)",
    "race_time_to_three_hour_limit": "Race time to 3h limit (live)",
    "safety_car": "Safety car (live)",
    "on_track_incident": "On-track incident (live)",
    "possible_on_track_incident": "Possible on-track incident (live)",
    "formation_start": "Formation start (replay or live with F1TV access)",
    "race_control": "Race control (live)",
    "top_three": "Top three (leader, live)",
    "pitstops": "Pit stops (F1TV live/replay)",
    "championship_prediction": "Championship prediction (F1TV live/replay)",
    "driver_positions": "Driver positions (live)",
    "starting_grid": "Starting grid (live)",
    "track_limits": "Track limits (live)",
    "investigations": "Investigations & penalties (live)",
    "overtake_mode": "Overtake mode (live)",
    "straight_mode": "Straight mode (live)",
}


def _build_sensor_options() -> dict:
    options = dict(SENSOR_OPTIONS)
    if const.ENABLE_DEVELOPMENT_MODE_UI:
        options["live_timing_diagnostics"] = "Live timing online"
    return options


def _normalize_auth_header(value: object) -> str:
    """Return a normalized live timing authorization header."""
    return normalize_live_timing_auth_header(value)


class F1FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _pending_f1tv_setup_data: dict | None = None
    _completed_f1tv_pairing_session_id: str | None = None

    def _current_backend_language(self) -> str:
        """Return the current backend language for new config entries."""
        language = getattr(self.hass.config, "language", None)
        if not language:
            return DEFAULT_ENTITY_NAME_LANGUAGE
        normalized = str(language).strip().replace("_", "-")
        return normalized or DEFAULT_ENTITY_NAME_LANGUAGE

    def _normalize_race_week_start(self, data: dict) -> str:
        value = data.get(CONF_RACE_WEEK_START_DAY)
        if value in RACE_WEEK_START_OPTIONS:
            return value
        legacy = data.get(CONF_RACE_WEEK_SUNDAY_START)
        if isinstance(legacy, bool):
            return RACE_WEEK_START_SUNDAY if legacy else RACE_WEEK_START_MONDAY
        if legacy in RACE_WEEK_START_OPTIONS:
            return legacy
        return DEFAULT_RACE_WEEK_START_DAY

    async def async_step_user(self, user_input=None):
        errors = {}
        current = user_input or {}
        race_week_start = self._normalize_race_week_start(current)

        if user_input is not None:
            auth_header = _normalize_auth_header(
                user_input.pop(CONF_LIVE_TIMING_AUTH_HEADER, "")
            )
            start_pairing = bool(user_input.pop(CONF_START_F1TV_PAIRING, False))
            if is_auth_feature_enabled() and auth_header:
                user_input[CONF_LIVE_TIMING_AUTH_HEADER] = auth_header

            # Resolve and validate operation mode. Development/replay controls stay
            # tied to developer UI even when F1TV auth is public.
            mode = user_input.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
            if not const.ENABLE_DEVELOPMENT_MODE_UI or mode not in (
                OPERATION_MODE_LIVE,
                OPERATION_MODE_DEVELOPMENT,
            ):
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
                # Store disabled_sensors (what the user unchecked) instead of
                # enabled_sensors so that new sensors added in future versions
                # are automatically enabled.
                all_keys = set(_build_sensor_options().keys())
                checked = set(user_input.pop("enabled_sensors", all_keys))
                user_input["disabled_sensors"] = sorted(all_keys - checked)
                user_input[CONF_ENTITY_NAME_MODE] = ENTITY_NAME_MODE_LOCALIZED
                user_input[CONF_ENTITY_NAME_LANGUAGE] = self._current_backend_language()
                if start_pairing and is_auth_feature_enabled():
                    self._pending_f1tv_setup_data = dict(user_input)
                    return await self._async_start_f1tv_pairing(None)
                return self.async_create_entry(
                    title=user_input["sensor_name"], data=user_input
                )

        sensor_options = _build_sensor_options()
        all_sensor_keys = list(sensor_options.keys())

        # Build base schema
        schema_fields: dict = {
            vol.Required(
                "sensor_name", default=current.get("sensor_name", "F1")
            ): cv.string,
            vol.Required(
                "enabled_sensors",
                default=current.get("enabled_sensors", all_sensor_keys),
            ): cv.multi_select(sensor_options),
            vol.Optional("enable_race_control", default=False): cv.boolean,
            vol.Optional(
                CONF_RACE_WEEK_START_DAY,
                default=race_week_start,
            ): vol.In(RACE_WEEK_START_OPTIONS),
        }

        # Only expose development-related controls when explicitly enabled.
        # This keeps the main setup simple for normal users.
        if const.ENABLE_DEVELOPMENT_MODE_UI:
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
        if is_auth_feature_enabled():
            schema_fields.update(
                {
                    vol.Optional(CONF_START_F1TV_PAIRING, default=False): cv.boolean,
                    vol.Optional(
                        CONF_LIVE_TIMING_AUTH_HEADER, default=""
                    ): _AUTH_HEADER_SELECTOR,
                }
            )

        data_schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reconfigure(self, user_input=None):
        errors = {}

        entry = self._get_reconfigure_entry()
        current = entry.data
        race_week_start = self._normalize_race_week_start(current)

        if user_input is not None:
            auth_header = _normalize_auth_header(
                user_input.pop(CONF_LIVE_TIMING_AUTH_HEADER, "")
            )
            user_input.pop(CONF_CLEAR_LIVE_TIMING_AUTH_HEADER, None)
            start_pairing = bool(user_input.pop(CONF_START_F1TV_PAIRING, False))
            if start_pairing and is_auth_feature_enabled():
                return await self._async_start_f1tv_pairing(entry)
            if auth_header:
                if is_auth_feature_enabled():
                    user_input[CONF_LIVE_TIMING_AUTH_HEADER] = auth_header

            mode = user_input.get(
                CONF_OPERATION_MODE,
                current.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE),
            )
            if not const.ENABLE_DEVELOPMENT_MODE_UI or mode not in (
                OPERATION_MODE_LIVE,
                OPERATION_MODE_DEVELOPMENT,
            ):
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
                all_keys = set(_build_sensor_options().keys())
                checked = set(user_input.pop("enabled_sensors", all_keys))
                user_input["disabled_sensors"] = sorted(all_keys - checked)
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                )

        sensor_options = _build_sensor_options()
        all_sensor_keys = set(sensor_options.keys())

        # Build the default enabled list for reconfigure:
        # Use disabled_sensors (new format) if available, fall back to
        # enabled_sensors (legacy format), otherwise enable everything.
        raw_disabled = current.get("disabled_sensors")
        raw_enabled = current.get("enabled_sensors")
        if raw_disabled is not None:
            # New format: disabled_sensors stores what the user unchecked.
            # New sensor keys not in disabled are automatically checked.
            disabled_set = set(raw_disabled) & all_sensor_keys
            default_enabled = [k for k in sensor_options if k not in disabled_set]
        elif raw_enabled is not None:
            # Legacy format: enabled_sensors stores what was checked.
            # New sensor keys are auto-enabled.
            normalized: list[str] = []
            seen: set[str] = set()
            for key in raw_enabled:
                if key == "next_session":
                    key = "next_race"
                if key in all_sensor_keys and key not in seen:
                    normalized.append(key)
                    seen.add(key)
            for key in sensor_options:
                if key not in seen:
                    normalized.append(key)
            default_enabled = normalized
        else:
            default_enabled = list(sensor_options.keys())

        schema_fields: dict = {
            vol.Required(
                "sensor_name", default=current.get("sensor_name", "F1")
            ): cv.string,
            vol.Required(
                "enabled_sensors",
                default=default_enabled,
            ): cv.multi_select(sensor_options),
            vol.Optional(
                "enable_race_control",
                default=current.get("enable_race_control", False),
            ): cv.boolean,
            vol.Optional(
                CONF_RACE_WEEK_START_DAY,
                default=race_week_start,
            ): vol.In(RACE_WEEK_START_OPTIONS),
        }

        # Reconfigure keeps replay/development controls behind the developer UI
        # gate, independently of the public F1TV auth surface.
        show_dev_controls = const.ENABLE_DEVELOPMENT_MODE_UI

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
        if is_auth_feature_enabled():
            schema_fields.update(
                {
                    vol.Optional(CONF_START_F1TV_PAIRING, default=False): cv.boolean,
                    vol.Optional(
                        CONF_LIVE_TIMING_AUTH_HEADER, default=""
                    ): _AUTH_HEADER_SELECTOR,
                }
            )

        data_schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data=None):
        """Handle reauthentication for live timing authorization."""
        if not is_auth_feature_enabled():
            return self.async_abort(reason="reauth_not_supported")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Handle live timing authorization reauthentication."""
        if not is_auth_feature_enabled():
            return self.async_abort(reason="reauth_not_supported")

        errors = {}

        if user_input is not None:
            auth_header = _normalize_auth_header(
                user_input.get(CONF_LIVE_TIMING_AUTH_HEADER)
            )
            clear_auth_header = bool(
                user_input.get(CONF_CLEAR_LIVE_TIMING_AUTH_HEADER, False)
            )
            start_pairing = bool(user_input.get(CONF_START_F1TV_PAIRING, False))
            if start_pairing:
                return await self._async_start_f1tv_pairing(self._get_reauth_entry())
            if auth_header:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_LIVE_TIMING_AUTH_HEADER: auth_header},
                )
            if clear_auth_header:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_LIVE_TIMING_AUTH_HEADER: ""},
                )
            if not auth_header:
                errors[CONF_LIVE_TIMING_AUTH_HEADER] = "auth_header_required"

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_START_F1TV_PAIRING, default=False): cv.boolean,
                vol.Required(CONF_LIVE_TIMING_AUTH_HEADER): _AUTH_HEADER_SELECTOR,
                vol.Optional(CONF_CLEAR_LIVE_TIMING_AUTH_HEADER, default=False): (
                    cv.boolean
                ),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

    async def _async_start_f1tv_pairing(self, entry):
        """Start the helper pairing external step."""
        if not is_auth_feature_enabled():
            return self.async_abort(reason="f1tv_pairing_unavailable")
        async_setup_f1tv_auth_http(self.hass)
        session = async_create_f1tv_pairing_session(
            self.hass,
            entry,
            flow_id=self.flow_id,
        )
        if session is None:
            return self.async_abort(reason="f1tv_pairing_unavailable")
        return self.async_external_step(
            step_id="f1tv_pairing",
            url=session.helper_url,
            description_placeholders={"expires_at": session.expires_at_iso},
        )

    async def async_step_f1tv_pairing(self, user_input=None):
        """Complete the helper pairing external step."""
        if not is_auth_feature_enabled():
            return self.async_abort(reason="f1tv_pairing_unavailable")
        if isinstance(user_input, dict) and user_input.get("session_id"):
            self._completed_f1tv_pairing_session_id = str(user_input["session_id"])
            return self.async_external_step_done(next_step_id="f1tv_pairing_complete")
        return self.async_external_step_done(next_step_id="f1tv_pairing_failed")

    async def async_step_f1tv_pairing_complete(self, user_input=None):
        """Finish after the helper callback saved a token."""
        pending = self._pending_f1tv_setup_data
        if pending is not None:
            session_id = self._completed_f1tv_pairing_session_id
            result = async_pop_f1tv_pairing_session_result(
                self.hass, session_id or "", self.flow_id
            )
            if result is None:
                return self.async_abort(reason="f1tv_pairing_failed")
            auth_header, _status = result
            data = dict(pending)
            data[CONF_LIVE_TIMING_AUTH_HEADER] = auth_header
            self._pending_f1tv_setup_data = None
            self._completed_f1tv_pairing_session_id = None
            return self.async_create_entry(title=data["sensor_name"], data=data)
        return self.async_abort(reason="reconfigure_successful")

    async def async_step_f1tv_pairing_failed(self, user_input=None):
        """Abort when the helper callback did not complete."""
        return self.async_abort(reason="f1tv_pairing_failed")

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
