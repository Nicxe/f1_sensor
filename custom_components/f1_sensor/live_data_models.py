"""Runtime-owned live/replay projections. No Home Assistant entities are constructed."""

from __future__ import annotations

from contextlib import suppress
from copy import deepcopy
import datetime
from logging import getLogger
import math
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
)
from homeassistant.util import dt as dt_util

from .card_data_models import DataSnapshot
from .const import (
    LATEST_TRACK_STATUS,
)
from .data_helpers import (
    _extract_driver_position,
    _hex_to_rgb,
    _map_session_status_payload,
    _parse_lap_time_to_secs,
    _session_identity_year,
    _session_status_mapping_context,
)
from .entity import (
    entry_runtime_registry,
    is_auth_gated_stream_active,
    is_no_spoiler_live_state,
    is_replay_only_stream_active,
)
from .helpers import (
    normalize_track_status,
)
from .push_laps import empty_push_lap
from .static_data_models import ProjectionModel
from .stream_state import StreamStateMixin
from .team_radio_common import team_radio_clip_id
from .team_radio_media import team_radio_media_url

_TRACK_LIMITS_DELETED = re.compile(
    "CAR (\\d+) \\(([A-Z]{2,3})\\) (?:TIME [0-9:.]+|LAP) DELETED - TRACK LIMITS AT TURN (\\d+) LAP (\\d+)",
    re.IGNORECASE,
)

_TRACK_LIMITS_WARNING = re.compile(
    "BLACK AND WHITE FLAG FOR CAR (\\d+) \\(([A-Z]{2,3})\\) - TRACK LIMITS",
    re.IGNORECASE,
)

_TRACK_LIMITS_PENALTY = re.compile(
    "(\\d+ SECOND TIME PENALTY) FOR CAR (\\d+) \\(([A-Z]{2,3})\\) - TRACK LIMITS",
    re.IGNORECASE,
)

_DRIVER_PATTERN = re.compile("(?:CARS? )?(\\d+) \\(([A-Z]{2,3})\\)")

_INCIDENT_NOTED = re.compile(
    "(?:(?:UPDATE|CORRECTION):?\\s*)?(?:FIA STEWARDS:\\s*)?(?:(?:S?Q[123]|LAP \\d+)\\s+)?(?:(?:TURNS? \\d+(?:\\s+TO\\s+\\d+)?|PIT (?:LANE|EXIT|ENTRY)|START/FINISH STRAIGHT)\\s+)?INCIDENT(?: INVOLVING)? .+ NOTED",
    re.IGNORECASE,
)

_UNDER_INVESTIGATION = re.compile(
    "(?:FIA STEWARDS:|CORRECTION::?)\\s*.+ UNDER INVESTIGATION", re.IGNORECASE
)

_NO_FURTHER_INVESTIGATION = re.compile(
    "FIA STEWARDS:\\s*.+ (?:REVIEWED\\s+)?NO FURTHER (?:INVESTIGATION|ACTION)",
    re.IGNORECASE,
)

_PENALTY_ISSUED = re.compile(
    "FIA STEWARDS:\\s*(\\d+ SECOND TIME PENALTY|DRIVE THROUGH PENALTY|(?:\\d+\\s+(?:SECOND\\s+)?)?STOP(?:[-\\s]+AND[-\\s]+|/)?GO PENALTY|REPRIMAND \\([^)]+\\))\\s+FOR CAR (\\d+) \\(([A-Z]{2,3})\\)",
    re.IGNORECASE,
)

_PENALTY_SERVED = re.compile("FIA STEWARDS:\\s*PENALTY SERVED", re.IGNORECASE)

_WILL_BE_INVESTIGATED_AFTER = re.compile(
    "WILL BE INVESTIGATED AFTER THE (?:RACE|SESSION)", re.IGNORECASE
)

_LOCATION_PATTERN = re.compile(
    "(TURNS? \\d+(?:\\s+TO\\s+\\d+)?|PIT (?:LANE|EXIT|ENTRY)|START/FINISH STRAIGHT)",
    re.IGNORECASE,
)

_REASON_PATTERN = re.compile(
    "(?:NOTED|UNDER INVESTIGATION|NO FURTHER (?:INVESTIGATION|ACTION))\\s*-\\s*(.+?)$",
    re.IGNORECASE,
)


class LiveProjectionModel(StreamStateMixin, ProjectionModel):
    """Runtime-owned incremental calculation, independent of any entity."""

    def __init__(self, coordinator, unique_id=None, entry_id=None, device_name=None):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._stream_last_active = None
        self._last_inputs = None

    def _notify(self, *args):
        """Publication belongs to the owner after a complete projection."""

    def _schedule_stale_check(self, *args, **kwargs):
        """Freshness is evaluated by the runtime owner's single clock."""

    def snapshot(self):
        reg = entry_runtime_registry(self.hass, self._entry_id)
        for attribute, key in self.context_bindings.items():
            setattr(self, attribute, reg.get(key))
        dependency_keys = {
            "session_info_coordinator",
            "session_status_coordinator",
            *self.context_bindings.values(),
        }
        inputs = {key: getattr(reg.get(key), "data", None) for key in dependency_keys}
        status_coordinator = reg.get("session_status_coordinator")
        inputs["session_status_context"] = (
            *_session_status_mapping_context(status_coordinator, use_status_part=True),
            bool(getattr(status_coordinator, "is_testing_session", False)),
        )
        # Race Control keeps incremental messages separately from its latest row.
        inputs["messages"] = getattr(self.coordinator, "data_list", None)
        inputs["primary"] = self.coordinator.data
        live_state = reg.get("live_state")
        inputs["availability"] = (
            getattr(live_state, "is_live", False),
            getattr(live_state, "reason", None),
        )
        if inputs != self._last_inputs or type(self).__name__ in {
            "DriverPositionsModel",
            "InvestigationsModel",
        }:
            self._last_inputs = deepcopy(inputs)
            if hasattr(self, "_handle_session_info_update"):
                self._handle_session_info_update()
            if hasattr(self, "_handle_race_control_update"):
                self._handle_race_control_update()
            self.refresh_data()
        if type(self).__name__ == "DriverListModel" and self._attr_native_value is None:
            self._bootstrap_from_ergast()
        if type(self).__name__ == "LapCountModel":
            self._handle_stale_timeout()
        return DataSnapshot(self.state, deepcopy(self.extra_state_attributes))

    _persistent_fields = {
        "RaceControlModel": ("_last_event_id", "_history", "_sequence"),
        "TrackLimitsModel": ("_by_driver", "_processed_ids"),
        "InvestigationsModel": (
            "_noted",
            "_under_investigation",
            "_nfi",
            "_penalties",
            "_processed_ids",
            "_session_key",
            "_session_time",
        ),
        "TeamRadioModel": ("_last_utc", "_sequence"),
    }

    def export_state(self):
        """Persist an explicit allowlist of session accumulators, never runtime objects."""
        result = {}
        for name in self._persistent_fields.get(type(self).__name__, ()):
            value = getattr(self, name)
            result[name] = (
                sorted(value)
                if isinstance(value, set)
                else value.isoformat()
                if isinstance(value, datetime.datetime)
                else deepcopy(value)
            )
        return result

    def restore_state(self, saved):
        """Restore accumulators only after the owner validates session context."""
        if not isinstance(saved, dict):
            return
        for name in self._persistent_fields.get(type(self).__name__, ()):
            if name not in saved:
                continue
            value = deepcopy(saved[name])
            if name == "_processed_ids":
                value = set(value or [])
            elif name == "_session_time":
                value = dt_util.parse_datetime(value) if value else None
            setattr(self, name, value)

    context_bindings = {}


class AuthGatedProjection(LiveProjectionModel):
    _auth_gated_stream: str | None = None

    def _is_stream_active(self) -> bool:
        hass = getattr(self, "hass", None)
        entry_id = getattr(self, "_entry_id", None)
        return is_replay_only_stream_active(hass, entry_id) or (
            self._auth_gated_stream is not None
            and is_auth_gated_stream_active(hass, entry_id, self._auth_gated_stream)
        )


