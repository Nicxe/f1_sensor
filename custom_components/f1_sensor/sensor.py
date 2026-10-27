from __future__ import annotations

import asyncio
from contextlib import suppress
import datetime
from logging import getLogger
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_interval,
    async_track_utc_time_change,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import (
    const,
    live_data_models as _live_models,
    static_data_models as _static_models,
)
from .auth import (
    AUTH_RUNTIME_STATUS,
    AUTH_STATUS_OPTIONS,
    F1TvAuthStatus,
    async_add_f1tv_auth_status_listener,
    is_auth_health_visible,
)
from .card_data_models import standings_snapshot
from .const import (
    CONF_OPERATION_MODE,
    DEFAULT_OPERATION_MODE,
    OPERATION_MODE_DEVELOPMENT,
    STRAIGHT_MODE_DISABLED,
    STRAIGHT_MODE_LOW,
    STRAIGHT_MODE_NORMAL,
)
from .data_helpers import (
    _combine_date_time as _combine_date_time,
    _extract_driver_position as _extract_driver_position,
    _hex_to_rgb as _hex_to_rgb,
    _map_session_status_payload as _map_session_status_payload,
    _parse_lap_time_to_secs as _parse_lap_time_to_secs,
    _session_identity_year as _session_identity_year,
    _session_status_mapping_context as _session_status_mapping_context,
    _timezone_from_circuit as _timezone_from_circuit,
    _timezone_from_location as _timezone_from_location,
    _to_float_value as _to_float_value,
    _to_home as _to_home,
    _to_local as _to_local,
)
from .entity import (
    F1AuxEntity,
    F1BaseEntity,
    default_object_id,
    entry_runtime_registry,
    set_default_entity_id,
)
from .favorite_driver import FavoriteDriverController
from .race_weather import weather_icon
from .replay_entities import F1ReplayStatusSensor
from .runtime import F1ConfigEntry, entry_value


class _ReplayOrAuthGatedStreamMixin:
    _auth_gated_stream: str | None = None

    def _is_stream_active(self) -> bool:
        return _live_models.AuthGatedProjection._is_stream_active(self)


async def _async_setup_points_progression(sensor) -> None:
    sensor._recompute()
    if sensor._attr_native_value is None:
        last = await sensor.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                sensor._attr_native_value = int(last.state)
            except Exception:
                sensor._attr_native_value = None
            sensor._attr_extra_state_attributes = dict(
                getattr(last, "attributes", {}) or {}
            )
    removal = sensor.coordinator.async_add_listener(sensor._handle_coordinator_update)
    sensor.async_on_remove(removal)
    sensor.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: F1ConfigEntry, async_add_entities
):
    """Create sensors when integration is added."""
    data = entry_runtime_registry(hass, entry.entry_id)
    base = entry.data.get("sensor_name", "F1")
    disabled: set[str] = set(entry_value(entry, "disabled_sensors", []) or [])
    mapping = {
        "next_race": (F1NextRaceSensor, data["race_coordinator"]),
        "track_time": (F1TrackTimeSensor, data["race_coordinator"]),
        "current_season": (F1CurrentSeasonSensor, data["race_coordinator"]),
        "driver_standings": (F1DriverStandingsSensor, data["driver_coordinator"]),
        "constructor_standings": (
            F1ConstructorStandingsSensor,
            data["constructor_coordinator"],
        ),
        "weather": (F1WeatherSensor, data.get("race_weather_coordinator")),
        "track_weather": (F1TrackWeatherSensor, data.get("weather_data_coordinator")),
        "race_lap_count": (F1RaceLapCountSensor, data.get("lap_count_coordinator")),
        "last_race_results": (F1LastRaceSensor, data["last_race_coordinator"]),
        "season_results": (F1SeasonResultsSensor, data["season_results_coordinator"]),
        "sprint_results": (F1SprintResultsSensor, data["sprint_results_coordinator"]),
        "lap_position_progression": (
            F1LapPositionProgressionSensor,
            data.get("lap_position_progression_coordinator"),
        ),
        "driver_points_progression": (
            F1DriverPointsProgressionSensor,
            data["season_results_coordinator"],
        ),
        "constructor_points_progression": (
            F1ConstructorPointsProgressionSensor,
            data["season_results_coordinator"],
        ),
        "track_status": (F1TrackStatusSensor, data.get("track_status_coordinator")),
        "session_status": (
            F1SessionStatusSensor,
            data.get("session_status_coordinator"),
        ),
        "session_time_remaining": (
            F1SessionTimeRemainingSensor,
            data.get("session_clock_coordinator"),
        ),
        "session_time_elapsed": (
            F1SessionTimeElapsedSensor,
            data.get("session_clock_coordinator"),
        ),
        "race_time_to_three_hour_limit": (
            F1RaceTimeToThreeHourLimitSensor,
            data.get("session_clock_coordinator"),
        ),
        "current_session": (
            F1CurrentSessionSensor,
            data.get("session_info_coordinator"),
        ),
        "driver_list": (F1DriverListSensor, data.get("drivers_coordinator")),
        "current_tyres": (F1CurrentTyresSensor, data.get("drivers_coordinator")),
        "tyre_statistics": (F1TyreStatisticsSensor, data.get("drivers_coordinator")),
        "driver_positions": (F1DriverPositionsSensor, data.get("drivers_coordinator")),
        "favorite_driver": (None, None),
        "starting_grid": (F1StartingGridSensor, data.get("starting_grid_coordinator")),
        "fia_documents": (F1FiaDocumentsSensor, data.get("fia_documents_coordinator")),
        "race_control": (F1RaceControlSensor, data.get("race_control_coordinator")),
        "straight_mode": (F1StraightModeSensor, data.get("live_mode_coordinator")),
        "track_limits": (F1TrackLimitsSensor, data.get("race_control_coordinator")),
        "investigations": (
            F1InvestigationsSensor,
            data.get("race_control_coordinator"),
        ),
        "top_three": (None, data.get("top_three_coordinator")),
        "team_radio": (F1TeamRadioSensor, data.get("team_radio_coordinator")),
        "pitstops": (F1PitStopsSensor, data.get("pitstop_coordinator")),
        "championship_prediction": (
            None,
            data.get("championship_prediction_coordinator"),
        ),
        "live_timing_diagnostics": (None, None),
    }

    sensors = []
    for key, (cls, coord) in mapping.items():
        if key in disabled:
            continue
        if key == "top_three":
            # Expandera till tre separata sensorer: P1, P2, P3
            if not coord:
                continue
            for pos in range(3):
                object_id = default_object_id(f"top_three_p{pos + 1}")
                sensor = F1TopThreePositionSensor(
                    coord,
                    f"{entry.entry_id}_top_three_p{pos + 1}",
                    entry.entry_id,
                    base,
                    pos,
                )
                set_default_entity_id(sensor, Platform.SENSOR, object_id)
                sensors.append(sensor)
        elif key == "championship_prediction":
            if not coord:
                continue
            drivers_sensor = F1ChampionshipPredictionDriversSensor(
                coord,
                f"{entry.entry_id}_championship_prediction_drivers",
                entry.entry_id,
                base,
            )
            set_default_entity_id(
                drivers_sensor,
                Platform.SENSOR,
                default_object_id("championship_prediction_drivers"),
            )
            sensors.append(drivers_sensor)
            teams_sensor = F1ChampionshipPredictionTeamsSensor(
                coord,
                f"{entry.entry_id}_championship_prediction_teams",
                entry.entry_id,
                base,
            )
            set_default_entity_id(
                teams_sensor,
                Platform.SENSOR,
                default_object_id("championship_prediction_teams"),
            )
            sensors.append(teams_sensor)
        elif key == "favorite_driver":
            controller = data.get("favorite_driver_controller")
            if not isinstance(controller, FavoriteDriverController):
                continue
            sensor = F1FavoriteDriverSensor(
                controller,
                f"{entry.entry_id}_favorite_driver",
                entry.entry_id,
                base,
            )
            set_default_entity_id(
                sensor,
                Platform.SENSOR,
                default_object_id("favorite_driver"),
            )
            sensors.append(sensor)
        elif key == "live_timing_diagnostics":
            # Dev-only diagnostic sensor; hide it fully unless dev UI is enabled.
            if const.ENABLE_DEVELOPMENT_MODE_UI:
                sensor = F1LiveTimingModeSensor(
                    hass,
                    entry.entry_id,
                    base,
                )
                set_default_entity_id(
                    sensor, Platform.SENSOR, default_object_id("live_timing_mode")
                )
                sensors.append(sensor)
        elif cls and coord:
            sensor = cls(
                coord,
                f"{entry.entry_id}_{key}",
                entry.entry_id,
                base,
            )
            set_default_entity_id(sensor, Platform.SENSOR, default_object_id(key))
            sensors.append(sensor)

    auth_status = data.get(AUTH_RUNTIME_STATUS)
    if isinstance(auth_status, F1TvAuthStatus) and is_auth_health_visible(auth_status):
        status_sensor = F1TvTokenStatusSensor(hass, entry.entry_id, base)
        set_default_entity_id(
            status_sensor, Platform.SENSOR, default_object_id("f1tv_token_status")
        )
        sensors.append(status_sensor)

        expires_sensor = F1TvTokenExpiresAtSensor(hass, entry.entry_id, base)
        set_default_entity_id(
            expires_sensor,
            Platform.SENSOR,
            default_object_id("f1tv_token_expires_at"),
        )
        sensors.append(expires_sensor)

    # Replay status sensor
    replay_controller = data.get("replay_controller")
    if replay_controller is not None:
        sensor = F1ReplayStatusSensor(
            replay_controller,
            f"{entry.entry_id}_replay_status",
            entry.entry_id,
            base,
        )
        set_default_entity_id(
            sensor, Platform.SENSOR, default_object_id("replay_status")
        )
        sensors.append(sensor)

    async_add_entities(sensors, False)