class CoordinatorStreamProjection(LiveProjectionModel):
    """Shared calculation for _CoordinatorStreamSensorBase."""

    def refresh_data(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        updated = self._update_from_coordinator()
        if not self._handle_stream_state(updated):
            return
        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return
        self._notify()

    def _update_from_coordinator(self) -> bool:
        raise NotImplementedError

    context_bindings = {"_session_info_coordinator": "session_info_coordinator"}


class PredictionProjection(LiveProjectionModel):
    """Shared calculation for _ChampionshipPredictionBase."""

    _DEFAULT_ICON = "mdi:trophy"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _is_stream_active(self) -> bool:
        hass = getattr(self, "hass", None)
        entry_id = getattr(self, "_entry_id", None)
        return is_replay_only_stream_active(
            hass, entry_id
        ) or is_auth_gated_stream_active(hass, entry_id, "ChampionshipPrediction")

    def refresh_data(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._notify()

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        raise NotImplementedError

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}


class TrackWeatherModel(LiveProjectionModel):
    """Shared calculation for TrackWeather."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        try:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None

    @property
    def available(self) -> bool:
        return super().available and self._attr_native_value is not None

    def _to_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and any(
            k in data for k in ("TrackTemp", "AirTemp", "Humidity")
        ):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            inner = data.get("data")
            if any(k in inner for k in ("TrackTemp", "AirTemp", "Humidity")):
                return inner
        history = getattr(self.coordinator, "data_list", None)
        if isinstance(history, list) and history:
            last = history[-1]
            if isinstance(last, dict) and any(
                k in last for k in ("TrackTemp", "AirTemp", "Humidity")
            ):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        track_temp = self._to_float(raw.get("TrackTemp"))
        air_temp = self._to_float(raw.get("AirTemp"))
        humidity = self._to_float(raw.get("Humidity"))
        pressure = self._to_float(raw.get("Pressure"))
        rainfall = self._to_float(raw.get("Rainfall"))
        wind_dir = self._to_float(raw.get("WindDirection"))
        wind_speed = self._to_float(raw.get("WindSpeed"))
        measurement_inferred = False
        now_utc = dt_util.utcnow()
        with suppress(Exception):
            utc_raw = (
                raw.get("Utc")
                or raw.get("utc")
                or raw.get("processedAt")
                or raw.get("timestamp")
            )
            if utc_raw:
                ts = datetime.datetime.fromisoformat(
                    str(utc_raw).replace("Z", "+00:00")
                )
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.UTC)
                self._last_timestamped_dt = ts
            else:
                measurement_inferred = True
        with suppress(Exception):
            getLogger(__name__).debug(
                "TrackWeather sensor state computed at %s, raw=%s -> air_temp=%s (inferred_ts=%s)",
                now_utc.isoformat(timespec="seconds"),
                raw,
                air_temp,
                measurement_inferred,
            )
        self._attr_native_value = air_temp
        self._last_received_utc = now_utc
        self._attr_extra_state_attributes = {
            "air_temperature": air_temp,
            "air_temperature_unit": "celsius",
            "humidity": humidity,
            "humidity_unit": "%",
            "pressure": pressure,
            "pressure_unit": "hPa",
            "rainfall": rainfall,
            "rainfall_unit": "mm",
            "track_temperature": track_temp,
            "track_temperature_unit": "celsius",
            "wind_speed": wind_speed,
            "wind_speed_unit": "m/s",
            "wind_from_direction_degrees": wind_dir,
            "wind_from_direction_unit": "degrees",
            "measurement_inferred": measurement_inferred,
        }

    def refresh_data(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if raw is None:
            with suppress(Exception):
                getLogger(__name__).debug(
                    "TrackWeather: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            self._notify()
            return
        self._apply_payload(raw)
        self._notify()

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None


class TrackStatusModel(LiveProjectionModel):
    """Shared calculation for TrackStatus."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._session_status_coordinator = None
        self._forced_unavailable = False
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None

    def _normalize(self, raw: dict | None) -> str | None:
        return normalize_track_status(raw)

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if not data:
            with suppress(Exception):
                hist = getattr(self.coordinator, "data_list", None)
                if isinstance(hist, list) and hist:
                    last = hist[-1]
                    if isinstance(last, dict):
                        return last
            with suppress(Exception):
                cache = self.hass.data.get(LATEST_TRACK_STATUS)
                if isinstance(cache, dict):
                    return cache
            return None
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
        return None

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def state(self):
        return self._attr_native_value

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not self._forced_unavailable

    def _session_is_terminal(self) -> bool:
        payload = getattr(self._session_status_coordinator, "data", None)
        is_qualifying_like, qualifying_part = _session_status_mapping_context(
            self._session_status_coordinator, use_status_part=True
        )
        mapped = _map_session_status_payload(
            payload,
            self.hass,
            is_qualifying_like=is_qualifying_like,
            qualifying_part=qualifying_part,
            is_testing_session=bool(
                getattr(self._session_status_coordinator, "is_testing_session", False)
            ),
        )
        return mapped in {"finished", "finalised", "ended"}

    def _handle_session_status_update(self) -> None:
        if not self._session_is_terminal():
            if self._forced_unavailable:
                TrackStatusModel.refresh_data(self)
            return
        if self._forced_unavailable:
            return
        self._clear_state()
        self._notify()

    def refresh_data(self) -> None:
        raw = self._extract_current()
        if self._session_is_terminal():
            self._clear_state()
            self._notify()
            return
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if raw is None:
            return
        new_state = self._normalize(raw)
        prev = self._attr_native_value
        if prev == new_state:
            return
        with suppress(Exception):
            from logging import getLogger

            getLogger(__name__).debug(
                "TrackStatus changed at %s: %s -> %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev,
                new_state,
            )
        self._attr_native_value = new_state
        self._forced_unavailable = False
        self._notify()

    @property
    def extra_state_attributes(self):
        return {}

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._forced_unavailable = True

    context_bindings = {"_session_status_coordinator": "session_status_coordinator"}


class SessionStatusModel(LiveProjectionModel):
    """Shared calculation for SessionStatus."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._started_flag = None
        self._session_info_coordinator = None
        self._race_control_coordinator = None
        self._track_grip_state: str | None = None
        self._attr_extra_state_attributes = {}
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
        return None

    def _extract_session_info(self) -> dict:
        """Extract session info attributes from SessionInfoCoordinator."""
        attrs = {}
        with suppress(Exception):
            if self._session_info_coordinator is None:
                return attrs
            data = self._session_info_coordinator.data
            if not isinstance(data, dict):
                return attrs
            meeting = data.get("Meeting") or {}
            circuit = (
                meeting.get("Circuit") if isinstance(meeting, dict) else None
            ) or {}
            attrs.update(
                {
                    "meeting_name": (meeting or {}).get("Name"),
                    "meeting_location": (meeting or {}).get("Location"),
                    "meeting_country": ((meeting or {}).get("Country") or {}).get(
                        "Name"
                    ),
                    "circuit_short_name": (circuit or {}).get("ShortName"),
                    "gmt_offset": data.get("GmtOffset"),
                    "start": data.get("StartDate"),
                    "end": data.get("EndDate"),
                }
            )
        return attrs

    def _handle_session_info_update(self) -> None:
        """Update attributes when SessionInfo changes."""
        if not self._is_stream_active():
            return
        new_attrs = self._extract_session_info()
        if new_attrs != self._attr_extra_state_attributes:
            self._attr_extra_state_attributes = new_attrs
            self._notify()

    def _detect_track_grip(self) -> str | None:
        """Detect current track grip condition from Race Control messages.

        Returns:
            "low": LOW GRIP CONDITIONS declared
            "normal": NORMAL GRIP CONDITIONS declared or default when unset
            None: No data available yet
        """
        if self._race_control_coordinator is None:
            return self._track_grip_state
        messages = getattr(self._race_control_coordinator, "data_list", None)
        if not isinstance(messages, list) or not messages:
            return self._track_grip_state
        for msg in reversed(messages):
            message_text = (msg.get("Message") or msg.get("Text") or "").upper()
            if "LOW GRIP CONDITIONS" in message_text:
                self._track_grip_state = "low"
                return "low"
            if "NORMAL GRIP CONDITIONS" in message_text:
                self._track_grip_state = "normal"
                return "normal"
        if self._track_grip_state is None:
            self._track_grip_state = "normal"
        return self._track_grip_state

    def _handle_race_control_update(self) -> None:
        """Update track_grip attribute when race control messages change."""
        if not self._is_stream_active():
            return
        grip = self._detect_track_grip()
        current = self._attr_extra_state_attributes.get("track_grip")
        if current != grip:
            self._attr_extra_state_attributes["track_grip"] = grip
            self._notify()

    def _map_status(self, raw: dict | None) -> str | None:
        is_qualifying_like, qualifying_part = _session_status_mapping_context(
            self.coordinator, use_status_part=True
        )
        return _map_session_status_payload(
            raw,
            self.hass,
            is_qualifying_like=is_qualifying_like,
            qualifying_part=qualifying_part,
            is_testing_session=bool(
                getattr(self.coordinator, "is_testing_session", False)
            ),
        )

    def refresh_data(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if raw is None:
            return
        new_state = self._map_status(raw)
        prev = self._attr_native_value
        with suppress(Exception):
            getLogger(__name__).debug(
                "SessionStatus: coordinator update, raw=%s, mapped=%s, prev=%s",
                raw,
                new_state,
                prev,
            )
        if prev == new_state:
            return
        with suppress(Exception):
            getLogger(__name__).debug(
                "SessionStatus changed at %s: %s -> %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev,
                new_state,
            )
        self._attr_native_value = new_state
        self._notify()

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._started_flag = None
        self._track_grip_state = None
        self._attr_extra_state_attributes = {}

    context_bindings = {
        "_session_info_coordinator": "session_info_coordinator",
        "_race_control_coordinator": "race_control_coordinator",
    }


class SessionClockModel(LiveProjectionModel):
    """Shared calculation for SessionClockBase."""

    _value_key: str = ""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @staticmethod
    def _format_hms(value: int | None) -> str | None:
        if not isinstance(value, int) or value < 0:
            return None
        hours = value // 3600
        minutes = value % 3600 // 60
        seconds = value % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    def _extract_state(self) -> dict | None:
        data = getattr(self.coordinator, "data", None)
        return data if isinstance(data, dict) else None

    def _extract_value(self, state: dict) -> int | None:
        raw = state.get(self._value_key)
        try:
            if raw is None:
                return None
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _is_value_available(self, state: dict, value: int | None) -> bool:
        source_quality = str(state.get("source_quality") or "").strip()
        return value is not None and source_quality != "unavailable"

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        return {
            "session_type": state.get("session_type"),
            "session_name": state.get("session_name"),
            "session_part": state.get("session_part"),
            "session_status": state.get("session_status"),
            "clock_phase": state.get("clock_phase"),
            "clock_running": state.get("clock_running"),
            "source_quality": state.get("source_quality"),
            "session_start_utc": state.get("session_start_utc"),
            "reference_utc": state.get("reference_utc"),
            "last_server_utc": state.get("last_server_utc"),
            "value_seconds": value,
            "formatted_hms": self._format_hms(value),
        }

    def refresh_data(self) -> None:
        state = self._extract_state()
        if not isinstance(state, dict):
            return
        value = self._extract_value(state)
        source_quality = str(state.get("source_quality") or "").strip()
        if value is None and source_quality == "unavailable":
            self._notify()
            return
        value_text = self._format_hms(value)
        attrs = self._build_attrs(state, value)
        if (
            self._attr_native_value == value_text
            and self._attr_extra_state_attributes == attrs
        ):
            return
        self._attr_native_value = value_text
        self._attr_extra_state_attributes = attrs
        self._notify()

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        state = self._extract_state()
        if not isinstance(state, dict):
            return False
        value = self._extract_value(state)
        return self._is_value_available(state, value)

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}


class TimeRemainingModel(SessionClockModel):
    """Shared calculation for SessionTimeRemaining."""

    _value_key = "clock_remaining_s"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["clock_total_s"] = state.get("clock_total_s")
        return attrs


class TimeElapsedModel(SessionClockModel):
    """Shared calculation for SessionTimeElapsed."""

    _value_key = "clock_elapsed_s"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["clock_total_s"] = state.get("clock_total_s")
        attrs["clock_remaining_s"] = state.get("clock_remaining_s")
        return attrs


class RaceLimitModel(SessionClockModel):
    """Shared calculation for RaceTimeToThreeHourLimit."""

    _value_key = "race_three_hour_remaining_s"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    @staticmethod
    def _is_main_race(state: dict) -> bool:
        session_type = str(state.get("session_type") or "").strip().lower()
        session_name = str(state.get("session_name") or "").strip().lower()
        return session_type == "race" and "sprint" not in session_name

    def _is_value_available(self, state: dict, value: int | None) -> bool:
        if not self._is_main_race(state):
            return False
        return super()._is_value_available(state, value)

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["race_start_utc"] = state.get("race_start_utc")
        attrs["race_three_hour_cap_utc"] = state.get("race_three_hour_cap_utc")
        return attrs


class CurrentSessionModel(LiveProjectionModel):
    """Shared calculation for CurrentSession."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        self._status_coordinator = None

    def _is_replay_active(self) -> bool:
        """Return True when replay mode is playing or paused."""
        reg = entry_runtime_registry(self.hass, self._entry_id)
        replay_controller = reg.get("replay_controller")
        if replay_controller is None:
            return False
        try:
            from .replay_mode import ReplayState

            return replay_controller.state in (ReplayState.PLAYING, ReplayState.PAUSED)
        except Exception:
            return False

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and any(
            k in data for k in ("Type", "Name", "Meeting")
        ):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and any(
            k in inner for k in ("Type", "Name", "Meeting")
        ):
            return inner
        return None

    def _resolve_label(self, info: dict) -> tuple[str | None, dict]:
        t = str(info.get("Type") or "").strip()
        name = str(info.get("Name") or "").strip()
        num = info.get("Number")
        try:
            num_i = int(num) if num is not None else None
        except Exception:
            num_i = None
        session_part = None
        try:
            drivers_data = entry_runtime_registry(self.hass, self._entry_id).get(
                "drivers_coordinator"
            )
            if drivers_data and hasattr(drivers_data, "data"):
                sd = drivers_data.data or {}
                session = sd.get("session") or {}
                session_part = session.get("part")
        except Exception:
            session_part = None
        label = None
        if t == "Practice":
            label = f"Practice {num_i}" if num_i else name or "Practice"
        elif t == "Qualifying":
            nm = name.lower()
            is_sprint_quali = nm.startswith("sprint qualifying") or nm.startswith(
                "sprint shootout"
            )
            label = "Sprint Qualifying" if is_sprint_quali else "Qualifying"
        elif t == "Race":
            nm = name.lower()
            if nm.startswith("sprint qualifying") or nm.startswith("sprint shootout"):
                label = "Sprint Qualifying"
            elif nm.startswith("sprint"):
                label = "Sprint"
            else:
                label = name or "Race"
        else:
            label = name or t or None
        meta = {
            "type": t or None,
            "name": name or None,
            "number": num_i,
            "session_part": session_part,
        }
        return (label, meta)

    def _live_status_payload(self) -> dict | None:
        try:
            if self._status_coordinator and isinstance(
                self._status_coordinator.data, dict
            ):
                return self._status_coordinator.data
        except Exception:
            return None
        return None

    def _live_status(self) -> str | None:
        payload = self._live_status_payload()
        if isinstance(payload, dict):
            return str(payload.get("Status") or payload.get("Message") or "").strip()
        return None

    def _mapped_live_status(self) -> str | None:
        is_qualifying_like, qualifying_part = _session_status_mapping_context(
            self._status_coordinator, use_status_part=True
        )
        return _map_session_status_payload(
            self._live_status_payload(),
            self.hass,
            is_qualifying_like=is_qualifying_like,
            qualifying_part=qualifying_part,
            is_testing_session=bool(
                getattr(self._status_coordinator, "is_testing_session", False)
            ),
        )

    def _apply_payload(self, raw: dict, allow_clear: bool = True) -> None:
        label, meta = self._resolve_label(raw or {})
        status = self._live_status()
        mapped_status = self._mapped_live_status()
        ended = mapped_status in ("finished", "finalised", "ended")
        with suppress(Exception):
            end_iso = raw.get("EndDate")
            if end_iso and (not ended) and (not self._is_replay_active()):
                end_dt = datetime.datetime.fromisoformat(
                    str(end_iso).replace("Z", "+00:00")
                )
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=datetime.UTC)
                now_utc = datetime.datetime.now(datetime.UTC)
                if now_utc >= end_dt + datetime.timedelta(minutes=5):
                    st = str(status or "").strip()
                    if st not in ("Started", "Green", "GreenFlag"):
                        ended = True
        active = mapped_status == "live"
        desired_state = None
        if label in ("Qualifying", "Sprint Qualifying"):
            desired_state = None if ended else label
        else:
            desired_state = label if active else None
        if desired_state is None and (not allow_clear):
            desired_state = self._attr_native_value
        self._attr_native_value = desired_state
        attrs = dict(meta)
        with suppress(Exception):
            meeting = raw.get("Meeting") or {}
            circuit = (
                meeting.get("Circuit") if isinstance(meeting, dict) else None
            ) or {}
            attrs.update(
                {
                    "season": _session_identity_year(raw.get("StartDate")),
                    "session_key": raw.get("Key"),
                    "meeting_key": (meeting or {}).get("Key"),
                    "meeting_name": (meeting or {}).get("Name"),
                    "meeting_location": (meeting or {}).get("Location"),
                    "meeting_country": ((meeting or {}).get("Country") or {}).get(
                        "Name"
                    ),
                    "circuit_short_name": (circuit or {}).get("ShortName"),
                    "gmt_offset": raw.get("GmtOffset"),
                    "start": raw.get("StartDate"),
                    "end": raw.get("EndDate"),
                }
            )
        with suppress(Exception):
            attrs["live_status"] = status
            attrs["active"] = active
            if not active and label:
                attrs["last_label"] = label
        self._attr_extra_state_attributes = attrs
        with suppress(Exception):
            getLogger(__name__).debug(
                "CurrentSession apply: label=%s status=%s mapped=%s ended=%s active=%s",
                label,
                status,
                mapped_status,
                ended,
                active,
            )

    def refresh_data(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if raw is None:
            with suppress(Exception):
                getLogger(__name__).debug(
                    "CurrentSession: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            return
        self._apply_payload(raw)
        self._notify()

    def _handle_status_update(self) -> None:
        raw = self._extract_current() or {}
        if not self._handle_stream_state(True):
            return
        if not self._is_stream_active():
            self._notify()
            return
        self._apply_payload(raw)
        with suppress(Exception):
            getLogger(__name__).debug(
                "CurrentSession: Status update at %s -> state=%s, live_status=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
                self._live_status(),
            )
        self._notify()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    context_bindings = {"_status_coordinator": "session_status_coordinator"}


class RaceControlModel(LiveProjectionModel):
    """Shared calculation for RaceControl."""

    _history_limit = 5

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_event_id: str | None = None
        self._history: list[dict] = []
        self._sequence = 0

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and data:
            return data
        hist = getattr(self.coordinator, "data_list", None)
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, dict):
                return last
        return None

    def _cleanup_string(self, value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _build_event_id(self, payload: dict) -> str | None:
        ts = (
            self._cleanup_string(
                payload.get("Utc")
                or payload.get("utc")
                or payload.get("processedAt")
                or payload.get("timestamp")
            )
            or ""
        )
        category = (
            self._cleanup_string(
                payload.get("Category") or payload.get("CategoryType") or ""
            )
            or ""
        )
        message = (
            self._cleanup_string(
                payload.get("Message")
                or payload.get("Text")
                or payload.get("Flag")
                or ""
            )
            or ""
        )
        ident = f"{ts}|{category}|{message}"
        return ident if ident.strip("|") else None

    def _resolve_icon(self, flag: str | None, category: str | None) -> str:
        flag_upper = (flag or "").upper()
        if flag_upper in ("RED", "BLACK"):
            return "mdi:flag-variant"
        if flag_upper in ("YELLOW", "DOUBLE YELLOW"):
            return "mdi:flag"
        if flag_upper in ("GREEN", "CLEAR"):
            return "mdi:flag-checkered"
        if flag_upper in ("BLUE", "WHITE"):
            return "mdi:flag-variant-outline"
        if str(category or "").lower() == "safetycar":
            return "mdi:car-emergency"
        if str(category or "").lower() == "vsc":
            return "mdi:car-brake-alert"
        return "mdi:flag-outline"

    def _format_state(self, payload: dict) -> str:
        message = self._cleanup_string(payload.get("Message") or payload.get("Text"))
        if message:
            return message[:255]
        flag = self._cleanup_string(payload.get("Flag"))
        category = self._cleanup_string(
            payload.get("Category") or payload.get("CategoryType")
        )
        scope = self._cleanup_string(payload.get("Scope"))
        sector = self._cleanup_string(payload.get("Sector"))
        parts = [part for part in (flag, category, scope, sector) if part]
        return " - ".join(parts) if parts else "Race control update"

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        event_id = self._build_event_id(payload)
        if event_id and self._last_event_id == event_id and (not force):
            return
        utc_str = self._cleanup_string(
            payload.get("Utc")
            or payload.get("utc")
            or payload.get("processedAt")
            or payload.get("timestamp")
        )
        try:
            if utc_str:
                dt = datetime.datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.UTC)
                utc_str = dt.astimezone(datetime.UTC).isoformat(timespec="seconds")
        except Exception:
            utc_str = self._cleanup_string(utc_str)
        category = self._cleanup_string(
            payload.get("Category") or payload.get("CategoryType")
        )
        flag = self._cleanup_string(payload.get("Flag"))
        scope = self._cleanup_string(payload.get("Scope"))
        sector = self._cleanup_string(
            payload.get("Sector") or payload.get("TrackSegment")
        )
        car_number = self._cleanup_string(
            payload.get("CarNumber")
            or payload.get("Number")
            or payload.get("Car")
            or payload.get("Driver")
        )
        message = self._format_state(payload)
        received_at = dt_util.utcnow().isoformat(timespec="seconds")
        self._sequence += 1
        attrs = {
            "utc": utc_str,
            "received_at": received_at,
            "category": category,
            "flag": flag,
            "scope": scope,
            "sector": sector,
            "car_number": car_number,
            "message": self._cleanup_string(
                payload.get("Message") or payload.get("Text")
            ),
            "event_id": event_id,
            "sequence": self._sequence,
            "raw_message": payload,
        }
        history_entry = {
            "event_id": event_id,
            "utc": utc_str,
            "category": category,
            "flag": flag,
            "message": attrs["message"] or message,
        }
        self._history.insert(0, history_entry)
        self._history = self._history[: self._history_limit]
        attrs["history"] = [dict(item) for item in self._history]
        self._attr_native_value = message
        self._attr_extra_state_attributes = attrs
        self._attr_icon = self._resolve_icon(flag, category)
        if event_id:
            self._last_event_id = event_id

    def refresh_data(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._notify()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_event_id = None
        self._history = []
        self._sequence = 0


class TrackLimitsModel(LiveProjectionModel):
    """Shared calculation for TrackLimits."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = 0
        self._by_driver: dict[str, dict] = {}
        self._processed_ids: set[str] = set()
        self._live_state_unsub = None
        self._attr_extra_state_attributes = {
            "by_driver": {},
            "total_deletions": 0,
            "total_warnings": 0,
            "total_penalties": 0,
            "last_update": None,
        }

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init" or is_no_spoiler_live_state(reason):
            return
        if not is_live:
            self._clear_state()
            self._notify()

    def _build_message_id(self, msg: dict) -> str:
        utc = msg.get("Utc") or msg.get("utc") or ""
        message = msg.get("Message") or ""
        return f"{utc}|{message}"

    def _process_message(self, msg: dict) -> bool:
        """Process a single race control message for track limits data.

        Returns True if a new violation was detected.
        """
        message_text = msg.get("Message") or ""
        if "TRACK LIMITS" not in message_text.upper():
            return False
        msg_id = self._build_message_id(msg)
        if msg_id in self._processed_ids:
            return False
        self._processed_ids.add(msg_id)
        utc = msg.get("Utc") or msg.get("utc")
        lap = msg.get("Lap")
        match = _TRACK_LIMITS_DELETED.search(message_text)
        if match:
            racing_number, tla, turn, violation_lap = match.groups()
            lap_value = lap
            try:
                if violation_lap:
                    lap_value = int(violation_lap)
            except (TypeError, ValueError):
                lap_value = lap
            self._add_violation(
                tla=tla.upper(),
                racing_number=racing_number,
                violation_type="time_deleted",
                utc=utc,
                lap=lap_value,
                turn=int(turn),
            )
            return True
        match = _TRACK_LIMITS_WARNING.search(message_text)
        if match:
            racing_number, tla = match.groups()
            self._add_violation(
                tla=tla.upper(),
                racing_number=racing_number,
                violation_type="warning",
                utc=utc,
                lap=lap,
                turn=None,
            )
            return True
        match = _TRACK_LIMITS_PENALTY.search(message_text)
        if match:
            penalty_text, racing_number, tla = match.groups()
            self._add_violation(
                tla=tla.upper(),
                racing_number=racing_number,
                violation_type="penalty",
                utc=utc,
                lap=lap,
                turn=None,
                penalty=penalty_text.upper(),
            )
            return True
        return False

    def _add_violation(
        self,
        *,
        tla: str,
        racing_number: str,
        violation_type: str,
        utc: str | None,
        lap: int | None,
        turn: int | None,
        penalty: str | None = None,
    ) -> None:
        """Add a violation to the driver's record."""
        if tla not in self._by_driver:
            self._by_driver[tla] = {
                "racing_number": racing_number,
                "deletions": 0,
                "warning": False,
                "penalty": None,
                "violations": [],
            }
        driver_data = self._by_driver[tla]
        violation = {"utc": utc, "lap": lap, "turn": turn, "type": violation_type}
        if violation_type == "time_deleted":
            driver_data["deletions"] += 1
        elif violation_type == "warning":
            driver_data["warning"] = True
        elif violation_type == "penalty":
            driver_data["penalty"] = penalty
            violation["penalty"] = penalty
        driver_data["violations"].append(violation)

    def _process_all_messages(self) -> None:
        """Process all messages from the coordinator."""
        messages = getattr(self.coordinator, "data_list", None)
        if not isinstance(messages, list):
            return
        for msg in messages:
            if isinstance(msg, dict):
                self._process_message(msg)
        self._update_attributes()

    def _update_attributes(self) -> None:
        """Update sensor attributes and state."""
        total_deletions = sum(d.get("deletions", 0) for d in self._by_driver.values())
        total_warnings = sum(1 for d in self._by_driver.values() if d.get("warning"))
        total_penalties = sum(
            1 for d in self._by_driver.values() if d.get("penalty") is not None
        )
        self._attr_native_value = total_deletions + total_warnings
        self._attr_extra_state_attributes = {
            "by_driver": dict(self._by_driver),
            "total_deletions": total_deletions,
            "total_warnings": total_warnings,
            "total_penalties": total_penalties,
            "last_update": dt_util.utcnow().isoformat(timespec="seconds"),
        }

    def refresh_data(self) -> None:
        messages = getattr(self.coordinator, "data_list", None)
        updated = isinstance(messages, list) and len(messages) > 0
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if not isinstance(messages, list):
            return
        changed = False
        for msg in messages:
            if isinstance(msg, dict) and self._process_message(msg):
                changed = True
        if changed:
            self._update_attributes()
            self._notify()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = 0
        self._by_driver = {}
        self._processed_ids = set()
        self._attr_extra_state_attributes = {
            "by_driver": {},
            "total_deletions": 0,
            "total_warnings": 0,
            "total_penalties": 0,
            "last_update": None,
        }


class InvestigationsModel(LiveProjectionModel):
    """Shared calculation for Investigations."""

    NFI_EXPIRY_SECONDS = 300

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = 0
        self._noted: dict[str, dict] = {}
        self._under_investigation: dict[str, dict] = {}
        self._nfi: dict[str, dict] = {}
        self._penalties: list[dict] = []
        self._processed_ids: set[str] = set()
        self._live_state_unsub = None
        self._session_info_coordinator = None
        self._session_key: str | None = None
        self._session_time: datetime.datetime | None = None
        self._attr_extra_state_attributes = {
            "noted": [],
            "under_investigation": [],
            "no_further_action": [],
            "penalties": [],
            "last_update": None,
            "session_key": None,
        }

    def _make_incident_key(
        self, drivers: list[str], location: str | None, reason: str | None
    ) -> str:
        """Create a unique key for matching incidents.

        Uses sorted drivers so BEA/LAW matches LAW/BEA.
        """
        sorted_drivers = tuple(sorted(drivers))
        return f"{sorted_drivers}|{location or ''}|{reason or ''}"

    def _find_incident_by_drivers(
        self, driver_tlas: list[str], collection: dict[str, dict]
    ) -> str | None:
        """Find an incident key in a collection by matching drivers exactly (any order).

        Returns the key if found, None otherwise.
        """
        sorted_input = set(driver_tlas)
        for key, incident in collection.items():
            if set(incident.get("drivers", [])) == sorted_input:
                return key
        return None

    def _find_incident_containing_driver(
        self, driver_tla: str, collection: dict[str, dict]
    ) -> str | None:
        """Find an incident where the driver is involved (partial match).

        Used for penalty matching where only one driver is mentioned.
        Returns the key if found, None otherwise.
        """
        for key, incident in collection.items():
            if driver_tla in incident.get("drivers", []):
                return key
        return None

    def _current_session_key(self) -> str | None:
        """Return the current live-timing session identity when available."""
        data = getattr(self._session_info_coordinator, "data", None)
        if not isinstance(data, dict):
            return None
        key = data.get("Key")
        if key is None:
            return None
        return str(key).strip() or None

    def _handle_session_info_update(self) -> None:
        """Reset investigation state when the live feed changes session."""
        session_key = self._current_session_key()
        if session_key is None or session_key == self._session_key:
            return
        previous_session_key = self._session_key
        self._session_key = session_key
        if previous_session_key is None:
            self._attr_extra_state_attributes["session_key"] = session_key
        else:
            self._clear_state()
        self._notify()

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init" or is_no_spoiler_live_state(reason):
            return
        if not is_live:
            self._clear_state()
            self._notify()

    def _build_message_id(self, msg: dict) -> str:
        utc = msg.get("Utc") or msg.get("utc") or ""
        message = msg.get("Message") or ""
        return f"{utc}|{message}"

    def _extract_drivers(self, message: str) -> list[tuple[str, str]]:
        """Extract all drivers (racing_number, tla) from a message."""
        return [
            (m.group(1), m.group(2).upper()) for m in _DRIVER_PATTERN.finditer(message)
        ]

    def _extract_location(self, message: str) -> str | None:
        """Extract location (TURN X, PIT LANE, etc.) from message."""
        match = _LOCATION_PATTERN.search(message)
        return match.group(1).upper() if match else None

    def _extract_reason(self, message: str) -> str | None:
        """Extract reason from message."""
        match = _REASON_PATTERN.search(message)
        return match.group(1).strip().upper() if match else None

    def _expire_nfi_items(self) -> bool:
        """Remove NFI items older than NFI_EXPIRY_SECONDS.

        Uses session time (latest message timestamp) for comparison,
        so expiry works correctly during replay mode.
        Returns True if any removed.
        """
        if self._session_time is None:
            return False
        expired_keys = []
        for key, item in self._nfi.items():
            nfi_utc = item.get("nfi_utc")
            if nfi_utc:
                with suppress((ValueError, TypeError)):
                    nfi_time = dt_util.parse_datetime(nfi_utc)
                    if (
                        nfi_time
                        and (self._session_time - nfi_time).total_seconds()
                        > self.NFI_EXPIRY_SECONDS
                    ):
                        expired_keys.append(key)
        for key in expired_keys:
            del self._nfi[key]
        return len(expired_keys) > 0

    def _process_message(self, msg: dict) -> bool:
        """Process a single race control message for investigation/penalty data.

        Returns True if state changed.
        """
        message_text = msg.get("Message") or ""
        message_upper = message_text.upper()
        if not any(
            kw in message_upper
            for kw in [
                "NOTED",
                "INVESTIGATION",
                "INVESTIGATED",
                "PENALTY",
                "REPRIMAND",
                "NO FURTHER",
            ]
        ):
            return False
        if "TRACK LIMITS" in message_upper:
            if (
                "PENALTY" not in message_upper
                and "INVESTIGATION" not in message_upper
                and ("NOTED" not in message_upper)
            ):
                return False
            if "DELETED" in message_upper:
                return False
        msg_id = self._build_message_id(msg)
        if msg_id in self._processed_ids:
            return False
        self._processed_ids.add(msg_id)
        utc = msg.get("Utc") or msg.get("utc")
        lap = msg.get("Lap")
        if utc:
            with suppress((ValueError, TypeError)):
                msg_time = dt_util.parse_datetime(utc)
                if msg_time and (
                    self._session_time is None or msg_time > self._session_time
                ):
                    self._session_time = msg_time
        drivers = self._extract_drivers(message_text)
        location = self._extract_location(message_text)
        reason = self._extract_reason(message_text)
        driver_tlas = [d[1] for d in drivers]
        racing_numbers = [d[0] for d in drivers]
        if _PENALTY_SERVED.search(message_text):
            if drivers:
                tlas_set = set(driver_tlas)
                self._penalties = [
                    p for p in self._penalties if p.get("driver") not in tlas_set
                ]
            return True
        match = _PENALTY_ISSUED.search(message_text)
        if match:
            penalty_text = match.group(1).upper()
            racing_number = match.group(2)
            tla = match.group(3).upper()
            key_noted = self._find_incident_containing_driver(tla, self._noted)
            if key_noted:
                del self._noted[key_noted]
            key_inv = self._find_incident_containing_driver(
                tla, self._under_investigation
            )
            if key_inv:
                del self._under_investigation[key_inv]
            self._penalties.append(
                {
                    "driver": tla,
                    "racing_number": racing_number,
                    "penalty": penalty_text,
                    "reason": reason,
                    "utc": utc,
                    "lap": lap,
                }
            )
            return True
        if _NO_FURTHER_INVESTIGATION.search(message_text):
            if drivers:
                key = self._find_incident_by_drivers(driver_tlas, self._noted)
                incident = None
                if key:
                    incident = self._noted.pop(key)
                else:
                    key = self._find_incident_by_drivers(
                        driver_tlas, self._under_investigation
                    )
                    if key:
                        incident = self._under_investigation.pop(key)
                nfi_key = self._make_incident_key(driver_tlas, location, reason)
                self._nfi[nfi_key] = {
                    "utc": incident.get("utc") if incident else utc,
                    "lap": incident.get("lap") if incident else lap,
                    "drivers": sorted(driver_tlas),
                    "racing_numbers": racing_numbers,
                    "location": location,
                    "reason": reason,
                    "nfi_utc": utc,
                }
            return True
        if _UNDER_INVESTIGATION.search(message_text):
            if drivers:
                key = self._find_incident_by_drivers(driver_tlas, self._noted)
                if key:
                    incident = self._noted.pop(key)
                    new_key = self._make_incident_key(
                        driver_tlas, location, reason or incident.get("reason")
                    )
                    self._under_investigation[new_key] = {
                        "utc": incident.get("utc"),
                        "lap": incident.get("lap"),
                        "drivers": sorted(driver_tlas),
                        "racing_numbers": racing_numbers,
                        "location": location or incident.get("location"),
                        "reason": reason or incident.get("reason"),
                    }
                    return True
                new_key = self._make_incident_key(driver_tlas, location, reason)
                if new_key not in self._under_investigation:
                    self._under_investigation[new_key] = {
                        "utc": utc,
                        "lap": lap,
                        "drivers": sorted(driver_tlas),
                        "racing_numbers": racing_numbers,
                        "location": location,
                        "reason": reason,
                    }
                    return True
            return False
        if _WILL_BE_INVESTIGATED_AFTER.search(message_text):
            if drivers:
                key = self._find_incident_by_drivers(driver_tlas, self._noted)
                if key:
                    incident = self._noted.pop(key)
                    new_key = self._make_incident_key(
                        driver_tlas, location, reason or incident.get("reason")
                    )
                    self._under_investigation[new_key] = {
                        "utc": incident.get("utc"),
                        "lap": incident.get("lap"),
                        "drivers": sorted(driver_tlas),
                        "racing_numbers": racing_numbers,
                        "location": location or incident.get("location"),
                        "reason": reason or incident.get("reason"),
                        "after_race": True,
                    }
                else:
                    new_key = self._make_incident_key(driver_tlas, location, reason)
                    self._under_investigation[new_key] = {
                        "utc": utc,
                        "lap": lap,
                        "drivers": sorted(driver_tlas),
                        "racing_numbers": racing_numbers,
                        "location": location,
                        "reason": reason,
                        "after_race": True,
                    }
            return True
        is_update = message_upper.startswith("UPDATE:")
        if _INCIDENT_NOTED.search(message_text):
            if drivers:
                if is_update:
                    key = self._find_incident_by_drivers(driver_tlas, self._noted)
                    if key:
                        incident = self._noted.pop(key)
                        new_key = self._make_incident_key(
                            driver_tlas, location or incident.get("location"), reason
                        )
                        self._noted[new_key] = {
                            "utc": incident.get("utc"),
                            "lap": incident.get("lap"),
                            "drivers": sorted(driver_tlas),
                            "racing_numbers": racing_numbers,
                            "location": location or incident.get("location"),
                            "reason": reason,
                        }
                        return True
                new_key = self._make_incident_key(driver_tlas, location, reason)
                existing = self._find_incident_by_drivers(driver_tlas, self._noted)
                if existing and reason is None:
                    return False
                if existing:
                    del self._noted[existing]
                self._noted[new_key] = {
                    "utc": utc,
                    "lap": lap,
                    "drivers": sorted(driver_tlas),
                    "racing_numbers": racing_numbers,
                    "location": location,
                    "reason": reason,
                }
            return True
        return False

    def _process_all_messages(self) -> None:
        """Process all messages from the coordinator."""
        messages = getattr(self.coordinator, "data_list", None)
        if not isinstance(messages, list):
            return
        for msg in messages:
            if isinstance(msg, dict):
                self._process_message(msg)
        self._expire_nfi_items()
        self._update_attributes()

    def _update_attributes(self) -> None:
        """Update sensor attributes and state."""
        self._expire_nfi_items()
        actionable_count = (
            len(self._noted) + len(self._under_investigation) + len(self._penalties)
        )
        self._attr_native_value = actionable_count
        self._attr_extra_state_attributes = {
            "noted": list(self._noted.values()),
            "under_investigation": list(self._under_investigation.values()),
            "no_further_action": list(self._nfi.values()),
            "penalties": list(self._penalties),
            "last_update": dt_util.utcnow().isoformat(timespec="seconds"),
            "session_key": self._session_key,
        }

    def refresh_data(self) -> None:
        messages = getattr(self.coordinator, "data_list", None)
        updated = isinstance(messages, list) and len(messages) > 0
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if not isinstance(messages, list):
            return
        changed = False
        for msg in messages:
            if isinstance(msg, dict) and self._process_message(msg):
                changed = True
        if self._expire_nfi_items():
            changed = True
        if changed:
            self._update_attributes()
            self._notify()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = 0
        self._noted = {}
        self._under_investigation = {}
        self._nfi = {}
        self._penalties = []
        self._processed_ids = set()
        self._session_time = None
        self._attr_extra_state_attributes = {
            "noted": [],
            "under_investigation": [],
            "no_further_action": [],
            "penalties": [],
            "last_update": None,
            "session_key": self._session_key,
        }

    context_bindings = {"_session_info_coordinator": "session_info_coordinator"}


class TeamRadioModel(AuthGatedProjection):
    """Shared calculation for TeamRadio."""

    _history_limit = 20
    _auth_gated_stream = "TeamRadio"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_utc: str | None = None
        self._history: list[dict] = []
        self._sequence = 0

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict):
            latest = data.get("latest")
            if isinstance(latest, dict):
                return latest
        return None

    @staticmethod
    def _cleanup_string(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_utc(self, utc_str: str | None) -> str | None:
        text = self._cleanup_string(utc_str)
        if not text:
            return None
        try:
            parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.UTC)
            return parsed.astimezone(datetime.UTC).isoformat(timespec="seconds")
        except Exception:
            return text

    def _build_clip_url(self, payload: dict, path: str | None) -> str | None:
        if not path:
            return None
        capture = dict(payload)
        capture.setdefault("Path", path)
        return team_radio_media_url(self.hass, self._entry_id, capture)

    @staticmethod
    def _transcription_attributes(payload: dict) -> dict[str, Any]:
        transcription = payload.get("Transcription")
        if not isinstance(transcription, dict):
            transcription = {}
        segments = transcription.get("segments")
        return {
            "transcription_status": transcription.get("status"),
            "transcription_text": transcription.get("text"),
            "transcription_segments": [
                dict(segment) for segment in segments if isinstance(segment, dict)
            ]
            if isinstance(segments, list)
            else [],
            "transcription_ai_task_entity_id": transcription.get("ai_task_entity_id"),
            "transcription_generated_at": transcription.get("generated_at"),
            "transcription_error": transcription.get("error"),
        }

    def _identity_attributes(self, payload: dict) -> dict[str, str | None]:
        team_color = self._cleanup_string(payload.get("team_color"))
        if team_color and (not team_color.startswith("#")):
            team_color = f"#{team_color}"
        return {
            "driver_tla": self._cleanup_string(payload.get("driver_tla")),
            "driver_name": self._cleanup_string(payload.get("driver_name")),
            "team_name": self._cleanup_string(payload.get("team_name")),
            "team_color": team_color,
        }

    def _build_history(self) -> list[dict]:
        """Expose only captures currently available to the media proxy."""
        data = self.coordinator.data
        if not isinstance(data, dict):
            return []
        candidates = [data.get("latest"), *reversed(data.get("history") or [])]
        history: list[dict] = []
        seen: set[str] = set()
        for capture in candidates:
            if not isinstance(capture, dict):
                continue
            clip_id = team_radio_clip_id(capture)
            if clip_id in seen:
                continue
            seen.add(clip_id)
            path = self._cleanup_string(capture.get("Path"))
            history.append(
                {
                    "utc": self._normalize_utc(
                        capture.get("Utc")
                        or capture.get("utc")
                        or capture.get("processedAt")
                        or capture.get("timestamp")
                    ),
                    "racing_number": self._cleanup_string(capture.get("RacingNumber")),
                    **self._identity_attributes(capture),
                    "path": path,
                    "clip_url": self._build_clip_url(capture, path),
                    **self._transcription_attributes(capture),
                }
            )
            if len(history) >= self._history_limit:
                break
        return history

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        utc_raw = (
            payload.get("Utc")
            or payload.get("utc")
            or payload.get("processedAt")
            or payload.get("timestamp")
        )
        utc_norm = self._normalize_utc(utc_raw)
        racing_number = self._cleanup_string(payload.get("RacingNumber"))
        path = self._cleanup_string(payload.get("Path"))
        clip_url = self._build_clip_url(payload, path)
        identity_attrs = self._identity_attributes(payload)
        transcription_attrs = self._transcription_attributes(payload)
        self._history = self._build_history()
        if (
            utc_norm
            and self._last_utc == utc_norm
            and (
                team_radio_clip_id(payload)
                == team_radio_clip_id(
                    self._attr_extra_state_attributes.get("raw_message", {})
                )
            )
            and (not force)
        ):
            has_transcription = isinstance(payload.get("Transcription"), dict)
            attrs = dict(self._attr_extra_state_attributes)
            attrs.update(identity_attrs)
            if has_transcription:
                attrs.update(transcription_attrs)
            attrs["raw_message"] = payload
            attrs["history"] = [dict(item) for item in self._history]
            self._attr_extra_state_attributes = attrs
            return
        received_at = dt_util.utcnow().isoformat(timespec="seconds")
        self._sequence += 1
        attrs = {
            "utc": utc_norm,
            "received_at": received_at,
            "racing_number": racing_number,
            **identity_attrs,
            "path": path,
            "clip_url": clip_url,
            **transcription_attrs,
            "sequence": self._sequence,
            "raw_message": payload,
        }
        attrs["history"] = [dict(item) for item in self._history]
        self._attr_native_value = utc_norm
        self._attr_extra_state_attributes = attrs
        self._last_utc = utc_norm

    def refresh_data(self) -> None:
        payload = self._extract_current()
        if payload is None:
            self._clear_state()
            self._handle_stream_state(False)
            self._notify()
            return
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        self._apply_payload(payload)
        self._notify()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._history = []
        self._sequence = 0
        self._last_utc = None


class PitStopsModel(AuthGatedProjection):
    """Shared calculation for PitStops."""

    _auth_gated_stream = "PitStopSeries"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"cars": {}, "last_update": None}
        self._last_reset: datetime.datetime | None = None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        total = payload.get("total_stops")
        cars = payload.get("cars")
        last_update = payload.get("last_update")
        last_reset = self._parse_last_reset(payload.get("last_reset"))
        try:
            total_int = int(total) if total is not None else 0
        except Exception:
            try:
                total_int = int(float(str(total)))
            except Exception:
                total_int = 0
        if not force and self._attr_native_value == total_int:
            with suppress(Exception):
                prev_cars = (self._attr_extra_state_attributes or {}).get("cars")
                if prev_cars == cars and self._last_reset == last_reset:
                    return
        self._attr_native_value = total_int
        self._last_reset = last_reset
        self._attr_extra_state_attributes = {
            "cars": cars if isinstance(cars, dict) else {},
            "last_update": last_update,
        }

    @staticmethod
    def _parse_last_reset(value) -> datetime.datetime | None:
        if isinstance(value, datetime.datetime):
            return value if value.tzinfo is not None else None
        if not isinstance(value, str):
            return None
        parsed = dt_util.parse_datetime(value)
        return parsed if parsed is not None and parsed.tzinfo is not None else None

    @property
    def last_reset(self) -> datetime.datetime | None:
        return self._last_reset

    def refresh_data(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._notify()

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"cars": {}, "last_update": None}


class DriverPredictionModel(PredictionProjection):
    """Shared calculation for ChampionshipPredictionDrivers."""

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        pred = payload.get("predicted_driver_p1")
        drivers = payload.get("drivers")
        last_update = payload.get("last_update")
        tla = None
        if isinstance(pred, dict):
            tla = pred.get("tla")
        if tla is not None:
            tla = str(tla).strip() or None
        self._attr_native_value = tla
        self._attr_extra_state_attributes = {
            "predicted_driver_p1": pred if isinstance(pred, dict) else None,
            "drivers": drivers if isinstance(drivers, dict) else {},
            "last_update": last_update,
        }


class TeamPredictionModel(PredictionProjection):
    """Shared calculation for ChampionshipPredictionTeams."""

    _DEFAULT_ICON = "mdi:trophy-variant"

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        pred = payload.get("predicted_team_p1")
        teams = payload.get("teams")
        last_update = payload.get("last_update")
        team_name = None
        if isinstance(pred, dict):
            team_name = pred.get("team_name")
        if team_name is not None:
            team_name = str(team_name).strip() or None
        self._attr_native_value = team_name
        self._attr_extra_state_attributes = {
            "predicted_team_p1": pred if isinstance(pred, dict) else None,
            "teams": teams if isinstance(teams, dict) else {},
            "last_update": last_update,
        }