class F1FavoriteDriverSensor(F1AuxEntity, SensorEntity):
    """Live position and automation attributes for the selected driver."""

    _device_category = "drivers"
    _attr_icon = "mdi:account-star"
    _attr_translation_key = "favorite_driver"

    def __init__(
        self,
        controller: FavoriteDriverController,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        SensorEntity.__init__(self)
        self._controller = controller
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        if self._unsub is None:
            self._unsub = self._controller.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @property
    def available(self) -> bool:
        return self._controller.available

    @property
    def native_value(self) -> int | None:
        snapshot = self._controller.snapshot
        return snapshot.get("position") if snapshot else None

    @property
    def extra_state_attributes(self) -> dict:
        snapshot = self._controller.snapshot or {}
        return {"selected": self._controller.selected_tla, **snapshot}

    @callback
    def _handle_update(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()


class _F1TvTokenSensorBase(F1AuxEntity, SensorEntity):
    """Base for redacted F1TV token health sensors."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry_id: str, device_name: str) -> None:
        super().__init__(
            unique_id=f"{entry_id}_{self._attr_translation_key}",
            entry_id=entry_id,
            device_name=device_name,
        )
        self.hass = hass
        self._entry_id = entry_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_add_f1tv_auth_status_listener(
                self.hass,
                self._entry_id,
                lambda *_: self._safe_write_ha_state(),
            )
        )

    def _status(self) -> F1TvAuthStatus | None:
        data = entry_runtime_registry(self.hass, self._entry_id)
        status = data.get(AUTH_RUNTIME_STATUS)
        return status if isinstance(status, F1TvAuthStatus) else None

    @property
    def extra_state_attributes(self) -> dict[str, object | None]:
        status = self._status()
        if status is None:
            return {
                "auth_configured": False,
                "used_for_live_timing": False,
                "expires_at": None,
                "reason": None,
            }
        return {
            "auth_configured": status.configured,
            "used_for_live_timing": status.used_for_live_timing,
            "expires_at": status.expires_at_iso,
            "reason": status.reason,
        }


class F1TvTokenStatusSensor(_F1TvTokenSensorBase):
    """Diagnostic sensor exposing redacted F1TV token status."""

    _attr_translation_key = "f1tv_token_status"
    _attr_icon = "mdi:key-alert"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(AUTH_STATUS_OPTIONS)

    @property
    def native_value(self) -> str:
        status = self._status()
        return status.status if status is not None else "not_configured"


class F1TvTokenExpiresAtSensor(_F1TvTokenSensorBase):
    """Diagnostic timestamp for the saved F1TV token expiry."""

    _attr_translation_key = "f1tv_token_expires_at"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime.datetime | None:
        status = self._status()
        if status is None:
            return None
        return status.expires_at


class F1LiveTimingModeSensor(F1AuxEntity, SensorEntity):
    """Diagnostic mode sensor for the live timing transport (idle/live/replay)."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "live", "replay"]

    _attr_translation_key = "live_timing_mode"
    _fallback_tracked_streams = (
        "SessionStatus",
        "TrackStatus",
        "TopThree",
        "TimingAppData",
        "ChampionshipPrediction",
        "TeamRadio",
        "DriverRaceInfo",
        "CarData.z",
        "Position.z",
    )

    def __init__(self, hass: HomeAssistant, entry_id: str, device_name: str) -> None:
        super().__init__(
            unique_id=f"{entry_id}_live_timing_mode",
            entry_id=entry_id,
            device_name=device_name,
        )
        self._attr_suggested_object_id = default_object_id("live_timing_mode")
        self.hass = hass
        self._entry_id = entry_id
        self._unsub_live_state = None

    @staticmethod
    def _stream_names(value: object) -> tuple[str, ...]:
        if not isinstance(value, (set, frozenset, tuple, list)):
            return ()
        streams: list[str] = []
        for stream in value:
            if stream is None:
                continue
            name = str(stream).strip()
            if name:
                streams.append(name)
        return tuple(sorted(streams))

    def _diagnostic_streams(self, reg: dict) -> tuple[str, ...]:
        capabilities = reg.get("signalr_stream_capabilities")
        if isinstance(capabilities, dict):
            active_streams = self._stream_names(capabilities.get("active_live_streams"))
            if active_streams:
                return active_streams
        return self._fallback_tracked_streams

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        reg = entry_runtime_registry(self.hass, self._entry_id)
        live_state = reg.get("live_state")
        if live_state is not None and hasattr(live_state, "add_listener"):
            try:
                self._unsub_live_state = live_state.add_listener(
                    lambda *_: self._safe_write_ha_state()
                )
                self.async_on_remove(self._unsub_live_state)
            except Exception:
                self._unsub_live_state = None

        # Periodic update for age/window attributes
        with suppress(Exception):
            unsub = async_track_time_interval(
                self.hass,
                lambda *_: self._safe_write_ha_state(),
                datetime.timedelta(seconds=10),
            )
            self.async_on_remove(unsub)

    def _compute(self) -> tuple[str, dict]:
        reg = entry_runtime_registry(self.hass, self._entry_id)
        operation_mode = reg.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
        live_state = reg.get("live_state")
        live_bus = reg.get("live_bus")
        live_supervisor = reg.get("live_supervisor")

        is_live_window = (
            bool(getattr(live_state, "is_live", False))
            if live_state is not None
            else False
        )
        reason = getattr(live_state, "reason", None) if live_state is not None else None

        if operation_mode == OPERATION_MODE_DEVELOPMENT:
            mode = "replay"
        else:
            mode = "live" if is_live_window else "idle"

        window = None
        try:
            cw = (
                getattr(live_supervisor, "current_window", None)
                if live_supervisor is not None
                else None
            )
            if cw is not None and hasattr(cw, "label"):
                window = cw.label
        except Exception:
            window = None

        hb_age = None
        activity_age = None
        try:
            if live_bus is not None:
                hb_age = live_bus.last_heartbeat_age()
                activity_age = live_bus.last_stream_activity_age()
        except Exception:
            hb_age = activity_age = None

        diagnostic_streams = self._diagnostic_streams(reg)
        stream_diagnostics = {
            stream: {
                "frame_count": 0,
                "last_seen_age_s": None,
                "last_payload_keys": None,
            }
            for stream in diagnostic_streams
        }
        try:
            if live_bus is not None and hasattr(live_bus, "stream_diagnostics"):
                stream_diagnostics.update(
                    live_bus.stream_diagnostics(diagnostic_streams)
                )
        except Exception:
            stream_diagnostics = {
                stream: {
                    "frame_count": 0,
                    "last_seen_age_s": None,
                    "last_payload_keys": None,
                }
                for stream in diagnostic_streams
            }

        attrs = {
            "reason": reason,
            "window": window,
            "schedule_source": (
                getattr(live_supervisor, "schedule_source", "none")
                if live_supervisor is not None
                else "none"
            ),
            "index_http_status": (
                getattr(live_supervisor, "index_http_status", None)
                if live_supervisor is not None
                else None
            ),
            "fallback_active": (
                bool(getattr(live_supervisor, "fallback_active", False))
                if live_supervisor is not None
                else False
            ),
            "last_schedule_error": (
                getattr(live_supervisor, "last_schedule_error", None)
                if live_supervisor is not None
                else None
            ),
            "heartbeat_age_s": (round(hb_age, 1) if hb_age is not None else None),
            "activity_age_s": (
                round(activity_age, 1) if activity_age is not None else None
            ),
            "streams": stream_diagnostics,
        }
        return mode, attrs

    @property
    def native_value(self):
        mode, _ = self._compute()
        return mode

    @property
    def extra_state_attributes(self):
        _, attrs = self._compute()
        return attrs


class _NextRaceMixin:
    """Shared helper for finding the next/current race from schedule data."""

    def _get_next_race(self, *, default_time: str = "00:00:00Z") -> dict | None:
        return _static_models.NextRaceProjection._get_next_race(
            self, default_time=default_time
        )


class _PointsProgressionBase(F1BaseEntity, RestoreEntity, SensorEntity):
    """Base for points progression sensors with shared setup/refresh logic."""

    _device_category = "championship"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-line"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await _async_setup_points_progression(self)

    def _handle_coordinator_update(self) -> None:
        self._recompute()
        self.async_write_ha_state()

    def _get_sprint_results(self) -> list:
        return _static_models.PointsProjection._get_sprint_results(self)


class _CoordinatorStreamSensorBase(F1BaseEntity, SensorEntity):
    """Base class for coordinator-driven live sensors with change detection."""

    _device_category = "drivers"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        updated = self._update_from_coordinator()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            self._session_info_coordinator = reg.get("session_info_coordinator")
            if self._session_info_coordinator is not None:
                rem_info = self._session_info_coordinator.async_add_listener(
                    self._handle_session_info_update
                )
                self.async_on_remove(rem_info)
        except Exception:
            self._session_info_coordinator = None
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        return _live_models.CoordinatorStreamProjection.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    def _update_from_coordinator(self) -> bool:
        return _live_models.CoordinatorStreamProjection._update_from_coordinator(self)


class _ChampionshipPredictionBase(F1BaseEntity, RestoreEntity, SensorEntity):
    """Base for championship prediction sensors with shared restore logic."""

    _device_category = "championship"
    _DEFAULT_ICON = "mdi:trophy"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = self._DEFAULT_ICON
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        init = self._extract_current()
        updated = init is not None
        if init is not None:
            self._apply_payload(init, force=True)
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    self._attr_native_value = last.state
                    self._attr_extra_state_attributes = dict(
                        getattr(last, "attributes", {}) or {}
                    )
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        return _live_models.PredictionProjection._extract_current(self)

    def _is_stream_active(self) -> bool:
        return _live_models.PredictionProjection._is_stream_active(self)

    def _handle_coordinator_update(self) -> None:
        return _live_models.PredictionProjection.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        return _live_models.PredictionProjection._apply_payload(
            self, payload, force=force
        )

    def _clear_state(self) -> None:
        return _live_models.PredictionProjection._clear_state(self)


class F1NextRaceSensor(_NextRaceMixin, F1BaseEntity, SensorEntity):
    """Sensor that returns date/time (ISO8601) for the next race in 'state'."""

    _device_category = "race"
    _unrecorded_attributes = frozenset(
        {
            "last_5_winners",
            "last_5_poles",
            "top_5_driver_wins_here",
            "top_5_constructor_wins_here",
            "dnf_rate_last_5_stats",
            "pole_to_win_conversion_last_5_stats",
        }
    )

    _attr_translation_key = "next_race"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._history_coordinator = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        reg = entry_runtime_registry(self.hass, self._entry_id)
        self._history_coordinator = reg.get("next_race_history_coordinator")
        if self._history_coordinator is not None:
            removal = self._history_coordinator.async_add_listener(
                self._handle_history_update
            )
            self.async_on_remove(removal)
        self._refresh_cached_state()

    @callback
    def _handle_history_update(self) -> None:
        self._refresh_cached_state()
        self._safe_write_ha_state()

    def _history_attributes(self) -> dict:
        return _static_models.NextRaceModel._history_attributes(self)

    def _refresh_cached_state(self) -> None:
        return _static_models.NextRaceModel._refresh_cached_state(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_cached_state()
        self._safe_write_ha_state()

    @property
    def state(self):
        return _static_models.NextRaceModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.NextRaceModel.__dict__["extra_state_attributes"].fget(
            self
        )


class F1TrackTimeSensor(_NextRaceMixin, F1BaseEntity, SensorEntity):
    """Sensor showing current local time at the circuit."""

    _device_category = "race"

    _attr_translation_key = "track_time"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:clock-outline"
        self._unsub_timer = None

    def _get_circuit_timezone(self, race):
        return _static_models.TrackTimeModel._get_circuit_timezone(self, race)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._unsub_timer = async_track_utc_time_change(
            self.hass, self._handle_time_update, second=0
        )

    async def async_will_remove_from_hass(self):
        if self._unsub_timer:
            self._unsub_timer()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_time_update(self, now):
        self.async_write_ha_state()

    @property
    def available(self):
        if not super().available:
            return False
        race = self._get_next_race()
        if not race:
            return False
        return self._get_circuit_timezone(race) is not None

    @property
    def state(self):
        return _static_models.TrackTimeModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.TrackTimeModel.__dict__["extra_state_attributes"].fget(
            self
        )


class F1CurrentSeasonSensor(F1BaseEntity, SensorEntity):
    """Sensor showing number of races this season."""

    _device_category = "race"
    _unrecorded_attributes = frozenset({"races"})

    _attr_translation_key = "current_season"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-month"

    @property
    def state(self):
        return _static_models.CurrentSeasonModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.CurrentSeasonModel.__dict__[
            "extra_state_attributes"
        ].fget(self)


class F1DriverStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for driver standings."""

    _device_category = "championship"

    _attr_translation_key = "driver_standings"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple-check"

    @property
    def state(self):
        return standings_snapshot(self.coordinator.data, "drivers").value

    @property
    def extra_state_attributes(self):
        return standings_snapshot(self.coordinator.data, "drivers").attributes


class F1ConstructorStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for constructor standings."""

    _device_category = "championship"

    _attr_translation_key = "constructor_standings"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:factory"

    @property
    def state(self):
        return standings_snapshot(self.coordinator.data, "constructors").value

    @property
    def extra_state_attributes(self):
        return standings_snapshot(self.coordinator.data, "constructors").attributes


class F1WeatherSensor(F1BaseEntity, SensorEntity):
    """Backward-compatible sensor for current and race-start weather."""

    _device_category = "race"
    _attr_translation_key = "weather"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def _weather_data(self) -> dict:
        return _static_models.WeatherModel.__dict__["_weather_data"].fget(self)

    @property
    def available(self) -> bool:
        """Return whether current next-race weather is available."""
        current = self._weather_data.get("current", {})
        return super().available and current.get("temperature") is not None

    @property
    def icon(self):
        """Return an icon matching the current normalized condition."""
        current = self._weather_data.get("current", {})
        return weather_icon(current.get("weather_code"), current.get("is_daytime"))

    @property
    def native_value(self):
        return _static_models.WeatherModel.__dict__["native_value"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.WeatherModel.__dict__["extra_state_attributes"].fget(self)


class F1LastRaceSensor(F1BaseEntity, SensorEntity):
    """Sensor for results of the latest race."""

    _device_category = "race"

    _attr_translation_key = "last_race_results"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:trophy"

    @property
    def state(self):
        return _static_models.LastRaceModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.LastRaceModel.__dict__["extra_state_attributes"].fget(
            self
        )


class F1SeasonResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor for full season results."""

    _device_category = "race"
    _unrecorded_attributes = frozenset({"races"})

    _attr_translation_key = "season_results"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:podium"

    @property
    def state(self):
        return _static_models.SeasonResultsModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.SeasonResultsModel.__dict__[
            "extra_state_attributes"
        ].fget(self)


class F1SprintResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor exposing sprint results across the current season."""

    _device_category = "race"
    _unrecorded_attributes = frozenset({"races"})

    _attr_translation_key = "sprint_results"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-variant"

    def _get_races(self):
        return _static_models.SprintResultsModel._get_races(self)

    @staticmethod
    def _clean_result(result: dict) -> dict:
        return _static_models.SprintResultsModel._clean_result(result)

    @property
    def state(self):
        return _static_models.SprintResultsModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.SprintResultsModel.__dict__[
            "extra_state_attributes"
        ].fget(self)


class F1LapPositionProgressionSensor(F1BaseEntity, SensorEntity):
    """Sensor exposing post-race lap-by-lap position progression sessions."""

    _device_category = "race"
    _unrecorded_attributes = frozenset({"sessions"})

    _attr_translation_key = "lap_position_progression"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-timeline-variant"

    def _get_sessions(self) -> list[dict]:
        return _static_models.LapPositionProgressionModel._get_sessions(self)

    @staticmethod
    def _clean_session(session: dict) -> dict:
        return _static_models.LapPositionProgressionModel._clean_session(session)

    @property
    def state(self):
        return _static_models.LapPositionProgressionModel.__dict__["state"].fget(self)

    @property
    def extra_state_attributes(self):
        return _static_models.LapPositionProgressionModel.__dict__[
            "extra_state_attributes"
        ].fget(self)


class F1FiaDocumentsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor that tracks FIA decision documents per race weekend."""

    _device_category = "officials"
    _unrecorded_attributes = frozenset({"documents"})
    _DOC1_RESET_PATTERN = re.compile(
        r"\bdoc(?:ument)?(?:\s+(?:no\.?|number))?\s*0*1\b",
        re.IGNORECASE,
    )
    _DOC_NUMBER_RE = re.compile(
        r"\bdoc(?:ument)?(?:\s+(?:no\.?|number))?\s*0*(\d+)\b",
        re.IGNORECASE,
    )

    _attr_translation_key = "fia_documents"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:file-document-alert"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = self._build_attributes(None, [], None)
        self._documents: list[dict] = []
        self._seen_urls: set[str] = set()
        self._event_key: str | None = None
        self._race: dict | None = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._restore_last_state()
        self._update_from_coordinator(force=True)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    async def _restore_last_state(self) -> None:
        last = await self.async_get_last_state()
        if not last or last.state in (None, "unknown", "unavailable"):
            return
        attrs = dict(getattr(last, "attributes", {}) or {})
        docs = attrs.get("documents")
        if isinstance(docs, list):
            cleaned = [doc for doc in docs if isinstance(doc, dict)]
            self._documents = cleaned
            self._seen_urls = {
                str(doc.get("url")).strip()
                for doc in cleaned
                if isinstance(doc.get("url"), str)
            }
        else:
            # Newer format: restore single latest document from flat attributes if present
            name = attrs.get("name")
            url = attrs.get("url")
            published = attrs.get("published")
            if any((name, url, published)):
                self._documents = [
                    {
                        "name": name,
                        "url": url,
                        "published": published,
                    }
                ]
        race = attrs.get("race")
        self._race = race if isinstance(race, dict) else None
        self._sort_documents()

        latest = (
            self._select_latest_document(self._documents) if self._documents else None
        )
        self._attr_native_value = (
            self._extract_doc_number(latest.get("name")) if latest else 0
        )
        self._attr_extra_state_attributes = self._build_attributes(
            latest, self._documents, self._race
        )

    def _handle_coordinator_update(self) -> None:
        changed = self._update_from_coordinator()
        if changed:
            from logging import getLogger

            with suppress(Exception):
                getLogger(__name__).debug(
                    "FIA documents updated -> event=%s count=%s",
                    self._event_key,
                    self._attr_native_value,
                )
            self._safe_write_ha_state()

    def _update_from_coordinator(self, force: bool = False) -> bool:
        return _static_models.FiaDocumentsModel._update_from_coordinator(self, force)

    @classmethod
    def _should_reset_for_doc(cls, doc: dict) -> bool:
        return _static_models.FiaDocumentsModel._should_reset_for_doc.__func__(cls, doc)

    @staticmethod
    def _published_timestamp(doc: dict) -> float | None:
        return _static_models.FiaDocumentsModel._published_timestamp(doc)

    def _sort_documents(self) -> None:
        return _static_models.FiaDocumentsModel._sort_documents(self)

    @classmethod
    def _extract_doc_number(cls, name: str | None) -> int:
        return _static_models.FiaDocumentsModel._extract_doc_number.__func__(cls, name)

    @classmethod
    def _select_latest_document(cls, docs: list[dict]) -> dict | None:
        return _static_models.FiaDocumentsModel._select_latest_document.__func__(
            cls, docs
        )

    @classmethod
    def _clean_document_attribute(cls, doc: dict | None) -> dict:
        return _static_models.FiaDocumentsModel._clean_document_attribute.__func__(
            cls, doc
        )

    @staticmethod
    def _clean_race_attribute(race: dict | None) -> dict | None:
        return _static_models.FiaDocumentsModel._clean_race_attribute(race)

    @classmethod
    def _build_attributes(
        cls, latest: dict | None, documents: list[dict] | None, race: dict | None
    ) -> dict:
        return _static_models.FiaDocumentsModel._build_attributes.__func__(
            cls, latest, documents, race
        )


class F1DriverPointsProgressionSensor(_PointsProgressionBase):
    """Sensor that exposes per-round and cumulative points per driver, including sprint points.

    - State: number of rounds included.
    - Attributes: season, rounds[], drivers{}, series{} for charting.
    """

    _attr_translation_key = "driver_points_progression"

    _unrecorded_attributes = frozenset({"drivers", "series"})

    def _get_full_schedule(self) -> list:
        return _static_models.DriverPointsProgressionModel._get_full_schedule(self)

    def _get_driver_standings(self) -> tuple[dict, int | None]:
        return _static_models.DriverPointsProgressionModel._get_driver_standings(self)

    def _recompute(self) -> None:
        return _static_models.DriverPointsProgressionModel._recompute(self)


class F1ConstructorPointsProgressionSensor(_PointsProgressionBase):
    """Constructor points per team by round, including sprint; cumulative series for charts."""

    _attr_translation_key = "constructor_points_progression"

    _unrecorded_attributes = frozenset({"constructors", "series"})

    def _recompute(self) -> None:
        return _static_models.ConstructorPointsProgressionModel._recompute(self)

    def _get_constructor_standings(self) -> tuple[dict, int | None]:
        return (
            _static_models.ConstructorPointsProgressionModel._get_constructor_standings(
                self
            )
        )


class F1TrackWeatherSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor for live track weather via WeatherData feed.

    State: air temperature (Celsius). Attributes include track temp, humidity, pressure, rainfall,
    wind speed and direction, with units. Waits for fresh stream data before becoming available.
    """

    _device_category = "session"

    _attr_translation_key = "track_weather"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:thermometer"
        try:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "°C"
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        # No stale timer: once a payload has arrived, keep it until a new payload arrives.

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator if available, otherwise wait for a live payload.
        init = self._extract_current()
        updated = init is not None
        if init is not None:
            self._apply_payload(init)
            with suppress(Exception):
                getLogger(__name__).debug(
                    "TrackWeather: Initialized from coordinator: %s", init
                )
        else:
            self._clear_state()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        return

    @property
    def available(self) -> bool:
        return super().available and self._attr_native_value is not None

    def _to_float(self, value):
        return _live_models.TrackWeatherModel._to_float(self, value)

    def _extract_current(self) -> dict | None:
        return _live_models.TrackWeatherModel._extract_current(self)

    def _apply_payload(self, raw: dict) -> None:
        return _live_models.TrackWeatherModel._apply_payload(self, raw)

        # No staleness handling: keep last known value until a new payload arrives

    # No stale scheduling required for Track Weather

    # No stale timeout handler

    # Use default attributes storage; do not force placeholders

    def _handle_coordinator_update(self) -> None:
        return _live_models.TrackWeatherModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    def _clear_state(self) -> None:
        return _live_models.TrackWeatherModel._clear_state(self)

    def _safe_write_ha_state(self) -> None:
        try:
            in_loop = False
            try:
                running = asyncio.get_running_loop()
                in_loop = running is self.hass.loop
            except RuntimeError:
                in_loop = False
            if in_loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()
        except Exception:
            # Last resort: avoid raising in thread-safety guard
            with suppress(Exception):
                self.schedule_update_ha_state()


class F1TrackStatusSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Track status sensor independent from flag logic."""

    _device_category = "session"

    _attr_translation_key = "track_status"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_native_value = None
        self._session_status_coordinator = None
        self._forced_unavailable = False
        # Advertise as enum sensor so HA UI can suggest valid states
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        # Canonical states as produced by normalize_track_status
        self._attr_options = [
            "CLEAR",
            "YELLOW",
            "VSC",
            "SC",
            "RED",
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        reg = entry_runtime_registry(self.hass, self._entry_id)
        self._session_status_coordinator = reg.get("session_status_coordinator")
        # Prefer coordinator's latest if present, otherwise restore last state
        raw = self._extract_current()
        initial = self._normalize(raw)
        updated = raw is not None
        if self._session_is_terminal():
            self._clear_state()
        elif initial is not None:
            self._attr_native_value = initial
            self._forced_unavailable = False
            with suppress(Exception):
                from logging import getLogger

                getLogger(__name__).debug(
                    "TrackStatus: Initialized from coordinator: %s", initial
                )
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    self._attr_native_value = last.state
                    with suppress(Exception):
                        from logging import getLogger

                        getLogger(__name__).debug(
                            "TrackStatus: Restored last state: %s", last.state
                        )
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        # Listen for coordinator pushes
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        if self._session_status_coordinator is not None:
            status_removal = self._session_status_coordinator.async_add_listener(
                self._handle_session_status_update
            )
            self.async_on_remove(status_removal)
        self.async_write_ha_state()

    def _normalize(self, raw: dict | None) -> str | None:
        return _live_models.TrackStatusModel._normalize(self, raw)

    def _extract_current(self) -> dict | None:
        return _live_models.TrackStatusModel._extract_current(self)

    @property
    def native_value(self):
        return _live_models.TrackStatusModel.__dict__["native_value"].fget(self)

    @property
    def state(self):
        return _live_models.TrackStatusModel.__dict__["state"].fget(self)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not self._forced_unavailable

    def _session_is_terminal(self) -> bool:
        return _live_models.TrackStatusModel._session_is_terminal(self)

    def _handle_session_status_update(self) -> None:
        return _live_models.TrackStatusModel._handle_session_status_update(self)

    def _handle_coordinator_update(self) -> None:
        return _live_models.TrackStatusModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self.async_write_ha_state(*args)

    @property
    def extra_state_attributes(self):
        return _live_models.TrackStatusModel.__dict__["extra_state_attributes"].fget(
            self
        )

    def _clear_state(self) -> None:
        return _live_models.TrackStatusModel._clear_state(self)


class F1TopThreePositionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live Top Three sensor for a single position (P1, P2 eller P3).

    - State: TLA (t.ex. VER) för vald position när Withheld är False.
    - Attribut: withhold-flagga och fält för just den positionen.
    """

    _device_category = "drivers"
    _WRITE_CAP_SECONDS = 1.0

    def __init__(
        self,
        coordinator,
        unique_id,
        entry_id,
        device_name,
        position_index: int,
    ):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        # 0-baserat index: 0=P1, 1=P2, 2=P3
        self._position_index = max(0, min(2, int(position_index or 0)))
        self._attr_translation_key = f"top_three_p{self._position_index + 1}"
        # Enkelt ikonval; P1 kan få "full" trophy
        if self._position_index == 0:
            self._attr_icon = "mdi:trophy"
        else:
            self._attr_icon = "mdi:trophy-outline"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_write_ts: float | None = None
        self._pending_write: bool = False

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Försök initialisera från koordinatorns state; annars restaurera från historik
        state = self._extract_state()
        updated = isinstance(state, dict)
        self._update_from_coordinator(initial=True)
        if self._attr_native_value is None:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    self._attr_native_value = last.state
                    with suppress(Exception):
                        attrs = dict(getattr(last, "attributes", {}) or {})
                        self._attr_extra_state_attributes = attrs
                        from logging import getLogger

                        getLogger(__name__).debug(
                            "TopThree P%s: Restored last state: %s",
                            self._position_index + 1,
                            last.state,
                        )
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _extract_state(self) -> dict | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        # Förvänta samma struktur som TopThreeCoordinator._state
        # { "withheld": bool|None, "lines": [dict|None, dict|None, dict|None], ... }
        lines = data.get("lines")
        if not isinstance(lines, list):
            return {
                "withheld": data.get("withheld"),
                "lines": [None, None, None],
                "last_update_ts": data.get("last_update_ts"),
            }
        # Normalisera till exakt tre element
        norm = []
        for idx in range(3):
            try:
                item = lines[idx]
            except Exception:
                item = None
            norm.append(item if isinstance(item, dict) else None)
        return {
            "withheld": data.get("withheld"),
            "lines": norm,
            "last_update_ts": data.get("last_update_ts"),
        }

    @staticmethod
    def _normalize_color(value):
        if not isinstance(value, str) or not value:
            return value
        try:
            s = value.strip()
            if not s:
                return s
            if s.startswith("#"):
                return s
            return f"#{s}"
        except Exception:
            return value

    def _build_attrs(self, state: dict | None, line: dict | None) -> dict:
        """Bygg ett komplett attributschema även när ingen data finns ännu.

        Detta gör det enklare för användaren att se vilka fält som finns tillgängliga.
        """
        if isinstance(state, dict):
            withheld = state.get("withheld")
            last_update_ts = state.get("last_update_ts")
        else:
            withheld = None
            last_update_ts = None

        withheld_flag = bool(withheld) if withheld is not None else None

        if isinstance(line, dict):
            team_color = self._normalize_color(
                line.get("TeamColour") or line.get("TeamColor")
            )
            position = line.get("Position")
            racing_number = line.get("RacingNumber")
            tla = line.get("Tla") or line.get("TLA")
            broadcast_name = line.get("BroadcastName")
            full_name = line.get("FullName")
            first_name = line.get("FirstName")
            last_name = line.get("LastName")
            team = line.get("Team")
            lap_time = line.get("LapTime")
            overall_fastest = line.get("OverallFastest")
            personal_fastest = line.get("PersonalFastest")
        else:
            team_color = None
            # Vi känner fortfarande till “index” (P1/P2/P3), men position i loppet
            # kan vara okänd när feeden inte skickat något ännu.
            position = None
            racing_number = None
            tla = None
            broadcast_name = None
            full_name = None
            first_name = None
            last_name = None
            team = None
            lap_time = None
            overall_fastest = None
            personal_fastest = None

        return {
            "withheld": withheld_flag,
            # “position” = position i listan (om känd från feeden)
            "position": position,
            "racing_number": racing_number,
            "tla": tla,
            "broadcast_name": broadcast_name,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "team": team,
            "team_color": team_color,
            "team_color_rgb": _hex_to_rgb(team_color),
            "lap_time": lap_time,
            "overall_fastest": overall_fastest,
            "personal_fastest": personal_fastest,
            "last_update_ts": last_update_ts,
        }

    def _update_from_coordinator(self, *, initial: bool = False) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes

        state = self._extract_state()
        if not isinstance(state, dict):
            self._attr_native_value = None
            # Ingen feed-data ännu – exponera ändå fulla attribut med None-värden
            self._attr_extra_state_attributes = self._build_attrs(None, None)
            return

        withheld = state.get("withheld")
        lines = state.get("lines") or [None, None, None]

        if withheld is True:
            # När F1 undanhåller topp-3-data, exponera inget state
            self._attr_native_value = None
            self._attr_extra_state_attributes = self._build_attrs(state, None)
            return

        # Hämta raden för den här sensorns position
        line = None
        try:
            line = lines[self._position_index]
        except Exception:
            line = None

        if not isinstance(line, dict):
            self._attr_native_value = None
            self._attr_extra_state_attributes = self._build_attrs(state, None)
        else:
            tla = line.get("Tla") or line.get("TLA") or line.get("BroadcastName")
            self._attr_native_value = tla
            self._attr_extra_state_attributes = self._build_attrs(state, line)

        # På initial start vill vi alltid skriva state; annars kan vi rate-limita
        if initial:
            return

        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return

        with suppress(Exception):
            from logging import getLogger

            getLogger(__name__).debug(
                "TopThree P%s changed at %s: %s -> %s",
                self._position_index + 1,
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev_state,
                self._attr_native_value,
            )
        # Rate-limit writes so dense TopThree deltas stay responsive without
        # writing every intermediate frame to Home Assistant state.
        try:
            import time as _time

            lw = getattr(self, "_last_write_ts", None)
            now = _time.time()
            if lw is None or (now - lw) >= self._WRITE_CAP_SECONDS:
                self._last_write_ts = now
                self._safe_write_ha_state()
            else:
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    self._pending_write = True
                    delay = (
                        max(0.0, self._WRITE_CAP_SECONDS - (now - lw))
                        if lw is not None
                        else self._WRITE_CAP_SECONDS
                    )

                    def _do_write(_):
                        try:
                            self._last_write_ts = _time.time()
                            self._safe_write_ha_state()
                        finally:
                            self._pending_write = False

                    async_call_later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        state = self._extract_state()
        updated = isinstance(state, dict)
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        self._update_from_coordinator(initial=False)

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def state(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}


class F1SessionStatusSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor mapping SessionStatus to semantic states for automations."""

    _device_category = "session"

    _attr_translation_key = "session_status"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-play"
        self._attr_native_value = None
        self._started_flag = None
        self._session_info_coordinator = None
        self._race_control_coordinator = None
        self._track_grip_state: str | None = None
        self._attr_extra_state_attributes = {}
        # Advertise as enum sensor so HA UI can suggest valid states
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        # Possible mapped states from _map_status
        self._attr_options = [
            "pre",
            "live",
            "suspended",
            "break",
            "finished",
            "finalised",
            "ended",
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator or restore
        init = self._extract_current()
        updated = init is not None
        if init is not None:
            self._attr_native_value = self._map_status(init)
            with suppress(Exception):
                getLogger(__name__).debug(
                    "SessionStatus: Initialized from coordinator: raw=%s -> %s",
                    init,
                    self._attr_native_value,
                )
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    self._attr_native_value = last.state
                    # Also restore session info attributes
                    attrs = dict(getattr(last, "attributes", {}) or {})
                    session_info_keys = {
                        "meeting_name",
                        "meeting_location",
                        "meeting_country",
                        "circuit_short_name",
                        "gmt_offset",
                        "start",
                        "end",
                    }
                    self._attr_extra_state_attributes = {
                        k: v for k, v in attrs.items() if k in session_info_keys
                    }
                    with suppress(Exception):
                        getLogger(__name__).debug(
                            "SessionStatus: Restored last state: %s", last.state
                        )
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        # Subscribe to SessionInfo for meeting/session metadata
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            self._session_info_coordinator = reg.get("session_info_coordinator")
            if self._session_info_coordinator is not None:
                rem_info = self._session_info_coordinator.async_add_listener(
                    self._handle_session_info_update
                )
                self.async_on_remove(rem_info)
                # Initialize attributes from coordinator if available
                info_attrs = self._extract_session_info()
                if info_attrs:
                    self._attr_extra_state_attributes.update(info_attrs)
        except Exception:
            self._session_info_coordinator = None
        # Subscribe to RaceControlCoordinator for track grip detection
        try:
            self._race_control_coordinator = reg.get("race_control_coordinator")
            if self._race_control_coordinator is not None:
                rem_race_ctrl = self._race_control_coordinator.async_add_listener(
                    self._handle_race_control_update
                )
                self.async_on_remove(rem_race_ctrl)
                # Initialize track_grip attribute
                self._attr_extra_state_attributes["track_grip"] = (
                    self._detect_track_grip()
                )
        except Exception:
            self._race_control_coordinator = None
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        return _live_models.SessionStatusModel._extract_current(self)

    def _extract_session_info(self) -> dict:
        return _live_models.SessionStatusModel._extract_session_info(self)

    def _handle_session_info_update(self) -> None:
        return _live_models.SessionStatusModel._handle_session_info_update(self)

    def _detect_track_grip(self) -> str | None:
        return _live_models.SessionStatusModel._detect_track_grip(self)

    def _handle_race_control_update(self) -> None:
        return _live_models.SessionStatusModel._handle_race_control_update(self)

    def _map_status(self, raw: dict | None) -> str | None:
        return _live_models.SessionStatusModel._map_status(self, raw)

    def _handle_coordinator_update(self) -> None:
        return _live_models.SessionStatusModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self.async_write_ha_state(*args)

    @property
    def native_value(self):
        return _live_models.SessionStatusModel.__dict__["native_value"].fget(self)

    @property
    def extra_state_attributes(self):
        return _live_models.SessionStatusModel.__dict__["extra_state_attributes"].fget(
            self
        )

    def _clear_state(self) -> None:
        return _live_models.SessionStatusModel._clear_state(self)


class F1SessionClockBaseSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Base sensor for derived session clock values."""

    _device_category = "session"
    _value_key: str = ""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last.state
            self._attr_extra_state_attributes = dict(
                getattr(last, "attributes", {}) or {}
            )
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._handle_coordinator_update()

    @staticmethod
    def _format_hms(value: int | None) -> str | None:
        return _live_models.SessionClockModel._format_hms(value)

    def _extract_state(self) -> dict | None:
        return _live_models.SessionClockModel._extract_state(self)

    def _extract_value(self, state: dict) -> int | None:
        return _live_models.SessionClockModel._extract_value(self, state)

    def _is_value_available(self, state: dict, value: int | None) -> bool:
        return _live_models.SessionClockModel._is_value_available(self, state, value)

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        return _live_models.SessionClockModel._build_attrs(self, state, value)

    def _handle_coordinator_update(self) -> None:
        return _live_models.SessionClockModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

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
        return _live_models.SessionClockModel.__dict__["native_value"].fget(self)

    @property
    def extra_state_attributes(self):
        return _live_models.SessionClockModel.__dict__["extra_state_attributes"].fget(
            self
        )

    def _clear_state(self) -> None:
        return _live_models.SessionClockModel._clear_state(self)


class F1SessionTimeRemainingSensor(F1SessionClockBaseSensor):
    """Official session time remaining based on ExtrapolatedClock."""

    _value_key = "clock_remaining_s"

    _attr_translation_key = "session_time_remaining"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-sand"

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["clock_total_s"] = state.get("clock_total_s")
        return attrs


class F1SessionTimeElapsedSensor(F1SessionClockBaseSensor):
    """Official session elapsed time based on ExtrapolatedClock."""

    _value_key = "clock_elapsed_s"

    _attr_translation_key = "session_time_elapsed"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-outline"

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["clock_total_s"] = state.get("clock_total_s")
        attrs["clock_remaining_s"] = state.get("clock_remaining_s")
        return attrs


class F1RaceTimeToThreeHourLimitSensor(F1SessionClockBaseSensor):
    """Time remaining until the FIA 3-hour race duration cap."""

    _value_key = "race_three_hour_remaining_s"

    _attr_translation_key = "race_time_to_three_hour_limit"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car-clock"

    @staticmethod
    def _is_main_race(state: dict) -> bool:
        return _live_models.RaceLimitModel._is_main_race(state)

    def _is_value_available(self, state: dict, value: int | None) -> bool:
        if not self._is_main_race(state):
            return False
        return super()._is_value_available(state, value)

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["race_start_utc"] = state.get("race_start_utc")
        attrs["race_three_hour_cap_utc"] = state.get("race_three_hour_cap_utc")
        return attrs


class F1CurrentSessionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live sensor reporting current session label (e.g., Practice 1, Qualifying/Q1, Sprint Qualifying/SQ1, Sprint, Race).

    - State: compact label string
    - Attributes: full session metadata from SessionInfo (Type, Name, Number, Meeting, Circuit, Start/End),
                  session_part (numeric), resolved_label, and raw payloads; includes live status from SessionStatus if available.
    - Behavior: restores last state on restart; respects global live delay via coordinator.
    """

    _device_category = "session"

    _attr_translation_key = "current_session"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-clock"
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        # Enumerate possible labels for UI dropdowns in automations
        self._attr_options = [
            "Practice 1",
            "Practice 2",
            "Practice 3",
            "Qualifying",
            "Sprint Qualifying",
            "Sprint",
            "Race",
        ]
        self._status_coordinator = None

    def _is_replay_active(self) -> bool:
        return _live_models.CurrentSessionModel._is_replay_active(self)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Wire listeners first so _live_status() reflects current coordinator state
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        # Also listen to SessionStatus so we can clear state when session ends
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            self._status_coordinator = reg.get("session_status_coordinator")
            if self._status_coordinator is not None:
                rem2 = self._status_coordinator.async_add_listener(
                    self._handle_status_update
                )
                self.async_on_remove(rem2)
        except Exception:
            self._status_coordinator = None

        # Restore last known state immediately; prevents unknown on restart mid-session
        if self._is_stream_active():
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                # Restore last attributes as well for better end-detection and UI context
                attrs = dict(getattr(last, "attributes", {}) or {})
                self._attr_extra_state_attributes = attrs
                # If saved payload indicates the session ended long ago, clear state on startup
                ended_by_attrs = False
                try:
                    end_iso = attrs.get("end") or attrs.get("EndDate")
                    if end_iso and not self._is_replay_active():
                        end_dt = datetime.datetime.fromisoformat(
                            str(end_iso).replace("Z", "+00:00")
                        )
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=datetime.UTC)
                        now_utc = datetime.datetime.now(datetime.UTC)
                        if now_utc >= (end_dt + datetime.timedelta(minutes=5)):
                            # Also consider live status if available
                            st = str(self._live_status() or "").strip()
                            if st not in ("Started", "Green", "GreenFlag"):
                                ended_by_attrs = True
                except Exception:
                    ended_by_attrs = False
                if ended_by_attrs:
                    # Keep last label in attributes, but clear current state
                    if last.state:
                        with suppress(Exception):
                            self._attr_extra_state_attributes = dict(attrs)
                            self._attr_extra_state_attributes.setdefault(
                                "last_label", last.state
                            )
                            self._attr_extra_state_attributes["active"] = False
                    self._attr_native_value = None
                    with suppress(Exception):
                        getLogger(__name__).debug(
                            "CurrentSession: Restored as ended (cleared) based on saved end=%s",
                            attrs.get("end") or attrs.get("EndDate"),
                        )
                else:
                    self._attr_native_value = last.state
                    with suppress(Exception):
                        getLogger(__name__).debug(
                            "CurrentSession: Restored last state: %s", last.state
                        )
        else:
            self._clear_state()

        # Initialize from coordinator if available, but avoid clearing state at startup
        init = self._extract_current()
        updated = init is not None
        if init is not None and self._is_stream_active():
            self._apply_payload(init, allow_clear=False)
            with suppress(Exception):
                getLogger(__name__).debug(
                    "CurrentSession: Initialized from coordinator (no clear on startup): %s",
                    init,
                )
        self._handle_stream_state(updated)

        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        return _live_models.CurrentSessionModel._extract_current(self)

    def _resolve_label(self, info: dict) -> tuple[str | None, dict]:
        return _live_models.CurrentSessionModel._resolve_label(self, info)

    def _live_status_payload(self) -> dict | None:
        return _live_models.CurrentSessionModel._live_status_payload(self)

    def _live_status(self) -> str | None:
        return _live_models.CurrentSessionModel._live_status(self)

    def _mapped_live_status(self) -> str | None:
        return _live_models.CurrentSessionModel._mapped_live_status(self)

    def _apply_payload(self, raw: dict, allow_clear: bool = True) -> None:
        return _live_models.CurrentSessionModel._apply_payload(self, raw, allow_clear)

    def _handle_coordinator_update(self) -> None:
        return _live_models.CurrentSessionModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self.async_write_ha_state(*args)

    def _handle_status_update(self) -> None:
        return _live_models.CurrentSessionModel._handle_status_update(self)

    @property
    def state(self):
        return _live_models.CurrentSessionModel.__dict__["state"].fget(self)

    def _clear_state(self) -> None:
        return _live_models.CurrentSessionModel._clear_state(self)


class F1RaceControlSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Expose the latest Race Control message as an easy-to-use sensor."""

    _device_category = "officials"
    _history_limit = 5

    _attr_translation_key = "race_control"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-outline"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_event_id: str | None = None
        self._history: list[dict] = []
        self._sequence = 0

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        payload = self._extract_current()
        updated = payload is not None
        if payload:
            self._apply_payload(payload, force=True)
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    self._attr_native_value = last.state
                    self._attr_extra_state_attributes = dict(
                        getattr(last, "attributes", {}) or {}
                    )
                    self._last_event_id = self._attr_extra_state_attributes.get(
                        "event_id"
                    )
                    hist = self._attr_extra_state_attributes.get("history")
                    if isinstance(hist, list):
                        self._history = [
                            dict(item)
                            for item in hist[: self._history_limit]
                            if isinstance(item, dict)
                        ]
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        return _live_models.RaceControlModel._extract_current(self)

    def _cleanup_string(self, value) -> str | None:
        return _live_models.RaceControlModel._cleanup_string(self, value)

    def _build_event_id(self, payload: dict) -> str | None:
        return _live_models.RaceControlModel._build_event_id(self, payload)

    def _resolve_icon(self, flag: str | None, category: str | None) -> str:
        return _live_models.RaceControlModel._resolve_icon(self, flag, category)

    def _format_state(self, payload: dict) -> str:
        return _live_models.RaceControlModel._format_state(self, payload)

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        return _live_models.RaceControlModel._apply_payload(self, payload, force=force)

    def _handle_coordinator_update(self) -> None:
        return _live_models.RaceControlModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    @property
    def state(self):
        return _live_models.RaceControlModel.__dict__["state"].fget(self)

    def _clear_state(self) -> None:
        return _live_models.RaceControlModel._clear_state(self)


# Regex patterns for track limits parsing
_TRACK_LIMITS_DELETED = re.compile(
    r"CAR (\d+) \(([A-Z]{2,3})\) (?:TIME [0-9:.]+|LAP) DELETED - "
    r"TRACK LIMITS AT TURN (\d+) LAP (\d+)",
    re.IGNORECASE,
)
_TRACK_LIMITS_WARNING = re.compile(
    r"BLACK AND WHITE FLAG FOR CAR (\d+) \(([A-Z]{2,3})\) - TRACK LIMITS",
    re.IGNORECASE,
)
_TRACK_LIMITS_PENALTY = re.compile(
    r"(\d+ SECOND TIME PENALTY) FOR CAR (\d+) \(([A-Z]{2,3})\) - TRACK LIMITS",
    re.IGNORECASE,
)


class F1TrackLimitsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor tracking track limits violations per driver.

    State: Total number of track limit violations in this session.
    Attributes:
        - by_driver: Dict keyed by TLA with violations per driver
        - total_deletions: Count of deleted times/laps
        - total_warnings: Count of BLACK AND WHITE flags
        - total_penalties: Count of track limits penalties
        - last_update: ISO timestamp of last update
    """

    _device_category = "officials"

    _attr_translation_key = "track_limits"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:map-marker-off"
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

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        reg = entry_runtime_registry(self.hass, self._entry_id)
        live_state = reg.get("live_state")
        if live_state is not None and hasattr(live_state, "add_listener"):
            try:
                self._live_state_unsub = live_state.add_listener(
                    self._handle_live_state
                )
                self.async_on_remove(self._live_state_unsub)
            except Exception:
                self._live_state_unsub = None

        # Restore prior state first, then apply any live messages.
        stream_active = self._is_stream_active()
        if stream_active:
            await self._restore_from_last()
            self._process_all_messages()
        else:
            self._clear_state()

        # Signal stream state - treat as updated when stream is active
        self._handle_stream_state(stream_active)
        self.async_write_ha_state()

    async def _restore_from_last(self) -> None:
        last = await self.async_get_last_state()
        if not last or last.state in (None, "unknown", "unavailable"):
            return
        try:
            self._attr_native_value = int(last.state)
        except (ValueError, TypeError):
            self._attr_native_value = 0
        attrs = dict(getattr(last, "attributes", {}) or {})
        self._attr_extra_state_attributes = attrs
        by_driver = attrs.get("by_driver")
        if isinstance(by_driver, dict):
            self._by_driver = by_driver

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        return _live_models.TrackLimitsModel._handle_live_state(self, is_live, reason)

    def _build_message_id(self, msg: dict) -> str:
        return _live_models.TrackLimitsModel._build_message_id(self, msg)

    def _process_message(self, msg: dict) -> bool:
        return _live_models.TrackLimitsModel._process_message(self, msg)

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
        return _live_models.TrackLimitsModel._add_violation(
            self,
            tla=tla,
            racing_number=racing_number,
            violation_type=violation_type,
            utc=utc,
            lap=lap,
            turn=turn,
            penalty=penalty,
        )

    def _process_all_messages(self) -> None:
        return _live_models.TrackLimitsModel._process_all_messages(self)

    def _update_attributes(self) -> None:
        return _live_models.TrackLimitsModel._update_attributes(self)

    def _handle_coordinator_update(self) -> None:
        return _live_models.TrackLimitsModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    @property
    def state(self):
        return _live_models.TrackLimitsModel.__dict__["state"].fget(self)

    def _clear_state(self) -> None:
        return _live_models.TrackLimitsModel._clear_state(self)


# Regex patterns for investigations/penalties parsing
# Matches both "CAR 43 (COL)", "CARS 44 (HAM)", and "23 (ALB)" (second driver without prefix)
_DRIVER_PATTERN = re.compile(r"(?:CARS? )?(\d+) \(([A-Z]{2,3})\)")

# NOTED patterns - handles many prefix variants:
# - Location: TURN X, TURNS X TO Y, LAP X TURN X, PIT LANE, PIT EXIT, PIT ENTRY, START/FINISH STRAIGHT
# - Session: Q1, Q2, Q3, SQ1, SQ2, SQ3
# - Prefix: FIA STEWARDS:, UPDATE:, CORRECTION:
_INCIDENT_NOTED = re.compile(
    r"(?:(?:UPDATE|CORRECTION):?\s*)?"
    r"(?:FIA STEWARDS:\s*)?"
    r"(?:(?:S?Q[123]|LAP \d+)\s+)?"
    r"(?:(?:TURNS? \d+(?:\s+TO\s+\d+)?|PIT (?:LANE|EXIT|ENTRY)|START/FINISH STRAIGHT)\s+)?"
    r"INCIDENT(?: INVOLVING)? .+ NOTED",
    re.IGNORECASE,
)

# UNDER INVESTIGATION - also handles CORRECTION:: (with double colon typo in data)
_UNDER_INVESTIGATION = re.compile(
    r"(?:FIA STEWARDS:|CORRECTION::?)\s*.+ UNDER INVESTIGATION",
    re.IGNORECASE,
)

# NO FURTHER - handles both INVESTIGATION and ACTION variants
_NO_FURTHER_INVESTIGATION = re.compile(
    r"FIA STEWARDS:\s*.+ (?:REVIEWED\s+)?NO FURTHER (?:INVESTIGATION|ACTION)",
    re.IGNORECASE,
)

# PENALTY patterns - X SECOND TIME PENALTY, DRIVE THROUGH, STOP/GO, REPRIMAND
_PENALTY_ISSUED = re.compile(
    r"FIA STEWARDS:\s*(\d+ SECOND TIME PENALTY|DRIVE THROUGH PENALTY|"
    r"(?:\d+\s+(?:SECOND\s+)?)?STOP(?:[-\s]+AND[-\s]+|/)?GO PENALTY|"
    r"REPRIMAND \([^)]+\))\s+"
    r"FOR CAR (\d+) \(([A-Z]{2,3})\)",
    re.IGNORECASE,
)

_PENALTY_SERVED = re.compile(
    r"FIA STEWARDS:\s*PENALTY SERVED",
    re.IGNORECASE,
)

_WILL_BE_INVESTIGATED_AFTER = re.compile(
    r"WILL BE INVESTIGATED AFTER THE (?:RACE|SESSION)",
    re.IGNORECASE,
)

# Location extraction - extended to include PIT EXIT, PIT ENTRY, TURNS X TO Y
_LOCATION_PATTERN = re.compile(
    r"(TURNS? \d+(?:\s+TO\s+\d+)?|PIT (?:LANE|EXIT|ENTRY)|START/FINISH STRAIGHT)",
    re.IGNORECASE,
)

_REASON_PATTERN = re.compile(
    r"(?:NOTED|UNDER INVESTIGATION|NO FURTHER (?:INVESTIGATION|ACTION))\s*-\s*(.+?)$",
    re.IGNORECASE,
)


class F1InvestigationsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor tracking current investigations and penalties.

    Shows only currently relevant information:
    - NOTED incidents stay until resolved (NFI/UNDER INVESTIGATION/PENALTY)
    - UNDER INVESTIGATION items stay until resolved (NFI/PENALTY)
    - NO FURTHER ACTION items auto-expire after 5 minutes
    - PENALTY items stay until SERVED message received

    State: Count of actionable items (noted + under_investigation + penalties).
    Attributes:
        - noted: List of incidents noted but not yet under investigation
        - under_investigation: List of active investigations
        - no_further_action: List of recent NFI decisions (auto-expire)
        - penalties: List of pending penalties awaiting service
        - last_update: ISO timestamp of last update
    """

    _device_category = "officials"

    # NFI decisions expire after this many seconds
    NFI_EXPIRY_SECONDS = 300  # 5 minutes

    _attr_translation_key = "investigations"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-search"
        self._attr_native_value = 0
        # Internal state: keyed by incident key for matching
        self._noted: dict[str, dict] = {}
        self._under_investigation: dict[str, dict] = {}
        self._nfi: dict[str, dict] = {}  # Includes nfi_utc for expiry
        self._penalties: list[dict] = []
        self._processed_ids: set[str] = set()
        self._live_state_unsub = None
        self._session_info_coordinator = None
        self._session_key: str | None = None
        self._session_time: datetime.datetime | None = (
            None  # Track latest message time for NFI expiry
        )
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
        return _live_models.InvestigationsModel._make_incident_key(
            self, drivers, location, reason
        )

    def _find_incident_by_drivers(
        self, driver_tlas: list[str], collection: dict[str, dict]
    ) -> str | None:
        return _live_models.InvestigationsModel._find_incident_by_drivers(
            self, driver_tlas, collection
        )

    def _find_incident_containing_driver(
        self, driver_tla: str, collection: dict[str, dict]
    ) -> str | None:
        return _live_models.InvestigationsModel._find_incident_containing_driver(
            self, driver_tla, collection
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        reg = entry_runtime_registry(self.hass, self._entry_id)
        live_state = reg.get("live_state")
        if live_state is not None and hasattr(live_state, "add_listener"):
            try:
                self._live_state_unsub = live_state.add_listener(
                    self._handle_live_state
                )
                self.async_on_remove(self._live_state_unsub)
            except Exception:
                self._live_state_unsub = None

        self._session_info_coordinator = reg.get("session_info_coordinator")
        if self._session_info_coordinator is not None and hasattr(
            self._session_info_coordinator, "async_add_listener"
        ):
            try:
                removal = self._session_info_coordinator.async_add_listener(
                    self._handle_session_info_update
                )
                self.async_on_remove(removal)
                self._session_key = self._current_session_key()
            except Exception:
                self._session_info_coordinator = None

        # Restore prior state first, then apply any live messages.
        stream_active = self._is_stream_active()
        if stream_active:
            await self._restore_from_last()
            self._process_all_messages()
        else:
            self._clear_state()

        # Signal stream state
        self._handle_stream_state(stream_active)
        self.async_write_ha_state()

    async def _restore_from_last(self) -> None:
        last = await self.async_get_last_state()
        if not last or last.state in (None, "unknown", "unavailable"):
            return
        attrs = dict(getattr(last, "attributes", {}) or {})
        restored_session_key = attrs.get("session_key")
        if restored_session_key is not None:
            restored_session_key = str(restored_session_key).strip() or None
        if (
            self._session_key is not None
            and restored_session_key is not None
            and restored_session_key != self._session_key
        ):
            self._clear_state()
            return
        if self._session_key is None:
            self._session_key = restored_session_key
        try:
            self._attr_native_value = int(last.state)
        except (ValueError, TypeError):
            self._attr_native_value = 0
        noted = attrs.get("noted")
        under_inv = attrs.get("under_investigation")
        nfi = attrs.get("no_further_action")
        penalties = attrs.get("penalties")
        if isinstance(noted, list):
            self._noted = {}
            for item in noted:
                if not isinstance(item, dict):
                    continue
                key = self._make_incident_key(
                    item.get("drivers") or [],
                    item.get("location"),
                    item.get("reason"),
                )
                self._noted[key] = dict(item)
        if isinstance(under_inv, list):
            self._under_investigation = {}
            for item in under_inv:
                if not isinstance(item, dict):
                    continue
                key = self._make_incident_key(
                    item.get("drivers") or [],
                    item.get("location"),
                    item.get("reason"),
                )
                self._under_investigation[key] = dict(item)
        if isinstance(nfi, list):
            self._nfi = {}
            for item in nfi:
                if not isinstance(item, dict):
                    continue
                key = self._make_incident_key(
                    item.get("drivers") or [],
                    item.get("location"),
                    item.get("reason"),
                )
                self._nfi[key] = dict(item)
        if isinstance(penalties, list):
            self._penalties = [p for p in penalties if isinstance(p, dict)]
        attrs["session_key"] = self._session_key
        self._attr_extra_state_attributes = attrs
        last_update = attrs.get("last_update")
        if last_update:
            with suppress((ValueError, TypeError)):
                parsed = dt_util.parse_datetime(last_update)
                if parsed is not None:
                    self._session_time = parsed

    def _current_session_key(self) -> str | None:
        return _live_models.InvestigationsModel._current_session_key(self)

    def _handle_session_info_update(self) -> None:
        return _live_models.InvestigationsModel._handle_session_info_update(self)

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        return _live_models.InvestigationsModel._handle_live_state(
            self, is_live, reason
        )

    def _build_message_id(self, msg: dict) -> str:
        return _live_models.InvestigationsModel._build_message_id(self, msg)

    def _extract_drivers(self, message: str) -> list[tuple[str, str]]:
        return _live_models.InvestigationsModel._extract_drivers(self, message)

    def _extract_location(self, message: str) -> str | None:
        return _live_models.InvestigationsModel._extract_location(self, message)

    def _extract_reason(self, message: str) -> str | None:
        return _live_models.InvestigationsModel._extract_reason(self, message)

    def _expire_nfi_items(self) -> bool:
        return _live_models.InvestigationsModel._expire_nfi_items(self)

    def _process_message(self, msg: dict) -> bool:
        return _live_models.InvestigationsModel._process_message(self, msg)

    def _process_all_messages(self) -> None:
        return _live_models.InvestigationsModel._process_all_messages(self)

    def _update_attributes(self) -> None:
        return _live_models.InvestigationsModel._update_attributes(self)

    def _handle_coordinator_update(self) -> None:
        return _live_models.InvestigationsModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    @property
    def state(self):
        return _live_models.InvestigationsModel.__dict__["state"].fget(self)

    def _clear_state(self) -> None:
        return _live_models.InvestigationsModel._clear_state(self)


class F1TeamRadioSensor(
    _ReplayOrAuthGatedStreamMixin, F1BaseEntity, RestoreEntity, SensorEntity
):
    """Sensor exposing the latest Team Radio clip."""

    _device_category = "drivers"
    # Keep full clips and transcripts live without growing the Recorder database.
    _unrecorded_attributes = frozenset(
        {"history", "raw_message", "transcription_text", "transcription_segments"}
    )
    _history_limit = 20

    _attr_translation_key = "team_radio"
    _auth_gated_stream = "TeamRadio"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:headset"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._last_utc: str | None = None
        self._history: list[dict] = []
        self._sequence = 0

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        payload = self._extract_current()
        updated = payload is not None
        if payload:
            self._apply_payload(payload, force=True)
        else:
            # Restored URLs cannot be resolved without their coordinator captures.
            self._clear_state()
        self._handle_stream_state(updated)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        return _live_models.TeamRadioModel._extract_current(self)

    @staticmethod
    def _cleanup_string(value) -> str | None:
        return _live_models.TeamRadioModel._cleanup_string(value)

    def _normalize_utc(self, utc_str: str | None) -> str | None:
        return _live_models.TeamRadioModel._normalize_utc(self, utc_str)

    def _build_clip_url(self, payload: dict, path: str | None) -> str | None:
        return _live_models.TeamRadioModel._build_clip_url(self, payload, path)

    @staticmethod
    def _transcription_attributes(payload: dict) -> dict[str, Any]:
        return _live_models.TeamRadioModel._transcription_attributes(payload)

    def _identity_attributes(self, payload: dict) -> dict[str, str | None]:
        return _live_models.TeamRadioModel._identity_attributes(self, payload)

    def _build_history(self) -> list[dict]:
        return _live_models.TeamRadioModel._build_history(self)

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        return _live_models.TeamRadioModel._apply_payload(self, payload, force=force)

    def _handle_coordinator_update(self) -> None:
        return _live_models.TeamRadioModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    @property
    def state(self):
        return _live_models.TeamRadioModel.__dict__["state"].fget(self)

    def _clear_state(self) -> None:
        return _live_models.TeamRadioModel._clear_state(self)


class F1PitStopsSensor(
    _ReplayOrAuthGatedStreamMixin, F1BaseEntity, RestoreEntity, SensorEntity
):
    """Live pit stops for all cars (aggregated).

    - State: total pit stops (int)
    - Attributes: cars (dict keyed by racing number), last_update
    """

    _device_category = "drivers"
    _unrecorded_attributes = frozenset({"cars"})

    _attr_translation_key = "pitstops"
    _auth_gated_stream = "PitStopSeries"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car-wrench"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"cars": {}, "last_update": None}
        self._attr_state_class = SensorStateClass.TOTAL
        self._last_reset: datetime.datetime | None = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        init = self._extract_current()
        updated = init is not None
        if init is not None:
            self._apply_payload(init, force=True)
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    try:
                        self._attr_native_value = int(float(str(last.state)))
                    except Exception:
                        self._attr_native_value = last.state
                    self._attr_extra_state_attributes = dict(
                        getattr(last, "attributes", {}) or {}
                    )
                    self._last_reset = self._parse_last_reset(
                        self._attr_extra_state_attributes.get("last_reset")
                    )
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        return _live_models.PitStopsModel._extract_current(self)

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        return _live_models.PitStopsModel._apply_payload(self, payload, force=force)

    @staticmethod
    def _parse_last_reset(value) -> datetime.datetime | None:
        return _live_models.PitStopsModel._parse_last_reset(value)

    @property
    def last_reset(self) -> datetime.datetime | None:
        return _live_models.PitStopsModel.__dict__["last_reset"].fget(self)

    def _handle_coordinator_update(self) -> None:
        return _live_models.PitStopsModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    def _clear_state(self) -> None:
        return _live_models.PitStopsModel._clear_state(self)


class F1ChampionshipPredictionDriversSensor(_ChampionshipPredictionBase):
    """Predicted Drivers Championship winner (P1).

    - State: predicted P1 driver TLA (string) when available
    - Attributes: predicted_driver_p1, drivers, last_update
    """

    _attr_translation_key = "championship_prediction_drivers"

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        return _live_models.DriverPredictionModel._apply_payload(
            self, payload, force=force
        )


class F1ChampionshipPredictionTeamsSensor(_ChampionshipPredictionBase):
    """Predicted Constructors Championship winner (P1).

    - State: predicted P1 team name (string)
    - Attributes: predicted_team_p1, teams, last_update
    """

    _attr_translation_key = "championship_prediction_teams"

    _DEFAULT_ICON = "mdi:trophy-variant"

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        return _live_models.TeamPredictionModel._apply_payload(
            self, payload, force=force
        )


class F1RaceLapCountSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live race lap count based on LapCount coordinator.

    - State: current lap (int)
    - Attributes: total_laps (if present), measurement_time, measurement_age_seconds, received_at, raw
    - Restore: Remembers last value/attributes on restart and keeps them until new feed data arrives.
    """

    _device_category = "session"

    _attr_translation_key = "race_lap_count"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:counter"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        self._stale_timer = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        init = self._extract_current()
        updated = init is not None
        if init is not None:
            self._apply_payload(init)
            with suppress(Exception):
                getLogger(__name__).debug(
                    "RaceLapCount: Initialized from coordinator: %s", init
                )
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    self._attr_native_value = self._to_int(last.state)
                    attrs = dict(getattr(last, "attributes", {}) or {})
                    for k in (
                        "measurement_time",
                        "measurement_age_seconds",
                        "received_at",
                    ):
                        attrs.pop(k, None)
                    self._attr_extra_state_attributes = attrs
                    with suppress(Exception):
                        t_ref = None
                        mt = self._attr_extra_state_attributes.get("measurement_time")
                        if isinstance(mt, str) and mt:
                            t_ref = datetime.datetime.fromisoformat(
                                mt.replace("Z", "+00:00")
                            )
                            if t_ref.tzinfo is None:
                                t_ref = t_ref.replace(tzinfo=datetime.UTC)
                            self._last_timestamped_dt = t_ref
                        if t_ref is None:
                            ra = self._attr_extra_state_attributes.get("received_at")
                            if isinstance(ra, str) and ra:
                                t_ref = datetime.datetime.fromisoformat(
                                    ra.replace("Z", "+00:00")
                                )
                                if t_ref.tzinfo is None:
                                    t_ref = t_ref.replace(tzinfo=datetime.UTC)
                        if isinstance(t_ref, datetime.datetime):
                            self._last_received_utc = t_ref
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()
        # No staleness timer: we keep last known value until new feed data arrives

    async def async_will_remove_from_hass(self) -> None:
        with suppress(Exception):
            if self._stale_timer:
                self._stale_timer()
                self._stale_timer = None

    def _to_int(self, value):
        return _live_models.LapCountModel._to_int(self, value)

    def _extract_current(self) -> dict | None:
        return _live_models.LapCountModel._extract_current(self)

    def _apply_payload(self, raw: dict) -> None:
        return _live_models.LapCountModel._apply_payload(self, raw)

        # No staleness handling: do not clear state; keep last value until a new payload arrives

    def _schedule_stale_check(
        self,
        t_ref: datetime.datetime | None = None,
        now_utc: datetime.datetime | None = None,
    ) -> None:
        with suppress(Exception):
            if now_utc is None:
                now_utc = dt_util.utcnow()
            if t_ref is None:
                t_ref = None
                mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
                if isinstance(mt, str) and mt:
                    try:
                        t_ref = datetime.datetime.fromisoformat(
                            mt.replace("Z", "+00:00")
                        )
                        if t_ref.tzinfo is None:
                            t_ref = t_ref.replace(tzinfo=datetime.UTC)
                    except Exception:
                        t_ref = None
                if t_ref is None and isinstance(
                    self._last_timestamped_dt, datetime.datetime
                ):
                    t_ref = self._last_timestamped_dt
                if t_ref is None and isinstance(
                    self._last_received_utc, datetime.datetime
                ):
                    t_ref = self._last_received_utc
            if not isinstance(t_ref, datetime.datetime):
                return
            age = (now_utc - t_ref).total_seconds()
            threshold = 300
            delay = max(0.0, threshold - age)
            if self._stale_timer:
                with suppress(Exception):
                    self._stale_timer()
                self._stale_timer = None

            def _cb(_now):
                self._handle_stale_timeout()

            self._stale_timer = async_call_later(self.hass, delay, _cb)

    def _handle_stale_timeout(self) -> None:
        return _live_models.LapCountModel._handle_stale_timeout(self)

    def _safe_write_ha_state(self) -> None:
        try:
            import asyncio as _asyncio

            in_loop = False
            try:
                running = _asyncio.get_running_loop()
                in_loop = running is self.hass.loop
            except RuntimeError:
                in_loop = False
            if in_loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()
        except Exception:
            with suppress(Exception):
                self.schedule_update_ha_state()

    def _handle_coordinator_update(self) -> None:
        return _live_models.LapCountModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    def _clear_state(self) -> None:
        return _live_models.LapCountModel._clear_state(self)


class F1DriverListSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live driver list sensor.

    - State: number of drivers in attributes
    - Attributes: drivers: [ { racing_number, tla, name, first_name, last_name, team, team_color, headshot_small, headshot_large, reference } ]
    - Behavior: restores last known state; logs only on change; respects consolidated drivers coordinator.
    """

    _device_category = "drivers"

    _attr_translation_key = "driver_list"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator (only if it has real driver data) or restore.
        #
        # LiveDriversCoordinator intentionally clears its consolidated state when
        # the live window ends to avoid briefly showing stale timing data at the
        # start of a new session. For `sensor.f1_drivers_driver_list` we *do* want to keep
        # the last known list for dashboards/UI, so we treat an empty coordinator
        # payload as "no update" and keep/restored state.
        updated = self._update_from_coordinator()
        if (not updated) and self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                with suppress(Exception):
                    from logging import getLogger

                    attrs = dict(getattr(last, "attributes", {}) or {})
                    # Drop legacy key 'headshot' if present (top-level or nested per-driver)
                    attrs.pop("headshot", None)
                    drivers_attr = attrs.get("drivers")
                    if isinstance(drivers_attr, list):
                        for drv in drivers_attr:
                            if isinstance(drv, dict):
                                drv.pop("headshot", None)
                    self._attr_extra_state_attributes = attrs
                    getLogger(__name__).debug(
                        "DriverList: Restored last state -> %s", last.state
                    )
        # If we have neither live data nor a restored state, try a one-time
        # bootstrap from Ergast/Jolpica standings (typically last completed season).
        if self._attr_native_value is None:
            with suppress(Exception):
                boot = self._bootstrap_from_ergast()
                if boot:
                    from logging import getLogger

                    getLogger(__name__).info(
                        "DriverList: Bootstrapped from Ergast/Jolpica standings (no live feed / no restore-state yet)"
                    )
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        updated = self._update_from_coordinator()
        if not updated:
            # No driver payload (common outside live windows): keep last value/attrs.
            return
        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return
        with suppress(Exception):
            from logging import getLogger

            getLogger(__name__).debug(
                "DriverList: Computed at %s -> count=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
            )
        # Rate limit writes to once per 60s
        try:
            import time as _time

            lw = getattr(self, "_last_write_ts", None)
            now = _time.time()
            if lw is None or (now - lw) >= 60.0:
                self._last_write_ts = now
                self._safe_write_ha_state()
            else:
                # Schedule a delayed write at the 60s boundary if not already pending
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    self._pending_write = True
                    delay = max(0.0, 60.0 - (now - lw)) if lw is not None else 60.0
                    from homeassistant.helpers.event import async_call_later as _later

                    def _do_write(_):
                        try:
                            self._last_write_ts = _time.time()
                            self._safe_write_ha_state()
                        finally:
                            self._pending_write = False

                    _later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _update_from_coordinator(self) -> bool:
        return _live_models.DriverListModel._update_from_coordinator(self)

    def _bootstrap_from_ergast(self) -> bool:
        return _live_models.DriverListModel._bootstrap_from_ergast(self)

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
        return _live_models.DriverListModel.__dict__["state"].fget(self)


class F1CurrentTyresSensor(_CoordinatorStreamSensorBase):
    """Live sensor exposing current tyre compound per car.

    - State: number of drivers exposed in the list.
    - Attributes: drivers: [
        {
          racing_number,
          compound, compound_short, compound_color,
          new, stint_laps
        }
      ]
    """

    # Simple mappings for UI-friendly representation
    _COMPOUND_SHORT = {
        "SOFT": "S",
        "MEDIUM": "M",
        "HARD": "H",
        "INTERMEDIATE": "I",
        "WET": "W",
    }

    _COMPOUND_COLOR = {
        # Pirelli standard colors (approximate)
        "SOFT": "#FF0000",  # red
        "MEDIUM": "#FFFF00",  # yellow
        "HARD": "#FFFFFF",  # white
        "INTERMEDIATE": "#00FF00",  # green
        "WET": "#0000FF",  # blue
    }

    _attr_translation_key = "current_tyres"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:tire"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    def _update_from_coordinator(self) -> bool:
        return _live_models.CurrentTyresModel._update_from_coordinator(self)

    def _clear_state(self) -> None:
        return _live_models.CurrentTyresModel._clear_state(self)

    @property
    def state(self):
        return _live_models.CurrentTyresModel.__dict__["state"].fget(self)


class F1TyreStatisticsSensor(_CoordinatorStreamSensorBase):
    """Live sensor exposing aggregated tyre statistics per compound.

    - State: fastest compound name (e.g., "SOFT")
    - Attributes:
        - fastest_time: Overall fastest lap time
        - fastest_time_secs: Fastest time in seconds
        - deltas: Delta to fastest per compound
        - compounds: {
            "SOFT": {
                "best_times": [top 3 with driver info],
                "total_laps": int,
                "sets_used": int (new tyres only),
                "sets_used_total": int (all stints),
            },
            ...
        }
    """

    # Compound colors for UI representation
    _COMPOUND_COLOR = {
        "SOFT": "#FF0000",  # red
        "MEDIUM": "#FFFF00",  # yellow
        "HARD": "#FFFFFF",  # white
        "INTERMEDIATE": "#00FF00",  # green
        "WET": "#0000FF",  # blue
    }

    _attr_translation_key = "tyre_statistics"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-bar"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @staticmethod
    def _compound_from_tyre_history(info: dict) -> str | None:
        return _live_models.TyreStatisticsModel._compound_from_tyre_history(info)

    def _update_waiting_for_compound_data(self, data: dict) -> bool:
        return _live_models.TyreStatisticsModel._update_waiting_for_compound_data(
            self, data
        )

    def _update_from_coordinator(self) -> bool:
        return _live_models.TyreStatisticsModel._update_from_coordinator(self)

    def _clear_state(self) -> None:
        return _live_models.TyreStatisticsModel._clear_state(self)

    @property
    def state(self):
        return _live_models.TyreStatisticsModel.__dict__["state"].fget(self)


class F1StartingGridSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor exposing the currently relevant starting grid for the weekend."""

    _device_category = "session"
    _unrecorded_attributes = frozenset({"grid"})
    _attr_translation_key = "starting_grid"

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
        self._attr_icon = "mdi:grid"
        self._attr_native_value = None
        self._attr_extra_state_attributes = self._empty_attributes()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        updated = self._update_from_coordinator()
        if not updated:
            await self._restore_if_relevant()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        return _live_models.StartingGridModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self._safe_write_ha_state(*args)

    def _update_from_coordinator(self) -> bool:
        return _live_models.StartingGridModel._update_from_coordinator(self)

    async def _restore_if_relevant(self) -> bool:
        last = await self.async_get_last_state()
        if not last or last.state in (None, "unknown", "unavailable"):
            return False
        attrs = dict(getattr(last, "attributes", {}) or {})
        current = (
            self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        )
        current_weekend = current.get("weekend_key")
        current_context = current.get("grid_context")
        if not current_weekend or attrs.get("weekend_key") != current_weekend:
            return False
        if current_context and attrs.get("grid_context") != current_context:
            return False
        if attrs.get("status") == "completed" or current.get("status") == "completed":
            return False
        restored = {key: attrs.get(key) for key in self._ATTR_KEYS}
        restored["status"] = str(last.state)
        grid = attrs.get("grid")
        restored["grid"] = grid if isinstance(grid, list) else []
        restored["grid_count"] = len(restored["grid"])
        self._apply_payload(restored)
        return True

    def _apply_payload(self, data: dict) -> None:
        return _live_models.StartingGridModel._apply_payload(self, data)

    @classmethod
    def _empty_attributes(cls) -> dict:
        return _live_models.StartingGridModel._empty_attributes.__func__(cls)

    @property
    def native_value(self):
        return _live_models.StartingGridModel.__dict__["native_value"].fget(self)

    @property
    def extra_state_attributes(self):
        return _live_models.StartingGridModel.__dict__["extra_state_attributes"].fget(
            self
        )


class F1DriverPositionsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live sensor tracking driver positions and lap times.

    - State: current lap number (leader's lap)
    - Attributes:
        - drivers: {
            racing_number: {
                "tla": "VER",
                "name": "Max Verstappen",
                "team": "Red Bull Racing",
                "grid_position": "1",
                "current_position": "2",
                "laps": {
                    "1": "1:32.456",
                    "2": "1:31.789",
                    ...
                },
                "completed_laps": 45,
                "status": "on_track",
                "gap_to_leader": "+1.234",
                "interval_to_position_ahead": "+0.456",
                "in_pit": False,
                "pit_out": False,
                "retired": False,
                "stopped": False,
                "best_lap_time": "1:30.456",
                "best_lap_time_secs": 90.456,
                "best_lap_lap": 40,
                "last_lap_status": {
                    "time": "1:30.789",
                    "lap": 45,
                    "overall_fastest": False,
                    "personal_fastest": False,
                },
                "fastest_lap": False,
                "fastest_lap_time": "1:29.123",
                "fastest_lap_time_secs": 89.123,
                "fastest_lap_lap": 42,
            },
            ...
        }
        - total_laps: 70 (race distance, if known)
        - fastest_lap: {
            "racing_number": "16",
            "tla": "LEC",
            "name": "Charles Leclerc",
            "team": "Ferrari",
            "team_color": "#DC0000",
            "lap": 42,
            "time": "1:29.123",
            "time_secs": 89.123,
          }
    """

    _device_category = "drivers"
    _unrecorded_attributes = frozenset({"drivers"})
    _PIT_OUT_HOLD_SECONDS = 6.0

    _attr_translation_key = "driver_positions"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:podium"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "drivers": [],
            "total_laps": None,
            "fastest_lap": None,
        }
        self._last_write_ts: float | None = None
        self._pending_write: bool = False
        self._pending_write_cancel = None
        self._pit_out_until: dict[str, float] = {}
        self._pit_out_last: dict[str, bool] = {}
        self._session_info_coordinator = None
        self._session_status_coordinator = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self._cancel_pending_state_write)

        # Subscribe to session coordinators for accurate gating and Q-part updates.
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            self._session_info_coordinator = reg.get("session_info_coordinator")
            if self._session_info_coordinator is not None:
                rem_info = self._session_info_coordinator.async_add_listener(
                    self._handle_session_info_update
                )
                self.async_on_remove(rem_info)
            self._session_status_coordinator = reg.get("session_status_coordinator")
            if self._session_status_coordinator is not None:
                rem_status = self._session_status_coordinator.async_add_listener(
                    self._handle_session_status_update
                )
                self.async_on_remove(rem_status)
        except Exception:
            self._session_info_coordinator = None
            self._session_status_coordinator = None

        # Try coordinator first
        updated = self._update_from_coordinator(initial=True)

        # Restore if coordinator has no data
        if (not updated) and self._attr_native_value is None:
            if self._is_stream_active():
                await self._restore_state()
            else:
                self._clear_state()

        self._handle_stream_state(updated)

        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    async def _restore_state(self) -> None:
        """Restore state from Home Assistant's state history."""
        last = await self.async_get_last_state()
        if not last or last.state in (None, "unknown", "unavailable"):
            return
        try:
            self._attr_native_value = (
                int(last.state) if last.state and last.state.isdigit() else None
            )
        except Exception:
            self._attr_native_value = None
        with suppress(Exception):
            attrs = dict(getattr(last, "attributes", {}) or {})
            self._attr_extra_state_attributes = self._normalize_restored_attributes(
                attrs
            )
            getLogger(__name__).debug(
                "DriverPositions: Restored last state -> lap %s", last.state
            )

    def _handle_coordinator_update(self) -> None:
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

        self._rate_limited_write()

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

        self._rate_limited_write()

    @staticmethod
    def _normalize_qualifying_part(value: object) -> int | None:
        return _live_models.DriverPositionsModel._normalize_qualifying_part(value)

    def _resolve_current_qualifying_part(
        self, data: dict[str, object], *, is_qualifying: bool
    ) -> int | None:
        return _live_models.DriverPositionsModel._resolve_current_qualifying_part(
            self, data, is_qualifying=is_qualifying
        )

    def _get_session_type_and_name(self) -> tuple[str | None, str | None]:
        return _live_models.DriverPositionsModel._get_session_type_and_name(self)

    def _get_session_from_replay(self) -> tuple[str | None, str | None]:
        return _live_models.DriverPositionsModel._get_session_from_replay(self)

    def _get_session_name_from_window(self) -> tuple[str | None, str | None]:
        return _live_models.DriverPositionsModel._get_session_name_from_window(self)

    @staticmethod
    def _is_race_or_sprint(session_type: str | None, session_name: str | None) -> bool:
        return _live_models.DriverPositionsModel._is_race_or_sprint(
            session_type, session_name
        )

    def _is_qualifying_like(self) -> bool:
        return _live_models.DriverPositionsModel._is_qualifying_like(self)

    def _normalize_restored_attributes(self, attrs: dict) -> dict:
        return _live_models.DriverPositionsModel._normalize_restored_attributes(
            self, attrs
        )

    def _update_from_coordinator(self, *, initial: bool = False) -> bool:
        return _live_models.DriverPositionsModel._update_from_coordinator(
            self, initial=initial
        )

    def _is_replay_active(self) -> bool:
        return _live_models.DriverPositionsModel._is_replay_active(self)

    def _derive_driver_status(
        self,
        rn: str,
        timing: dict | None,
        now: float | None = None,
        default_on_track: bool = False,
    ) -> tuple[str | None, dict[str, object]]:
        return _live_models.DriverPositionsModel._derive_driver_status(
            self, rn, timing, now, default_on_track
        )

    def _clear_state(self) -> None:
        return _live_models.DriverPositionsModel._clear_state(self)

    @callback
    def _cancel_pending_state_write(self) -> None:
        """Release the entity's scheduled state write when it is removed."""
        if self._pending_write_cancel is not None:
            self._pending_write_cancel()
            self._pending_write_cancel = None
        self._pending_write = False

    def _rate_limited_write(self) -> None:
        """Write state with 1-second rate limiting."""
        import time as _time

        now = _time.time()

        if self._last_write_ts is None or (now - self._last_write_ts) >= 1.0:
            self._last_write_ts = now
            self._safe_write_ha_state()
        elif not self._pending_write:
            self._pending_write = True
            delay = max(0.0, 1.0 - (now - self._last_write_ts))

            @callback
            def _do_write(_now):
                self._pending_write_cancel = None
                try:
                    self._last_write_ts = _time.time()
                    self._safe_write_ha_state()
                finally:
                    self._pending_write = False

            self._pending_write_cancel = async_call_later(self.hass, delay, _do_write)

    @property
    def state(self):
        return _live_models.DriverPositionsModel.__dict__["state"].fget(self)


class F1StraightModeSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor for the 2026 Straight Mode (active aero) state.

    Reflects the track-wide active aerodynamic permission broadcasted via
    Race Control messages. Three states are possible: normal grip (full aero
    allowed), low grip (limited aero), and disabled (aero off).
    """

    _device_category = "session"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STRAIGHT_MODE_NORMAL, STRAIGHT_MODE_LOW, STRAIGHT_MODE_DISABLED]
    _attr_icon = "mdi:car-speed-limiter"
    _attr_translation_key = "straight_mode"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_suggested_object_id = default_object_id("straight_mode")
        self._attr_native_value: str | None = None
        self._attr_extra_state_attributes: dict[str, object] = {}

    def _session_is_terminal(self) -> bool:
        return _live_models.StraightModeModel._session_is_terminal(self)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        data = self._extract_data()
        updated = self._has_straight_mode_state(data)
        restored = False
        if updated and data is not None:
            self._apply_data(data)
        else:
            if not self._session_is_terminal():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    restored_state = str(last.state)
                    if restored_state in self._attr_options:
                        self._attr_native_value = restored_state
                        attrs = dict(last.attributes or {})
                        self._attr_extra_state_attributes = {
                            "overtake_enabled": attrs.get("overtake_enabled"),
                            "restored": True,
                        }
                        restored = True
            if not restored and not self._is_stream_active():
                self._clear_state()
        self._stream_last_active = self._is_stream_active()
        self.async_write_ha_state()

    def _extract_data(self) -> dict | None:
        return _live_models.StraightModeModel._extract_data(self)

    def _has_straight_mode_state(self, data: dict | None) -> bool:
        return _live_models.StraightModeModel._has_straight_mode_state(self, data)

    def _apply_data(self, data: dict) -> None:
        return _live_models.StraightModeModel._apply_data(self, data)

    def _handle_coordinator_update(self) -> None:
        return _live_models.StraightModeModel.refresh_data(self)

    def _notify(self, *args) -> None:
        self.async_write_ha_state(*args)

    @property
    def native_value(self):
        return _live_models.StraightModeModel.__dict__["native_value"].fget(self)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._attr_native_value is not None

    @property
    def extra_state_attributes(self):
        return _live_models.StraightModeModel.__dict__["extra_state_attributes"].fget(
            self
        )

    def _clear_state(self) -> None:
        return _live_models.StraightModeModel._clear_state(self)