class LapCountModel(LiveProjectionModel):
    """Shared calculation for RaceLapCount."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        self._stale_timer = None

    def _to_int(self, value):
        try:
            if value is None:
                return None
            return int(float(value))
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and (
            "CurrentLap" in data or "TotalLaps" in data or "LapCount" in data
        ):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and (
            "CurrentLap" in inner or "TotalLaps" in inner or "LapCount" in inner
        ):
            return inner
        hist = getattr(self.coordinator, "data_list", None)
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, dict) and (
                "CurrentLap" in last or "TotalLaps" in last or "LapCount" in last
            ):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        curr = self._to_int(
            raw.get("CurrentLap") if "CurrentLap" in raw else raw.get("LapCount")
        )
        total = self._to_int(raw.get("TotalLaps"))
        now_utc = dt_util.utcnow()
        with suppress(Exception):
            utc_raw = (
                raw.get("Utc")
                or raw.get("utc")
                or raw.get("processedAt")
                or raw.get("timestamp")
            )
            if utc_raw:
                ts = datetime.datetime.fromisoformat(
                    str(utc_raw).replace("Z", "+00:00")
                )
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.UTC)
                self._last_timestamped_dt = ts
        self._attr_native_value = curr
        self._last_received_utc = now_utc
        prev_total = None
        try:
            prev_total = (self._attr_extra_state_attributes or {}).get("total_laps")
        except Exception:
            prev_total = None
        if total is None:
            total = prev_total
        self._attr_extra_state_attributes = {"total_laps": total}

    def _handle_stale_timeout(self) -> None:
        with suppress(Exception):
            now_utc = dt_util.utcnow()
            t_ref = None
            mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
            if isinstance(mt, str) and mt:
                try:
                    t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                    if t_ref.tzinfo is None:
                        t_ref = t_ref.replace(tzinfo=datetime.UTC)
                except Exception:
                    t_ref = None
            if t_ref is None and isinstance(
                self._last_timestamped_dt, datetime.datetime
            ):
                t_ref = self._last_timestamped_dt
            if t_ref is None and isinstance(self._last_received_utc, datetime.datetime):
                t_ref = self._last_received_utc
            if (
                isinstance(t_ref, datetime.datetime)
                and (now_utc - t_ref).total_seconds() >= 300
            ):
                self._attr_native_value = None
                attrs = dict(self._attr_extra_state_attributes or {})
                attrs["stale"] = True
                attrs["stale_threshold_seconds"] = 300
                self._attr_extra_state_attributes = attrs
                self._notify()

    def refresh_data(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if raw is None:
            with suppress(Exception):
                getLogger(__name__).debug(
                    "RaceLapCount: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            return
        self._apply_payload(raw)
        self._notify()

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        with suppress(Exception):
            if self._stale_timer:
                self._stale_timer()
                self._stale_timer = None


class DriverListModel(LiveProjectionModel):
    """Shared calculation for DriverList."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    def refresh_data(self) -> None:
        previous = (self._attr_native_value, self._attr_extra_state_attributes)
        updated = self._update_from_coordinator()
        if updated and previous != (
            self._attr_native_value,
            self._attr_extra_state_attributes,
        ):
            self._notify()

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data or {}
        drivers = data.get("drivers") or None if isinstance(data, dict) else None
        if not isinstance(drivers, dict) or not drivers:
            return False
        items = []
        for rn, info in drivers.items():
            ident = info.get("identity") or {} if isinstance(info, dict) else {}
            try:
                team_color = ident.get("team_color")
                if (
                    isinstance(team_color, str)
                    and team_color
                    and (not team_color.startswith("#"))
                ):
                    team_color = f"#{team_color}"
            except Exception:
                team_color = ident.get("team_color")
            items.append(
                {
                    "racing_number": ident.get("racing_number") or rn,
                    "tla": ident.get("tla"),
                    "name": ident.get("name"),
                    "first_name": ident.get("first_name"),
                    "last_name": ident.get("last_name"),
                    "team": ident.get("team"),
                    "team_color": team_color,
                    "team_color_rgb": _hex_to_rgb(team_color),
                    "headshot_small": ident.get("headshot_small")
                    or ident.get("headshot"),
                    "headshot_large": ident.get("headshot_large")
                    or ident.get("headshot"),
                    "reference": ident.get("reference"),
                }
            )

        def _rn_key(v):
            val = str(v.get("racing_number") or "")
            return (int(val) if val.isdigit() else 9999, val)

        items.sort(key=_rn_key)
        self._attr_extra_state_attributes = {"drivers": items}
        self._attr_native_value = len(items)
        return True

    def _bootstrap_from_ergast(self) -> bool:
        """Best-effort bootstrap driver list from the standings coordinator.

        This is used at season rollover (or first install) when live timing has
        no feed yet and there is no restored state available.
        """
        try:
            hass = getattr(self, "hass", None)
            if hass is None:
                return False
            reg = entry_runtime_registry(hass, self._entry_id)
            driver_coord = reg.get("driver_coordinator")
            data = getattr(driver_coord, "data", None) or {}
            standings = (
                (data.get("MRData") or {})
                .get("StandingsTable", {})
                .get("StandingsLists", [])
            )
            if not isinstance(standings, list) or not standings:
                return False
            ds = (standings[0] or {}).get("DriverStandings", [])
            if not isinstance(ds, list) or not ds:
                return False
            items: list[dict] = []
            for item in ds:
                if not isinstance(item, dict):
                    continue
                driver = item.get("Driver") or {}
                if not isinstance(driver, dict):
                    continue
                rn = str(driver.get("permanentNumber") or "").strip()
                if not rn:
                    continue
                tla = driver.get("code") or driver.get("driverId")
                first = driver.get("givenName")
                last = driver.get("familyName")
                full = None
                try:
                    parts = [p for p in (first, last) if p]
                    full = " ".join(parts) if parts else None
                except Exception:
                    full = None
                constructors = item.get("Constructors") or []
                team = None
                if isinstance(constructors, list) and constructors:
                    c0 = constructors[0]
                    if isinstance(c0, dict):
                        team = c0.get("name")
                items.append(
                    {
                        "racing_number": rn,
                        "tla": tla,
                        "name": full,
                        "first_name": first,
                        "last_name": last,
                        "team": team,
                        "team_color": None,
                        "headshot_small": None,
                        "headshot_large": None,
                        "reference": driver.get("url") or driver.get("driverId"),
                    }
                )
            if not items:
                return False

            def _rn_key(v):
                val = str(v.get("racing_number") or "")
                return (int(val) if val.isdigit() else 9999, val)

            items.sort(key=_rn_key)
            self._attr_extra_state_attributes = {"drivers": items, "source": "ergast"}
            self._attr_native_value = len(items)
            return True
        except Exception:
            return False

    @property
    def available(self) -> bool:
        """Keep this sensor available even without a live timing feed.

        Many dashboards are built around the driver list; showing it as
        `unavailable` breaks those UIs. We therefore keep the last known list and
        do not mirror live-feed availability here.
        """
        return True

    @property
    def state(self):
        return self._attr_native_value


class CurrentTyresModel(CoordinatorStreamProjection):
    """Shared calculation for CurrentTyres."""

    _COMPOUND_SHORT = {
        "SOFT": "S",
        "MEDIUM": "M",
        "HARD": "H",
        "INTERMEDIATE": "I",
        "WET": "W",
    }
    _COMPOUND_COLOR = {
        "SOFT": "#FF0000",
        "MEDIUM": "#FFFF00",
        "HARD": "#FFFFFF",
        "INTERMEDIATE": "#00FF00",
        "WET": "#0000FF",
    }

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data or {}
        if not isinstance(data, dict):
            return False
        drivers = data.get("drivers") or {}
        if not isinstance(drivers, dict) or not drivers:
            return False
        items: list[dict] = []
        for rn, info in drivers.items():
            if not isinstance(info, dict):
                continue
            ident = info.get("identity") or {} if isinstance(info, dict) else {}
            tyres = info.get("tyres") or {} if isinstance(info, dict) else {}
            compound = tyres.get("compound")
            stint_laps = tyres.get("stint_laps")
            is_new = tyres.get("new")
            position = _extract_driver_position(info)
            tla = ident.get("tla")
            team_color = ident.get("team_color")
            try:
                if (
                    isinstance(team_color, str)
                    and team_color
                    and (not team_color.startswith("#"))
                ):
                    team_color = f"#{team_color}"
            except Exception:
                team_color = ident.get("team_color")
            comp_upper = str(compound).upper() if isinstance(compound, str) else None
            if comp_upper in self._COMPOUND_SHORT:
                compound_short = self._COMPOUND_SHORT[comp_upper]
                compound_color = self._COMPOUND_COLOR.get(comp_upper)
            else:
                compound_short = "?" if compound not in (None, "") else None
                compound_color = None
            items.append(
                {
                    "racing_number": ident.get("racing_number") or rn,
                    "tla": tla,
                    "team_color": team_color,
                    "team_color_rgb": _hex_to_rgb(team_color),
                    "position": position,
                    "compound": compound,
                    "compound_short": compound_short,
                    "compound_color": compound_color,
                    "compound_color_rgb": _hex_to_rgb(compound_color),
                    "new": is_new,
                    "stint_laps": stint_laps,
                }
            )

        def _rn_key(v):
            val = str(v.get("racing_number") or "")
            return (int(val) if val.isdigit() else 9999, val)

        items.sort(key=_rn_key)
        self._attr_native_value = len(items)
        self._attr_extra_state_attributes = {"drivers": items}
        return True

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    @property
    def state(self):
        return self._attr_native_value


class TyreStatisticsModel(CoordinatorStreamProjection):
    """Shared calculation for TyreStatistics."""

    _COMPOUND_COLOR = {
        "SOFT": "#FF0000",
        "MEDIUM": "#FFFF00",
        "HARD": "#FFFFFF",
        "INTERMEDIATE": "#00FF00",
        "WET": "#0000FF",
    }

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @staticmethod
    def _compound_from_tyre_history(info: dict) -> str | None:
        tyre_history = info.get("tyre_history")
        if not isinstance(tyre_history, dict):
            return None
        stints = tyre_history.get("stints")
        if not isinstance(stints, list):
            return None
        for stint in stints:
            if not isinstance(stint, dict):
                continue
            compound = stint.get("compound")
            if isinstance(compound, str):
                compound = compound.strip().upper()
                if compound and compound != "UNKNOWN":
                    return compound
        return None

    def _update_waiting_for_compound_data(self, data: dict) -> bool:
        drivers = data.get("drivers")
        if not isinstance(drivers, dict) or not drivers:
            return False
        drivers_with_stints = 0
        drivers_with_stint_laps = 0
        drivers_with_compound = 0
        for info in drivers.values():
            if not isinstance(info, dict):
                continue
            tyre_history = info.get("tyre_history")
            if (
                isinstance(tyre_history, dict)
                and isinstance(tyre_history.get("stints"), list)
                and tyre_history["stints"]
            ):
                drivers_with_stints += 1
            tyres = info.get("tyres")
            if isinstance(tyres, dict) and tyres.get("stint_laps") is not None:
                drivers_with_stint_laps += 1
            if self._compound_from_tyre_history(info) is not None:
                drivers_with_compound += 1
        if drivers_with_compound > 0:
            return False
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "status": "waiting_for_compound_data",
            "source_stream": "TimingAppData",
            "waiting_for": "Compound",
            "drivers_seen": len(drivers),
            "drivers_with_stints": drivers_with_stints,
            "drivers_with_stint_laps": drivers_with_stint_laps,
            "drivers_with_compound": drivers_with_compound,
            "fastest_time": None,
            "fastest_time_secs": None,
            "deltas": {},
            "compounds": {},
            "start_compounds": [],
        }
        return True

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data or {}
        if not isinstance(data, dict):
            return False
        tyre_stats = data.get("tyre_statistics", {}) if isinstance(data, dict) else {}
        if not isinstance(tyre_stats, dict) or not tyre_stats:
            return self._update_waiting_for_compound_data(data)
        fastest_compound = tyre_stats.get("fastest_compound")
        fastest_time = tyre_stats.get("fastest_time")
        fastest_time_secs = tyre_stats.get("fastest_time_secs")
        deltas = tyre_stats.get("deltas", {})
        start_compounds = tyre_stats.get("start_compounds", [])
        compounds_raw = tyre_stats.get("compounds", {})
        if not isinstance(compounds_raw, dict) or not compounds_raw:
            return self._update_waiting_for_compound_data(data)
        compounds = {}
        for comp_name, comp_data in compounds_raw.items():
            comp_copy = dict(comp_data)
            comp_copy["compound_color"] = self._COMPOUND_COLOR.get(comp_name)
            comp_copy["compound_color_rgb"] = _hex_to_rgb(
                self._COMPOUND_COLOR.get(comp_name)
            )
            compounds[comp_name] = comp_copy
        self._attr_native_value = fastest_compound
        self._attr_extra_state_attributes = {
            "status": "ready",
            "source_stream": "TimingAppData",
            "fastest_time": fastest_time,
            "fastest_time_secs": fastest_time_secs,
            "deltas": deltas,
            "compounds": compounds,
            "start_compounds": start_compounds
            if isinstance(start_compounds, list)
            else [],
        }
        return True

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @property
    def state(self):
        return self._attr_native_value


class StartingGridModel(LiveProjectionModel):
    """Shared calculation for StartingGrid."""

    _ATTR_KEYS = (
        "status",
        "grid_context",
        "weekend_key",
        "weekend_format",
        "meeting_name",
        "session_key",
        "source_session_name",
        "target_session_name",
        "source",
        "source_updated_at",
        "cleared_at",
        "cleared_reason",
        "grid_count",
        "grid",
    )

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = self._empty_attributes()

    def refresh_data(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        self._update_from_coordinator()
        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return
        self._notify()

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data
        if not isinstance(data, dict) or data.get("status") is None:
            return False
        self._apply_payload(data)
        return True

    def _apply_payload(self, data: dict) -> None:
        status = data.get("status")
        self._attr_native_value = str(status) if status is not None else None
        attrs = self._empty_attributes()
        for key in self._ATTR_KEYS:
            if key == "grid":
                grid = data.get("grid")
                attrs["grid"] = grid if isinstance(grid, list) else []
            else:
                attrs[key] = data.get(key)
        attrs["status"] = self._attr_native_value
        attrs["grid_count"] = len(attrs["grid"])
        self._attr_extra_state_attributes = attrs

    @classmethod
    def _empty_attributes(cls) -> dict:
        attrs = dict.fromkeys(cls._ATTR_KEYS)
        attrs["grid"] = []
        attrs["grid_count"] = 0
        return attrs

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes


class DriverPositionsModel(LiveProjectionModel):
    """Shared calculation for DriverPositions."""

    _PIT_OUT_HOLD_SECONDS = 6.0

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "drivers": [],
            "total_laps": None,
            "fastest_lap": None,
            "push_laps_status": "waiting",
            "push_laps_stream_time": None,
        }
        self._last_write_ts: float | None = None
        self._pending_write: bool = False
        self._pending_write_cancel = None
        self._pit_out_until: dict[str, float] = {}
        self._pit_out_last: dict[str, bool] = {}
        self._session_info_coordinator = None
        self._session_status_coordinator = None

    def refresh_data(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        updated = self._update_from_coordinator(initial=False)
        if not self._handle_stream_state(updated):
            return
        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return
        self._notify()

    def _handle_session_info_update(self) -> None:
        self._handle_context_update()

    def _handle_session_status_update(self) -> None:
        self._handle_context_update()

    def _handle_context_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        updated = self._update_from_coordinator(initial=False)
        if not self._handle_stream_state(updated):
            return
        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return
        self._notify()

    @staticmethod
    def _normalize_qualifying_part(value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            return None
        if normalized == 0:
            return 1
        return normalized if normalized in (1, 2, 3) else None

    def _resolve_current_qualifying_part(
        self, data: dict[str, object], *, is_qualifying: bool
    ) -> int | None:
        session = data.get("session")
        if isinstance(session, dict):
            current_q_part = self._normalize_qualifying_part(session.get("part"))
            if current_q_part is not None:
                return current_q_part
        status_is_qualifying_like, status_q_part = _session_status_mapping_context(
            self._session_status_coordinator
        )
        if is_qualifying or status_is_qualifying_like:
            return self._normalize_qualifying_part(status_q_part)
        return None

    def _get_session_type_and_name(self) -> tuple[str | None, str | None]:
        try:
            coord = self._session_info_coordinator
            if coord is None:
                replay = self._get_session_from_replay()
                if replay != (None, None):
                    return replay
                return self._get_session_name_from_window()
            data = coord.data
            if not isinstance(data, dict):
                replay = self._get_session_from_replay()
                if replay != (None, None):
                    return replay
                return self._get_session_name_from_window()
            session_type = data.get("Type")
            session_name = data.get("Name")
            if session_type or session_name:
                return (session_type, session_name)
            replay = self._get_session_from_replay()
            if replay != (None, None):
                return replay
            return self._get_session_name_from_window()
        except Exception:
            replay = self._get_session_from_replay()
            if replay != (None, None):
                return replay
            return self._get_session_name_from_window()

    def _get_session_from_replay(self) -> tuple[str | None, str | None]:
        """Fallback to replay session metadata when replay is active."""
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            replay_controller = (
                reg.get("replay_controller") if isinstance(reg, dict) else None
            )
            if replay_controller is None:
                return (None, None)
            session_manager = getattr(replay_controller, "session_manager", None)
            if session_manager is None:
                return (None, None)
            selected = getattr(session_manager, "selected_session", None)
            if selected is None:
                return (None, None)
            session_type = getattr(selected, "session_type", None)
            session_name = getattr(selected, "session_name", None)
            if session_type or session_name:
                return (session_type, session_name)
        except Exception:
            return (None, None)
        return (None, None)

    def _get_session_name_from_window(self) -> tuple[str | None, str | None]:
        """Fallback to live window metadata when SessionInfo is unavailable."""
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            live_supervisor = (
                reg.get("live_supervisor") if isinstance(reg, dict) else None
            )
            window = getattr(live_supervisor, "current_window", None)
            session_name = getattr(window, "session_name", None)
            if isinstance(session_name, str) and session_name:
                return (None, session_name)
        except Exception:
            return (None, None)
        return (None, None)

    @staticmethod
    def _is_race_or_sprint(session_type: str | None, session_name: str | None) -> bool:
        joined = f"{session_type or ''} {session_name or ''}".lower()
        if "sprint" in joined and "qualifying" not in joined:
            return True
        return "race" in joined

    def _is_qualifying_like(self) -> bool:
        session_type, session_name = self._get_session_type_and_name()
        joined = f"{session_type or ''} {session_name or ''}".lower()
        return "qualifying" in joined or "shootout" in joined

    def _normalize_restored_attributes(self, attrs: dict) -> dict:
        attrs.setdefault("drivers", [])
        attrs.setdefault("total_laps", None)
        attrs.setdefault("fastest_lap", None)
        attrs.setdefault("current_qualifying_part", None)
        attrs["push_laps_status"] = "waiting"
        attrs["push_laps_stream_time"] = None
        drivers = attrs.get("drivers")
        if isinstance(drivers, list):
            for drv in drivers:
                if not isinstance(drv, dict):
                    continue
                drv["push_lap"] = empty_push_lap()
                drv.setdefault("best_lap_time", None)
                drv.setdefault("best_lap_time_secs", None)
                drv.setdefault("best_lap_lap", None)
                drv.setdefault("best_lap_time_source", None)
                drv.setdefault("best_lap_gap", None)
                drv.setdefault(
                    "last_lap_status",
                    {
                        "time": None,
                        "lap": None,
                        "overall_fastest": False,
                        "personal_fastest": False,
                    },
                )
                drv.setdefault("fastest_lap", False)
                drv.setdefault("fastest_lap_time", None)
                drv.setdefault("fastest_lap_time_secs", None)
                drv.setdefault("fastest_lap_lap", None)
                drv.setdefault("gap_to_leader", None)
                drv.setdefault("interval_to_position_ahead", None)
                drv.setdefault("q1_time", None)
                drv.setdefault("q1_knocked_out", None)
                drv.setdefault("q1_position", None)
                drv.setdefault("q2_time", None)
                drv.setdefault("q2_knocked_out", None)
                drv.setdefault("q2_position", None)
                drv.setdefault("q3_time", None)
                drv.setdefault("q3_knocked_out", None)
                drv.setdefault("q3_position", None)
        return attrs

    def _update_from_coordinator(self, *, initial: bool = False) -> bool:
        """Update sensor state from coordinator data."""
        data = self.coordinator.data or {}
        if not isinstance(data, dict):
            return False
        drivers_raw = data.get("drivers", {})
        if not drivers_raw:
            return False
        lap_current = data.get("lap_current")
        lap_total = data.get("lap_total")
        default_on_track = self._is_replay_active()
        session_type, session_name = self._get_session_type_and_name()
        allow_fastest = self._is_race_or_sprint(session_type, session_name)
        is_qualifying = self._is_qualifying_like()
        is_practice = str(session_type or "").strip().lower() == "practice" or (
            not session_type and "practice" in str(session_name or "").lower()
        )
        fastest = data.get("fastest_lap") if allow_fastest else None
        fastest_rn = None
        if isinstance(fastest, dict):
            fastest_rn = str(fastest.get("racing_number") or "").strip() or None
        if fastest_rn is None:
            fastest = None
        drivers_out = {}
        for rn, info in drivers_raw.items():
            identity = info.get("identity", {})
            lap_history = info.get("lap_history", {})
            timing = info.get("timing", {})
            last_lap_status = timing.get("last_lap_status")
            if not isinstance(last_lap_status, dict):
                last_lap_status = {}
            last_lap_status = {
                "time": last_lap_status.get("time"),
                "lap": last_lap_status.get("lap"),
                "overall_fastest": last_lap_status.get("overall_fastest") is True,
                "personal_fastest": last_lap_status.get("personal_fastest") is True,
            }
            official_best = timing.get("official_best_lap")
            best_lap_source = None
            if isinstance(official_best, dict):
                best_lap_time = official_best.get("time")
                best_lap_seconds = official_best.get("time_secs")
                best_lap_number = official_best.get("lap")
                if best_lap_seconds is not None:
                    best_lap_source = "official"
            else:
                best_lap_time = timing.get("best_lap")
                best_lap_seconds = None
                best_lap_number = None
                if isinstance(best_lap_time, str):
                    with suppress(ValueError, TypeError):
                        best_lap_seconds = _parse_lap_time_to_secs(best_lap_time)
                if (
                    best_lap_seconds is None
                    or not math.isfinite(best_lap_seconds)
                    or best_lap_seconds <= 0
                ):
                    best_lap_time = best_lap_seconds = None
                else:
                    best_lap_source = "observed"
            best_lap_gap = None
            if is_practice and best_lap_source == "official":
                raw_gap = timing.get("practice_gap_to_fastest")
                if raw_gap == "" and str(timing.get("position")) == "1":
                    best_lap_gap = 0.0
                elif isinstance(raw_gap, (str, int, float)) and not isinstance(
                    raw_gap, bool
                ):
                    with suppress(ValueError, TypeError):
                        parsed_gap = float(raw_gap)
                        if math.isfinite(parsed_gap) and parsed_gap >= 0:
                            best_lap_gap = parsed_gap
            _sectors = info.get("sectors", {})
            _cur = _sectors.get("current", {})
            _bst = _sectors.get("best", {})
            _pb = _sectors.get("personal_best", {})

            def _sec(idx: int, field: str, _c: dict = _cur) -> object:
                s = _c.get(idx)
                return s.get(field) if isinstance(s, dict) else None

            def _best_sec(
                idx: int, field: str = "time", _pb: dict = _pb, _bst: dict = _bst
            ) -> object:
                s = _pb.get(idx)
                if isinstance(s, dict):
                    return s.get(field)
                if field == "time":
                    return _bst.get(idx)
                return None

            def _sector_detail(idx: int) -> dict[str, object]:
                return {
                    "number": idx + 1,
                    "time": _sec(idx, "time"),
                    "value": _sec(idx, "value"),
                    "lap": _sec(idx, "lap"),
                    "overall_fastest": _sec(idx, "overall_fastest"),
                    "personal_fastest": _sec(idx, "personal_fastest"),
                    "source": _sec(idx, "source"),
                }

            def _best_sector_detail(idx: int) -> dict[str, object]:
                return {
                    "number": idx + 1,
                    "time": _best_sec(idx),
                    "value": _best_sec(idx, "value"),
                    "lap": _best_sec(idx, "lap"),
                    "session_part": _best_sec(idx, "session_part"),
                    "overall_fastest": _best_sec(idx, "overall_fastest"),
                    "personal_fastest": _best_sec(idx, "personal_fastest"),
                    "source": _best_sec(idx, "source"),
                }

            sectors_out = {
                "state": _sectors.get("state"),
                "current_lap": _sectors.get("current_lap"),
                "last_completed_sector": _sectors.get("last_completed_sector"),
                "current": {
                    f"sector_{idx + 1}": _sector_detail(idx) for idx in (0, 1, 2)
                },
                "personal_best": {
                    f"sector_{idx + 1}": _best_sector_detail(idx) for idx in (0, 1, 2)
                },
            }
            team_color = identity.get("team_color")
            if (
                isinstance(team_color, str)
                and team_color
                and (not team_color.startswith("#"))
            ):
                team_color = f"#{team_color}"
            status, status_attrs = self._derive_driver_status(
                rn, timing, default_on_track=default_on_track
            )
            is_fastest = bool(allow_fastest and fastest_rn == rn)
            _q_state = info.get("qualifying", {})
            _q_segs = _q_state.get("segments", {})
            _q_knocked_out_api = _q_state.get("knocked_out", False)
            if is_qualifying:
                _q2_participated = _q_segs.get(2, {}).get("participated", False)
                _q3_participated = _q_segs.get(3, {}).get("participated", False)
                _q1_time = _q_segs.get(1, {}).get("best_time")
                _q2_time = _q_segs.get(2, {}).get("best_time")
                _q3_time = _q_segs.get(3, {}).get("best_time")
                _q1_ko = _q_knocked_out_api and (not _q2_participated)
                _q2_ko = (
                    _q_knocked_out_api and _q2_participated and (not _q3_participated)
                )
                _q3_ko = False
            else:
                _q1_time = None
                _q2_time = None
                _q3_time = None
                _q1_ko = None
                _q2_ko = None
                _q3_ko = None
            drivers_out[rn] = {
                "racing_number": rn,
                "tla": identity.get("tla"),
                "name": identity.get("name"),
                "team": identity.get("team"),
                "team_color": team_color,
                "team_color_rgb": _hex_to_rgb(team_color),
                "grid_position": lap_history.get("grid_position"),
                "current_position": _extract_driver_position(info),
                "laps": lap_history.get("laps", {}),
                "completed_laps": lap_history.get(
                    "completed_laps", lap_history.get("last_recorded_lap", 0)
                ),
                "status": status,
                "push_lap": deepcopy(info.get("push_lap") or empty_push_lap()),
                "gap_to_leader": timing.get("gap_to_leader"),
                "interval_to_position_ahead": timing.get("interval"),
                "best_lap_time": best_lap_time,
                "best_lap_time_secs": best_lap_seconds,
                "best_lap_lap": best_lap_number,
                "best_lap_time_source": best_lap_source,
                "best_lap_gap": best_lap_gap,
                "last_lap_status": last_lap_status,
                "fastest_lap": is_fastest,
                "fastest_lap_time": fastest.get("time") if is_fastest else None,
                "fastest_lap_time_secs": fastest.get("time_secs")
                if is_fastest
                else None,
                "fastest_lap_lap": fastest.get("lap") if is_fastest else None,
                "sector_1": _sec(0, "time"),
                "sector_2": _sec(1, "time"),
                "sector_3": _sec(2, "time"),
                "sector_1_lap": _sec(0, "lap"),
                "sector_2_lap": _sec(1, "lap"),
                "sector_3_lap": _sec(2, "lap"),
                "sector_1_source": _sec(0, "source"),
                "sector_2_source": _sec(1, "source"),
                "sector_3_source": _sec(2, "source"),
                "sector_1_overall_fastest": _sec(0, "overall_fastest"),
                "sector_1_personal_fastest": _sec(0, "personal_fastest"),
                "sector_2_overall_fastest": _sec(1, "overall_fastest"),
                "sector_2_personal_fastest": _sec(1, "personal_fastest"),
                "sector_3_overall_fastest": _sec(2, "overall_fastest"),
                "sector_3_personal_fastest": _sec(2, "personal_fastest"),
                "best_sector_1": _best_sec(0),
                "best_sector_2": _best_sec(1),
                "best_sector_3": _best_sec(2),
                "best_sector_1_lap": _best_sec(0, "lap"),
                "best_sector_2_lap": _best_sec(1, "lap"),
                "best_sector_3_lap": _best_sec(2, "lap"),
                "best_sector_1_session_part": _best_sec(0, "session_part"),
                "best_sector_2_session_part": _best_sec(1, "session_part"),
                "best_sector_3_session_part": _best_sec(2, "session_part"),
                "sector_state": _sectors.get("state"),
                "sector_current_lap": _sectors.get("current_lap"),
                "last_completed_sector": _sectors.get("last_completed_sector"),
                "sectors": sectors_out,
                "q1_time": _q1_time,
                "q1_knocked_out": _q1_ko,
                "q1_position": None,
                "q2_time": _q2_time,
                "q2_knocked_out": _q2_ko,
                "q2_position": None,
                "q3_time": _q3_time,
                "q3_knocked_out": _q3_ko,
                "q3_position": None,
                **status_attrs,
            }

        def position_sort_key(drv: dict) -> tuple:
            current = drv.get("current_position")
            grid = drv.get("grid_position")
            pos = current if current is not None else grid
            try:
                return (0, int(pos))
            except (TypeError, ValueError):
                return (1, 0)

        drivers_list = sorted(drivers_out.values(), key=position_sort_key)
        if is_qualifying:
            for seg_num in (1, 2, 3):
                time_key = f"q{seg_num}_time"
                pos_key = f"q{seg_num}_position"
                timed = []
                for idx, drv in enumerate(drivers_list):
                    t = drv.get(time_key)
                    if t:
                        try:
                            timed.append((idx, _parse_lap_time_to_secs(t)))
                        except (ValueError, TypeError):
                            pass
                timed.sort(key=lambda x: x[1])
                for rank, (idx, _) in enumerate(timed, 1):
                    drivers_list[idx][pos_key] = rank
        current_q_part = self._resolve_current_qualifying_part(
            data, is_qualifying=is_qualifying
        )
        if isinstance(fastest, dict):
            fastest_out = dict(fastest)
            fastest_out["team_color_rgb"] = _hex_to_rgb(fastest_out.get("team_color"))
        else:
            fastest_out = None
        self._attr_native_value = lap_current
        self._attr_extra_state_attributes = {
            "drivers": drivers_list,
            "total_laps": lap_total,
            "fastest_lap": fastest_out,
            "current_qualifying_part": current_q_part,
            "push_laps_status": data.get("push_laps_status", "waiting"),
            "push_laps_stream_time": data.get("push_laps_stream_time"),
        }
        return True

    def _is_replay_active(self) -> bool:
        """Return True when replay mode is playing/paused."""
        reg = entry_runtime_registry(self.hass, self._entry_id)
        replay_controller = reg.get("replay_controller")
        if replay_controller is None:
            return False
        try:
            from .replay_mode import ReplayState

            return replay_controller.state in (ReplayState.PLAYING, ReplayState.PAUSED)
        except Exception:
            return False

    def _derive_driver_status(
        self,
        rn: str,
        timing: dict | None,
        now: float | None = None,
        default_on_track: bool = False,
    ) -> tuple[str | None, dict[str, object]]:
        """Derive a dashboard-friendly status and raw flags for a driver."""
        if not isinstance(timing, dict):
            timing = {}
        import time as _time

        if now is None:
            now = _time.monotonic()
        has_timing = bool(timing)
        in_pit = timing.get("in_pit") if "in_pit" in timing else None
        pit_out_raw = timing.get("pit_out") if "pit_out" in timing else None
        retired = timing.get("retired") if "retired" in timing else None
        stopped = timing.get("stopped") if "stopped" in timing else None
        if default_on_track and (not has_timing):
            self._pit_out_until.pop(rn, None)
            self._pit_out_last.pop(rn, None)
            in_pit = False
            retired = False
            stopped = False
        pit_out_recent = False
        last_raw = self._pit_out_last.get(rn)
        if pit_out_raw is True and last_raw is not True:
            self._pit_out_until[rn] = now + self._PIT_OUT_HOLD_SECONDS
        if pit_out_raw is not None:
            self._pit_out_last[rn] = pit_out_raw
        until = self._pit_out_until.get(rn)
        if until is not None:
            if until >= now:
                pit_out_recent = True
            else:
                self._pit_out_until.pop(rn, None)
        status: str | None = None
        if default_on_track:
            in_pit = bool(in_pit) if in_pit is not None else False
            retired = bool(retired) if retired is not None else False
            stopped = bool(stopped) if stopped is not None else False
        if has_timing or default_on_track:
            if retired is True or stopped is True:
                status = "out"
            elif in_pit is True:
                status = "pit_in"
            elif pit_out_recent is True:
                status = "pit_out"
            else:
                status = "on_track"
        return (
            status,
            {
                "in_pit": in_pit if has_timing or default_on_track else None,
                "pit_out": pit_out_recent if has_timing or default_on_track else None,
                "retired": retired if has_timing or default_on_track else None,
                "stopped": stopped if has_timing or default_on_track else None,
            },
        )

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "drivers": [],
            "total_laps": None,
            "fastest_lap": None,
            "push_laps_status": "unavailable",
            "push_laps_stream_time": None,
        }

    @property
    def state(self):
        return self._attr_native_value

    context_bindings = {
        "_session_info_coordinator": "session_info_coordinator",
        "_session_status_coordinator": "session_status_coordinator",
    }


class StraightModeModel(LiveProjectionModel):
    """Shared calculation for StraightMode."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value: str | None = None
        self._attr_extra_state_attributes: dict[str, object] = {}

    def _session_is_terminal(self) -> bool:
        return bool(getattr(self.coordinator, "session_is_terminal", False))

    def _extract_data(self) -> dict | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        return data

    def _has_straight_mode_state(self, data: dict | None) -> bool:
        if not isinstance(data, dict):
            return False
        value = data.get("straight_mode")
        return isinstance(value, str) and value in self._attr_options

    def _apply_data(self, data: dict) -> None:
        self._attr_native_value = data.get("straight_mode")
        self._attr_extra_state_attributes = {
            "overtake_enabled": data.get("overtake_enabled")
        }

    def refresh_data(self) -> None:
        data = self._extract_data()
        if self._session_is_terminal():
            self._clear_state()
            self._notify()
            return
        updated = self._has_straight_mode_state(data)
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._notify()
            return
        if not updated or data is None:
            return
        self._apply_data(data)
        self._notify()

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._attr_native_value is not None

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
