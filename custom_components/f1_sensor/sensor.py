from __future__ import annotations
from contextlib import suppress

import datetime
import asyncio
import re
from zoneinfo import ZoneInfo

import async_timeout
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import (
    async_call_later,
    async_track_time_interval,
    async_track_utc_time_change,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, ENABLE_DEVELOPMENT_MODE_UI
from .entity import F1AuxEntity, F1BaseEntity
from .const import (
    CONF_OPERATION_MODE,
    DEFAULT_OPERATION_MODE,
    LATEST_TRACK_STATUS,
    OPERATION_MODE_DEVELOPMENT,
    RACE_SWITCH_GRACE,
)
from .helpers import (
    format_entity_name,
    get_circuit_map_url,
    get_country_code,
    get_country_flag_url,
    get_next_race,
    get_timezone,
    normalize_track_status,
)
from .live_window import STATIC_BASE
from .replay_entities import F1ReplayStatusSensor
from logging import getLogger
from homeassistant.util import dt as dt_util

WMO_CODE_TO_MDI = {
    0: "mdi:weather-sunny",
    1: "mdi:weather-partly-cloudy",
    2: "mdi:weather-partly-cloudy",
    3: "mdi:weather-cloudy",
    45: "mdi:weather-fog",
    48: "mdi:weather-fog",
    51: "mdi:weather-rainy",
    53: "mdi:weather-rainy",
    55: "mdi:weather-rainy",
    56: "mdi:weather-snowy-rainy",
    57: "mdi:weather-snowy-rainy",
    61: "mdi:weather-rainy",
    63: "mdi:weather-rainy",
    65: "mdi:weather-pouring",
    66: "mdi:weather-snowy-rainy",
    67: "mdi:weather-snowy-rainy",
    71: "mdi:weather-snowy",
    73: "mdi:weather-snowy",
    75: "mdi:weather-snowy",
    77: "mdi:weather-snowy",
    80: "mdi:weather-rainy",
    81: "mdi:weather-rainy",
    82: "mdi:weather-pouring",
    85: "mdi:weather-snowy",
    86: "mdi:weather-snowy",
    95: "mdi:weather-lightning",
    96: "mdi:weather-lightning-rainy",
    99: "mdi:weather-lightning-rainy",
}


def _extract_driver_position(info: dict | None) -> str | None:
    if not isinstance(info, dict):
        return None
    timing = info.get("timing")
    if not isinstance(timing, dict):
        return None
    pos = timing.get("position")
    if pos is None:
        return None
    try:
        pos_str = str(pos).strip()
    except Exception:
        return pos if isinstance(pos, str) else None
    return pos_str or None


def _combine_date_time(
    date_str: str | None, time_str: str | None, *, force_utc: bool = False
) -> str | None:
    if not date_str:
        return None
    if not time_str:
        time_str = "00:00:00Z"
    dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(dt_str)
        if force_utc and dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _timezone_from_location(lat, lon):
    return get_timezone(lat, lon)


def _to_local(iso_ts, timezone):
    if not iso_ts or not timezone:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso_ts)
        return dt.astimezone(ZoneInfo(timezone)).isoformat()
    except Exception:
        return None


def _to_home(hass: HomeAssistant, iso_ts):
    if not iso_ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(iso_ts)
    except Exception:
        return None
    tzname = getattr(hass.config, "time_zone", None)
    if not tzname:
        return dt.isoformat()
    tzinfo = dt_util.get_time_zone(tzname)
    if tzinfo is None:
        return dt.isoformat()
    try:
        return dt.astimezone(tzinfo).isoformat()
    except Exception:
        return dt.isoformat()


def _to_float_value(value):
    try:
        if value is None:
            return 0.0
        s = str(value).strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0


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


def _set_suggested_object_id(entity, object_id: str) -> None:
    """Keep stable entity_id/object_id independent of user-facing name."""
    entity._attr_suggested_object_id = object_id


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Create sensors when integration is added."""
    data = hass.data[DOMAIN][entry.entry_id]
    base = entry.data.get("sensor_name", "F1")
    disabled: set[str] = set(entry.data.get("disabled_sensors") or [])
    mapping = {
        "next_race": (F1NextRaceSensor, data["race_coordinator"]),
        "track_time": (F1TrackTimeSensor, data["race_coordinator"]),
        "current_season": (F1CurrentSeasonSensor, data["race_coordinator"]),
        "driver_standings": (F1DriverStandingsSensor, data["driver_coordinator"]),
        "constructor_standings": (
            F1ConstructorStandingsSensor,
            data["constructor_coordinator"],
        ),
        "weather": (F1WeatherSensor, data["race_coordinator"]),
        "track_weather": (F1TrackWeatherSensor, data.get("weather_data_coordinator")),
        "race_lap_count": (F1RaceLapCountSensor, data.get("lap_count_coordinator")),
        "last_race_results": (F1LastRaceSensor, data["last_race_coordinator"]),
        "season_results": (F1SeasonResultsSensor, data["season_results_coordinator"]),
        "sprint_results": (F1SprintResultsSensor, data["sprint_results_coordinator"]),
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
        "fia_documents": (F1FiaDocumentsSensor, data.get("fia_documents_coordinator")),
        "race_control": (F1RaceControlSensor, data.get("race_control_coordinator")),
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
                object_id = f"{base}_top_three_p{pos + 1}"
                sensor = F1TopThreePositionSensor(
                    coord,
                    format_entity_name(
                        base, f"top_three_p{pos + 1}", include_base=False
                    ),
                    f"{entry.entry_id}_top_three_p{pos + 1}",
                    entry.entry_id,
                    base,
                    pos,
                )
                _set_suggested_object_id(sensor, object_id)
                sensors.append(sensor)
        elif key == "championship_prediction":
            if not coord:
                continue
            drivers_sensor = F1ChampionshipPredictionDriversSensor(
                coord,
                format_entity_name(
                    base, "championship_prediction_drivers", include_base=False
                ),
                f"{entry.entry_id}_championship_prediction_drivers",
                entry.entry_id,
                base,
            )
            _set_suggested_object_id(
                drivers_sensor, f"{base}_championship_prediction_drivers"
            )
            sensors.append(drivers_sensor)
            teams_sensor = F1ChampionshipPredictionTeamsSensor(
                coord,
                format_entity_name(
                    base, "championship_prediction_teams", include_base=False
                ),
                f"{entry.entry_id}_championship_prediction_teams",
                entry.entry_id,
                base,
            )
            _set_suggested_object_id(
                teams_sensor, f"{base}_championship_prediction_teams"
            )
            sensors.append(teams_sensor)
        elif key == "live_timing_diagnostics":
            # Dev-only diagnostic sensor; hide it fully unless dev UI is enabled.
            if ENABLE_DEVELOPMENT_MODE_UI:
                sensor = F1LiveTimingModeSensor(
                    hass,
                    entry.entry_id,
                    base,
                )
                _set_suggested_object_id(sensor, f"{base}_live_timing_mode")
                sensors.append(sensor)
        elif cls and coord:
            sensor = cls(
                coord,
                format_entity_name(base, key, include_base=False),
                f"{entry.entry_id}_{key}",
                entry.entry_id,
                base,
            )
            _set_suggested_object_id(sensor, f"{base}_{key}")
            sensors.append(sensor)

    # Replay status sensor
    replay_controller = data.get("replay_controller")
    if replay_controller is not None:
        sensor = F1ReplayStatusSensor(
            replay_controller,
            format_entity_name(base, "replay_status", include_base=False),
            f"{entry.entry_id}_replay_status",
            entry.entry_id,
            base,
        )
        _set_suggested_object_id(sensor, f"{base}_replay_status")
        sensors.append(sensor)

    async_add_entities(sensors, True)


class F1LiveTimingModeSensor(F1AuxEntity, SensorEntity):
    """Diagnostic mode sensor for the live timing transport (idle/live/replay)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "live", "replay"]

    def __init__(self, hass: HomeAssistant, entry_id: str, device_name: str) -> None:
        super().__init__(
            name=format_entity_name(
                device_name, "live_timing_mode", include_base=False
            ),
            unique_id=f"{entry_id}_live_timing_mode",
            entry_id=entry_id,
            device_name=device_name,
        )
        self._attr_suggested_object_id = f"{device_name}_live_timing_mode"
        self.hass = hass
        self._entry_id = entry_id
        self._unsub_live_state = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
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
        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
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
        data = self.coordinator.data
        if not data:
            return None
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        _, race = get_next_race(
            races,
            grace=RACE_SWITCH_GRACE,
            default_time=default_time,
        )
        return race


class _PointsProgressionBase(F1BaseEntity, RestoreEntity, SensorEntity):
    """Base for points progression sensors with shared setup/refresh logic."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            sprint_coord = reg.get("sprint_results_coordinator")
            if sprint_coord and isinstance(sprint_coord.data, dict):
                return (
                    sprint_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []


class _CoordinatorStreamSensorBase(F1BaseEntity, SensorEntity):
    """Base class for coordinator-driven live sensors with change detection."""

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        updated = self._update_from_coordinator()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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
        self._safe_write_ha_state()

    def _update_from_coordinator(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class _ChampionshipPredictionBase(F1BaseEntity, RestoreEntity, SensorEntity):
    """Base for championship prediction sensors with shared restore logic."""

    _DEFAULT_ICON = "mdi:trophy"

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()

    def _apply_payload(
        self, payload: dict, *, force: bool = False
    ) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}


class F1NextRaceSensor(_NextRaceMixin, F1BaseEntity, SensorEntity):
    """Sensor that returns date/time (ISO8601) for the next race in 'state'."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def state(self):
        next_race = self._get_next_race()
        if not next_race:
            return None
        return _combine_date_time(
            next_race.get("date"), next_race.get("time"), force_utc=True
        )

    @property
    def extra_state_attributes(self):
        race = self._get_next_race()
        if not race:
            return {}

        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = _timezone_from_location(loc.get("lat"), loc.get("long"))

        first_practice = race.get("FirstPractice", {})
        second_practice = race.get("SecondPractice", {})
        third_practice = race.get("ThirdPractice", {})
        qualifying = race.get("Qualifying", {})
        sprint_qualifying = race.get("SprintQualifying", {})
        sprint = race.get("Sprint", {})

        race_start = _combine_date_time(
            race.get("date"), race.get("time"), force_utc=True
        )
        first_start = _combine_date_time(
            first_practice.get("date"), first_practice.get("time"), force_utc=True
        )
        second_start = _combine_date_time(
            second_practice.get("date"), second_practice.get("time"), force_utc=True
        )
        third_start = _combine_date_time(
            third_practice.get("date"), third_practice.get("time"), force_utc=True
        )
        qual_start = _combine_date_time(
            qualifying.get("date"), qualifying.get("time"), force_utc=True
        )
        sprint_quali_start = _combine_date_time(
            sprint_qualifying.get("date"), sprint_qualifying.get("time"), force_utc=True
        )
        sprint_start = _combine_date_time(
            sprint.get("date"), sprint.get("time"), force_utc=True
        )

        attrs = {
            "season": race.get("season"),
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "race_url": race.get("url"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "circuit_lat": loc.get("lat"),
            "circuit_long": loc.get("long"),
            "circuit_locality": loc.get("locality"),
            "circuit_country": loc.get("country"),
            "country_code": get_country_code(loc.get("country")),
            "country_flag_url": get_country_flag_url(loc.get("country")),
            "circuit_map_url": get_circuit_map_url(circuit.get("circuitId")),
            "circuit_timezone": timezone,
        }

        def _populate(label, iso_value):
            attrs[f"{label}_utc"] = iso_value
            attrs[label] = _to_home(self.hass, iso_value)
            attrs[f"{label}_local"] = _to_local(iso_value, timezone)

        _populate("race_start", race_start)
        _populate("first_practice_start", first_start)
        _populate("second_practice_start", second_start)
        _populate("third_practice_start", third_start)
        _populate("qualifying_start", qual_start)
        _populate("sprint_qualifying_start", sprint_quali_start)
        _populate("sprint_start", sprint_start)

        return attrs


class F1TrackTimeSensor(_NextRaceMixin, F1BaseEntity, SensorEntity):
    """Sensor showing current local time at the circuit."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:clock-outline"
        self._unsub_timer = None

    def _get_circuit_timezone(self, race):
        if not race:
            return None
        loc = race.get("Circuit", {}).get("Location", {})
        return _timezone_from_location(loc.get("lat"), loc.get("long"))

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
        race = self._get_next_race()
        tz_name = self._get_circuit_timezone(race)
        if not tz_name:
            return None
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_track = now_utc.astimezone(ZoneInfo(tz_name))
        return now_track.strftime("%H:%M")

    @property
    def extra_state_attributes(self):
        race = self._get_next_race()
        if not race:
            return {}
        tz_name = self._get_circuit_timezone(race)
        if not tz_name:
            return {}

        circuit = race.get("Circuit", {})
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_track = now_utc.astimezone(ZoneInfo(tz_name))

        home_tz_name = getattr(self.hass.config, "time_zone", None)
        offset_from_home = None
        if home_tz_name:
            now_home = now_utc.astimezone(ZoneInfo(home_tz_name))
            diff_seconds = (
                now_track.utcoffset() - now_home.utcoffset()
            ).total_seconds()
            diff_hours = diff_seconds / 3600
            offset_from_home = f"{diff_hours:+.1f}h"

        return {
            "timezone": tz_name,
            "utc_offset": now_track.strftime("%z"),
            "offset_from_home": offset_from_home,
            "circuit_name": circuit.get("circuitName"),
            "circuit_locality": circuit.get("Location", {}).get("locality"),
            "circuit_country": circuit.get("Location", {}).get("country"),
        }


class F1CurrentSeasonSensor(F1BaseEntity, SensorEntity):
    """Sensor showing number of races this season."""

    _unrecorded_attributes = frozenset({"races"})

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-month"

    @property
    def state(self):
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return len(races)

    @property
    def extra_state_attributes(self):
        table = (self.coordinator.data or {}).get("MRData", {}).get("RaceTable", {})
        races = table.get("Races", [])

        enriched_races = []
        for race in races:
            enriched = dict(race)
            circuit = race.get("Circuit", {})
            country = circuit.get("Location", {}).get("country")
            enriched["country_code"] = get_country_code(country)
            enriched["country_flag_url"] = get_country_flag_url(country)
            enriched["circuit_map_url"] = get_circuit_map_url(circuit.get("circuitId"))
            enriched_races.append(enriched)

        return {"season": table.get("season"), "races": enriched_races}


class F1DriverStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for driver standings."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple-check"

    @property
    def state(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        return len(lists[0].get("DriverStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not lists:
            return {}
        first = lists[0]
        return {
            "season": first.get("season"),
            "round": first.get("round"),
            "driver_standings": first.get("DriverStandings", []),
        }


class F1ConstructorStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for constructor standings."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:factory"

    @property
    def state(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        return len(lists[0].get("ConstructorStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not lists:
            return {}
        first = lists[0]
        return {
            "season": first.get("season"),
            "round": first.get("round"),
            "constructor_standings": first.get("ConstructorStandings", []),
        }


class F1WeatherSensor(_NextRaceMixin, F1BaseEntity, SensorEntity):
    """Sensor for current and race-start weather."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:weather-partly-cloudy"
        self._current = {}
        self._race = {}
        self._circuit = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(
            lambda: self.hass.async_create_task(self._update_weather())
        )
        self.async_on_remove(removal)
        await self._update_weather()

    async def _update_weather(self):
        race = self._get_next_race()
        # Store which circuit this weather is for, so the UI can show context even
        # when only temperature is used as the sensor state.
        if race:
            circuit = race.get("Circuit", {}) or {}
            loc = circuit.get("Location", {}) or {}
            self._circuit = {
                "season": race.get("season"),
                "round": race.get("round"),
                "race_name": race.get("raceName"),
                "race_url": race.get("url"),
                "circuit_id": circuit.get("circuitId"),
                "circuit_name": circuit.get("circuitName"),
                "circuit_url": circuit.get("url"),
                "circuit_lat": loc.get("lat"),
                "circuit_long": loc.get("long"),
                "circuit_locality": loc.get("locality"),
                "circuit_country": loc.get("country"),
            }
        else:
            self._circuit = {}
        loc = race.get("Circuit", {}).get("Location", {}) if race else {}
        lat, lon = loc.get("lat"), loc.get("long")
        if lat is None or lon is None:
            return
        session = async_get_clientsession(self.hass)
        current_vars = ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "precipitation_probability",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "visibility",
                "weather_code",
            ]
        )
        hourly_vars = current_vars
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current={current_vars}"
            f"&hourly={hourly_vars}"
            f"&wind_speed_unit=ms"
            f"&timezone=UTC"
            f"&forecast_days=16"
        )
        try:
            async with async_timeout.timeout(10):
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception:
            # Avoid showing stale weather when a refresh fails.
            self._current = {}
            self._race = {}
            self._attr_icon = "mdi:weather-partly-cloudy"
            self.async_write_ha_state()
            return

        # Parse current conditions from the dedicated current block.
        current_block = data.get("current", {})
        self._current = self._extract(current_block)
        current_code = current_block.get("weather_code")
        self._attr_icon = WMO_CODE_TO_MDI.get(current_code, "mdi:weather-partly-cloudy")

        # Build an index over the hourly time series for race-start lookup.
        hourly = data.get("hourly", {})
        hourly_times = hourly.get("time", [])
        hourly_vars_keys = [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "precipitation_probability",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "visibility",
            "weather_code",
        ]
        hourly_entries = []
        for i, t in enumerate(hourly_times):
            entry = {"time": t}
            for key in hourly_vars_keys:
                vals = hourly.get(key, [])
                entry[key] = vals[i] if i < len(vals) else None
            hourly_entries.append(entry)

        start_iso = (
            _combine_date_time(race.get("date"), race.get("time")) if race else None
        )
        self._race = {k: None for k in self._current}
        if start_iso and hourly_entries:
            start_dt = datetime.datetime.fromisoformat(start_iso)
            # Ensure start_dt is UTC-aware for comparison.
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=datetime.timezone.utc)
            closest = min(
                hourly_entries,
                key=lambda e: abs(
                    datetime.datetime.fromisoformat(e["time"]).replace(
                        tzinfo=datetime.timezone.utc
                    )
                    - start_dt
                ),
            )
            self._race = self._extract(closest)
            race_code = closest.get("weather_code")
            race_icon = WMO_CODE_TO_MDI.get(race_code, self._attr_icon)
            self._race["weather_icon"] = race_icon
        self.async_write_ha_state()

    def _extract(self, d):
        wd = d.get("wind_direction_10m")
        precip = d.get("precipitation", 0) or 0
        return {
            "temperature": d.get("temperature_2m"),
            "temperature_unit": "celsius",
            "humidity": d.get("relative_humidity_2m"),
            "humidity_unit": "%",
            "cloud_cover": d.get("cloud_cover"),
            "cloud_cover_unit": "%",
            "precipitation": precip,
            # open-meteo gives an exact forecast value, not a range; expose the
            # same value for min/max to preserve backwards compatibility.
            "precipitation_amount_min": precip,
            "precipitation_amount_max": precip,
            "precipitation_probability": d.get("precipitation_probability"),
            "precipitation_probability_unit": "%",
            "precipitation_unit": "mm",
            "wind_speed": d.get("wind_speed_10m"),
            "wind_speed_unit": "m/s",
            "wind_direction": self._abbr(wd),
            "wind_from_direction_degrees": wd,
            "wind_from_direction_unit": "degrees",
            "wind_gusts": d.get("wind_gusts_10m"),
            "wind_gusts_unit": "m/s",
            "visibility": d.get("visibility"),
            "visibility_unit": "m",
            "weather_code": d.get("weather_code"),
            "weather_source": "open-meteo",
        }

    def _abbr(self, deg):
        if deg is None:
            return None
        dirs = [
            (i * 22.5, d)
            for i, d in enumerate(
                [
                    "N",
                    "NNE",
                    "NE",
                    "ENE",
                    "E",
                    "ESE",
                    "SE",
                    "SSE",
                    "S",
                    "SSW",
                    "SW",
                    "WSW",
                    "W",
                    "WNW",
                    "NW",
                    "NNW",
                    "N",
                ]
            )
        ]
        return min(dirs, key=lambda x: abs(deg - x[0]))[1]

    @property
    def state(self):
        return self._current.get("temperature")

    @property
    def extra_state_attributes(self):
        attrs = dict(self._circuit or {})
        attrs.update({f"current_{k}": v for k, v in self._current.items()})
        attrs.update({f"race_{k}": v for k, v in self._race.items()})
        return attrs


class F1LastRaceSensor(F1BaseEntity, SensorEntity):
    """Sensor for results of the latest race."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:trophy"

    @property
    def state(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        if not races:
            return None
        results = races[0].get("Results", [])
        winner = next((r for r in results if r.get("positionText") == "1"), None)
        return winner.get("Driver", {}).get("familyName") if winner else None

    @property
    def extra_state_attributes(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        if not races:
            return {}
        race = races[0]

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
                "points": r.get("points"),
                "status": r.get("status"),
                "driver": {
                    "permanentNumber": r.get("Driver", {}).get("permanentNumber"),
                    "code": r.get("Driver", {}).get("code"),
                    "givenName": r.get("Driver", {}).get("givenName"),
                    "familyName": r.get("Driver", {}).get("familyName"),
                },
                "constructor": {
                    "constructorId": r.get("Constructor", {}).get("constructorId"),
                    "name": r.get("Constructor", {}).get("name"),
                },
            }

        results = [_clean_result(r) for r in race.get("Results", [])]
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = _timezone_from_location(loc.get("lat"), loc.get("long"))
        race_start = _combine_date_time(
            race.get("date"), race.get("time"), force_utc=True
        )
        attrs = {
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "race_url": race.get("url"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "circuit_lat": loc.get("lat"),
            "circuit_long": loc.get("long"),
            "circuit_locality": loc.get("locality"),
            "circuit_country": loc.get("country"),
            "circuit_timezone": timezone,
            "results": results,
        }
        attrs["race_start_utc"] = race_start
        attrs["race_start"] = _to_home(self.hass, race_start)
        attrs["race_start_local"] = _to_local(race_start, timezone)
        return attrs


class F1SeasonResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor for full season results."""

    _unrecorded_attributes = frozenset({"races"})

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:podium"

    @property
    def state(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        return len(races)

    @property
    def extra_state_attributes(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
                "points": r.get("points"),
                "status": r.get("status"),
                "driver": {
                    "permanentNumber": r.get("Driver", {}).get("permanentNumber"),
                    "code": r.get("Driver", {}).get("code"),
                    "givenName": r.get("Driver", {}).get("givenName"),
                    "familyName": r.get("Driver", {}).get("familyName"),
                },
                "constructor": {
                    "constructorId": r.get("Constructor", {}).get("constructorId"),
                    "name": r.get("Constructor", {}).get("name"),
                },
            }

        cleaned = []
        for race in races:
            results = [_clean_result(r) for r in race.get("Results", [])]
            cleaned.append(
                {
                    "round": race.get("round"),
                    "race_name": race.get("raceName"),
                    "results": results,
                }
            )
        return {"races": cleaned}


class F1SprintResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor exposing sprint results across the current season."""

    _unrecorded_attributes = frozenset({"races"})

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-variant"

    def _get_races(self):
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return races or []

    @staticmethod
    def _clean_result(result: dict) -> dict:
        driver = result.get("Driver", {}) or {}
        constructor = result.get("Constructor", {}) or {}
        return {
            "number": result.get("number"),
            "position": result.get("position"),
            "points": result.get("points"),
            "status": result.get("status"),
            "driver": {
                "permanentNumber": driver.get("permanentNumber"),
                "code": driver.get("code"),
                "givenName": driver.get("givenName"),
                "familyName": driver.get("familyName"),
            },
            "constructor": {
                "name": constructor.get("name"),
            },
        }

    @property
    def state(self):
        races = self._get_races()
        if not races:
            return 0
        # Only count sprint weekends that actually include sprint results
        return sum(1 for race in races if race.get("SprintResults"))

    @property
    def extra_state_attributes(self):
        races = self._get_races()
        cleaned = []
        for race in races:
            sprint_results = race.get("SprintResults") or []
            sprint_payload = [self._clean_result(result) for result in sprint_results]
            cleaned.append(
                {
                    "round": race.get("round"),
                    "race_name": race.get("raceName"),
                    "results": sprint_payload,
                }
            )
        return {"races": cleaned}


class F1FiaDocumentsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor that tracks FIA decision documents per race weekend."""

    _DOC1_RESET_PATTERN = re.compile(
        r"\bdoc(?:ument)?(?:\s+(?:no\.?|number))?\s*0*1\b",
        re.IGNORECASE,
    )
    _DOC_NUMBER_RE = re.compile(
        r"\bdoc(?:ument)?(?:\s+(?:no\.?|number))?\s*0*(\d+)\b",
        re.IGNORECASE,
    )

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:file-document-alert"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"documents": []}
        self._documents: list[dict] = []
        self._seen_urls: set[str] = set()
        self._event_key: str | None = None

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
        self._sort_documents()

        latest = (
            self._select_latest_document(self._documents) if self._documents else None
        )
        self._attr_native_value = (
            self._extract_doc_number(latest.get("name")) if latest else 0
        )
        self._attr_extra_state_attributes = self._build_latest_attributes(latest)

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
        data = self.coordinator.data or {}
        updated = False
        event_key = data.get("event_key")
        documents = (
            data.get("documents") if isinstance(data.get("documents"), list) else []
        )

        if isinstance(event_key, str) and event_key and event_key != self._event_key:
            self._event_key = event_key
            self._documents = []
            self._seen_urls = set()
            updated = True

        # Process documents from oldest to newest so that "Doc 1" for the
        # current event is handled before later documents. This ensures that
        # the final reset triggered by a new Document 1 corresponds to the
        # latest race weekend instead of wiping out its newer docs.
        for doc in reversed(documents):
            if not isinstance(doc, dict):
                continue
            url = str(doc.get("url") or "").strip()
            if not url:
                continue
            is_new = url not in self._seen_urls
            if is_new and self._should_reset_for_doc(doc):
                if self._documents or self._seen_urls:
                    self._documents = []
                    self._seen_urls = set()
                    updated = True
            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)
            self._documents.append(doc)
            updated = True

        # Keep bounded attribute size
        if len(self._documents) > 100:
            excess = len(self._documents) - 100
            for _ in range(excess):
                removed = self._documents.pop(0)
                url = str(removed.get("url") or "").strip()
                if url in self._seen_urls:
                    self._seen_urls.remove(url)
            updated = True

        self._sort_documents()

        latest = (
            self._select_latest_document(self._documents) if self._documents else None
        )
        new_state = self._extract_doc_number(latest.get("name")) if latest else 0
        attrs = self._build_latest_attributes(latest)

        if (
            force
            or new_state != self._attr_native_value
            or attrs != self._attr_extra_state_attributes
        ):
            self._attr_native_value = new_state
            self._attr_extra_state_attributes = attrs
            updated = True

        return updated

    @classmethod
    def _should_reset_for_doc(cls, doc: dict) -> bool:
        """Return True when a newly-seen doc indicates a fresh race weekend (Document 1)."""
        name = doc.get("name")
        if not isinstance(name, str):
            return False
        normalized = " ".join(name.split())
        if not normalized:
            return False
        return bool(cls._DOC1_RESET_PATTERN.search(normalized))

    @staticmethod
    def _published_timestamp(doc: dict) -> float | None:
        published = doc.get("published")
        if not isinstance(published, str) or not published:
            return None
        try:
            dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.timestamp()
        except Exception:
            return None

    def _sort_documents(self) -> None:
        if not self._documents:
            return
        indexed = list(enumerate(self._documents))

        def sort_key(item):
            idx, doc = item
            ts = self._published_timestamp(doc)
            return (0 if ts is not None else 1, ts if ts is not None else 0.0, idx)

        indexed.sort(key=sort_key)
        self._documents = [doc for _, doc in indexed]

    @classmethod
    def _extract_doc_number(cls, name: str | None) -> int:
        """Extract the document number from a FIA document name like 'Doc 27 - ...'."""
        if not isinstance(name, str) or not name:
            return 0
        match = cls._DOC_NUMBER_RE.search(name)
        if not match:
            return 0
        try:
            return int(match.group(1))
        except Exception:
            return 0

    @classmethod
    def _select_latest_document(cls, docs: list[dict]) -> dict | None:
        """Select the latest document, preferring highest document number, then most recent published time.

        In practice the FIA HTML is not always consistent about the "Published on"
        metadata, but the document number monotonically increases for a given
        event. Using the doc number as the primary key guarantees that we do not
        regress from e.g. Doc 56 back to Doc 1 when some links lack a published
        timestamp or use an unparseable format.
        """
        if not isinstance(docs, list) or not docs:
            return None
        best_doc: dict | None = None
        best_num: int = -1
        best_ts: float | None = None
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            num = cls._extract_doc_number(doc.get("name"))
            ts = cls._published_timestamp(doc)
            # Primary key: highest document number
            if num > best_num:
                best_doc = doc
                best_num = num
                best_ts = ts
                continue
            if num < best_num:
                continue
            # Same document number: use newest publish timestamp when available
            if ts is not None and (best_ts is None or ts > best_ts):
                best_doc = doc
                best_ts = ts
        # Fallback: if we never selected anything (e.g. all names invalid), return the last doc
        return best_doc or docs[-1]

    @classmethod
    def _build_latest_attributes(cls, latest: dict | None) -> dict:
        """Build attributes for the latest document only."""
        if not isinstance(latest, dict) or not latest:
            return {}
        return {
            "name": latest.get("name"),
            "url": latest.get("url"),
            "published": latest.get("published"),
        }


class F1DriverPointsProgressionSensor(_PointsProgressionBase):
    """Sensor that exposes per-round and cumulative points per driver, including sprint points.

    - State: number of rounds included.
    - Attributes: season, rounds[], drivers{}, series{} for charting.
    """

    _unrecorded_attributes = frozenset({"drivers", "series"})

    def _get_full_schedule(self) -> list:
        """Return full season schedule (all planned rounds) from race_coordinator if available."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            race_coord = reg.get("race_coordinator")
            if race_coord and isinstance(race_coord.data, dict):
                return (
                    race_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []

    def _get_driver_standings(self) -> tuple[dict, int | None]:
        """Return (points_by_code, standings_round) from driver standings coordinator."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            coord = reg.get("driver_coordinator")
            points_map: dict[str, float] = {}
            round_num: int | None = None
            if coord and isinstance(coord.data, dict):
                lists = (
                    coord.data.get("MRData", {})
                    .get("StandingsTable", {})
                    .get("StandingsLists", [])
                )
                if lists:
                    try:
                        round_num = (
                            int(str(lists[0].get("round") or 0))
                            if str(lists[0].get("round") or "").isdigit()
                            else None
                        )
                    except Exception:
                        round_num = None
                    for item in lists[0].get("DriverStandings", []) or []:
                        drv = item.get("Driver", {}) or {}
                        code = drv.get("code") or drv.get("driverId")
                        if not code:
                            continue
                        try:
                            points_map[code] = float(str(item.get("points") or 0))
                        except Exception:
                            points_map[code] = 0.0
            return points_map, round_num
        except Exception:
            return {}, None

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        season = None
        rounds_meta = []
        # Build base per-round points from race Results
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        name_map: dict[str, dict] = {}
        round_numbers: list[int] = []
        for race in races:
            season = season or race.get("season")
            rnd = (
                int(str(race.get("round") or 0))
                if str(race.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append(
                {
                    "round": rnd,
                    "race_name": race.get("raceName"),
                    "date": _combine_date_time(race.get("date"), race.get("time")),
                }
            )
            # Prepare default 0 entries first
            # We'll fill driver points dynamically as we encounter drivers
            results = race.get("Results", []) or []
            # Determine winner code for wins array
            winner_code = None
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                if res.get("position") == "1" or res.get("positionText") == "1":
                    winner_code = code
                name_map.setdefault(
                    code,
                    {
                        "code": drv.get("code") or None,
                        "driverId": drv.get("driverId"),
                        "name": f"{drv.get('givenName', '')} {drv.get('familyName', '')}".strip()
                        or drv.get("familyName"),
                    },
                )
                # Ensure lists are sized to rnd index (append later)
            # Assign race points
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = _to_float_value(res.get("points"))
                per_round_points.setdefault(code, [])
                wins_per_round.setdefault(code, [])
                per_round_points[code].append(pts)
                wins_per_round[code].append(1 if code == winner_code else 0)
            # Normalize length for drivers missing this round
            max_len = len(round_numbers)
            for code in list(per_round_points.keys()):
                while len(per_round_points[code]) < max_len:
                    per_round_points[code].append(0.0)
                while len(wins_per_round[code]) < max_len:
                    wins_per_round[code].append(0)

        # Merge sprint points (by round)
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = (
                int(str(sp.get("round") or 0))
                if str(sp.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            if rnd not in round_index:
                # Lägg till sprint-rond som ännu ej har kört huvudlopp
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append(
                    {
                        "round": rnd,
                        "race_name": sp.get("raceName"),
                        "date": _combine_date_time(sp.get("date"), sp.get("time")),
                    }
                )
                for code in list(per_round_points.keys()):
                    per_round_points[code].append(0.0)
                for code in list(wins_per_round.keys()):
                    wins_per_round[code].append(None)
            idx = round_index[rnd]
            results = sp.get("SprintResults") or sp.get("Results") or []
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = _to_float_value(res.get("points"))
                per_round_points.setdefault(code, [0.0] * len(round_numbers))
                wins_per_round.setdefault(code, [None] * len(round_numbers))
                # Add sprint points to the same round
                with suppress(Exception):
                    per_round_points[code][idx] += pts
        # Align totals with latest standings if they refer to a newer round
        with suppress(Exception):
            standings_map, standings_round = self._get_driver_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                # If standings reference a newer round, create it
                if standings_round and (
                    max_round is None or standings_round > max_round
                ):
                    round_numbers.append(standings_round)
                    rounds_meta.append(
                        {
                            "round": standings_round,
                            "race_name": None,
                            "date": None,
                        }
                    )
                    # pad existing arrays
                    for code in list(per_round_points.keys()):
                        per_round_points[code].append(0.0)
                    for code in list(wins_per_round.keys()):
                        wins_per_round[code].append(None)
                # Compute and apply deltas
                for code, total_pts in standings_map.items():
                    pts_list = per_round_points.get(code)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        with suppress(Exception):
                            computed_total += float(v or 0.0)
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        # Apply delta to last available round (new one if created)
                        per_round_points[code][-1] = (
                            per_round_points[code][-1] or 0.0
                        ) + delta
        # Återställ: visa endast körda ronder (som vi redan byggt från resultat)

        # Bygg cumulative och totals samt series
        drivers_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for code, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                if p is None:
                    cum.append(None)
                else:
                    total += float(p or 0.0)
                    cum.append(total)
            wins = wins_per_round.get(code, [0] * len(pts_list))
            # Sanitize None -> 0 for totals
            safe_wins = [
                int(w) if isinstance(w, int) else (1 if w is True else 0) for w in wins
            ]
            info = name_map.get(code, {})
            drivers_attr[code] = {
                "identity": {
                    "code": info.get("code") or (code if len(code) <= 3 else None),
                    "driverId": info.get("driverId"),
                    "name": info.get("name"),
                },
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append(
                {
                    "key": info.get("code") or code,
                    "name": info.get("name") or code,
                    "data": cum,
                }
            )

        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "drivers": drivers_attr,
            "series": series,
        }


class F1ConstructorPointsProgressionSensor(_PointsProgressionBase):
    """Constructor points per team by round, including sprint; cumulative series for charts."""

    _unrecorded_attributes = frozenset({"constructors", "series"})

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        season = None
        rounds_meta = []
        round_numbers: list[int] = []

        # Per round team points and wins
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        team_info: dict[str, dict] = {}  # constructorId -> {name}

        for race in races:
            season = season or race.get("season")
            rnd = (
                int(str(race.get("round") or 0))
                if str(race.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append(
                {
                    "round": rnd,
                    "race_name": race.get("raceName"),
                    "date": _combine_date_time(race.get("date"), race.get("time")),
                }
            )

            # Aggregate points by constructor this round
            results = race.get("Results", []) or []
            # Identify winning constructor (winner driver position 1)
            winning_constructor = None
            for res in results:
                if str(res.get("position") or res.get("positionText")) == "1":
                    c = (res.get("Constructor") or {}).get("constructorId")
                    winning_constructor = c
                    break
            # Sum per constructor
            per_round_sum: dict[str, float] = {}
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(
                    cid,
                    {
                        "constructorId": cons.get("constructorId"),
                        "name": cons.get("name"),
                    },
                )
                per_round_sum[cid] = per_round_sum.get(cid, 0.0) + _to_float_value(
                    res.get("points")
                )

            # Append to arrays
            for cid, pts in per_round_sum.items():
                per_round_points.setdefault(cid, [])
                wins_per_round.setdefault(cid, [])
                per_round_points[cid].append(pts)
                wins_per_round[cid].append(1 if cid == winning_constructor else 0)
            # Normalize length for teams not present in this round
            max_len = len(round_numbers)
            for cid in list(per_round_points.keys()):
                while len(per_round_points[cid]) < max_len:
                    per_round_points[cid].append(0.0)
                while len(wins_per_round[cid]) < max_len:
                    wins_per_round[cid].append(0)

        # Merge sprint points
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = (
                int(str(sp.get("round") or 0))
                if str(sp.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            if rnd not in round_index:
                # Lägg till sprint-rond även om huvudlopp saknas
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append(
                    {
                        "round": rnd,
                        "race_name": sp.get("raceName"),
                        "date": _combine_date_time(sp.get("date"), sp.get("time")),
                    }
                )
                for cid in list(per_round_points.keys()):
                    per_round_points[cid].append(0.0)
                for cid in list(wins_per_round.keys()):
                    wins_per_round[cid].append(None)
            idx = round_index[rnd]
            results = sp.get("SprintResults") or sp.get("Results") or []
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(
                    cid,
                    {
                        "constructorId": cons.get("constructorId"),
                        "name": cons.get("name"),
                    },
                )
                per_round_points.setdefault(cid, [0.0] * len(round_numbers))
                wins_per_round.setdefault(cid, [None] * len(round_numbers))
                with suppress(Exception):
                    per_round_points[cid][idx] += _to_float_value(res.get("points"))
        # Synka totals med senaste Constructor Standings
        with suppress(Exception):
            standings_map, standings_round = self._get_constructor_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                if standings_round and (
                    max_round is None or standings_round > max_round
                ):
                    round_numbers.append(standings_round)
                    rounds_meta.append(
                        {
                            "round": standings_round,
                            "race_name": None,
                            "date": None,
                        }
                    )
                    for cid in list(per_round_points.keys()):
                        per_round_points[cid].append(0.0)
                    for cid in list(wins_per_round.keys()):
                        wins_per_round[cid].append(None)
                for cid, total_pts in standings_map.items():
                    pts_list = per_round_points.get(cid)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        with suppress(Exception):
                            computed_total += float(v or 0.0)
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        per_round_points[cid][-1] = (
                            per_round_points[cid][-1] or 0.0
                        ) + delta
        # Build cumulative and series
        teams_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for cid, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                total += float(p or 0.0)
                cum.append(total)
            wins = wins_per_round.get(cid, [0] * len(pts_list))
            safe_wins = [
                int(w) if isinstance(w, int) else (1 if w is True else 0) for w in wins
            ]
            info = team_info.get(cid, {"name": cid})
            teams_attr[cid] = {
                "identity": {
                    "constructorId": info.get("constructorId"),
                    "name": info.get("name"),
                },
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append(
                {
                    "key": info.get("constructorId") or cid,
                    "name": info.get("name") or cid,
                    "data": cum,
                }
            )

        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "constructors": teams_attr,
            "series": series,
        }

    def _get_constructor_standings(self) -> tuple[dict, int | None]:
        """Return (points_by_constructorId, standings_round) from constructor standings coordinator."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            coord = reg.get("constructor_coordinator")
            points_map: dict[str, float] = {}
            round_num: int | None = None
            if coord and isinstance(coord.data, dict):
                lists = (
                    coord.data.get("MRData", {})
                    .get("StandingsTable", {})
                    .get("StandingsLists", [])
                )
                if lists:
                    try:
                        round_num = (
                            int(str(lists[0].get("round") or 0))
                            if str(lists[0].get("round") or "").isdigit()
                            else None
                        )
                    except Exception:
                        round_num = None
                    for item in lists[0].get("ConstructorStandings", []) or []:
                        cons = item.get("Constructor", {}) or {}
                        cid = cons.get("constructorId") or cons.get("name")
                        if not cid:
                            continue
                        try:
                            points_map[cid] = float(str(item.get("points") or 0))
                        except Exception:
                            points_map[cid] = 0.0
            return points_map, round_num
        except Exception:
            return {}, None


class F1TrackWeatherSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor for live track weather via WeatherData feed.

    State: air temperature (Celsius). Attributes include track temp, humidity, pressure, rainfall,
    wind speed and direction, with units. Restores last value on restart if no live data yet.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
        # No stale timer: we keep last known value until a new payload arrives

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator if available, else restore
        init = self._extract_current()
        updated = init is not None
        if init is not None:
            self._apply_payload(init)
            with suppress(Exception):
                getLogger(__name__).debug(
                    "TrackWeather: Initialized from coordinator: %s", init
                )
        else:
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    # Restore last known state and attributes; do not clear due to age
                    self._attr_native_value = self._to_float(last.state)
                    attrs = dict(getattr(last, "attributes", {}) or {})
                    for k in (
                        "measurement_time",
                        "measurement_age_seconds",
                        "received_at",
                    ):
                        attrs.pop(k, None)
                    self._attr_extra_state_attributes = attrs
                    with suppress(Exception):
                        getLogger(__name__).debug(
                            "TrackWeather: Restored last state: %s", last.state
                        )
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        return

    def _to_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        # Accept direct dict from coordinator
        if isinstance(data, dict) and any(
            k in data for k in ("TrackTemp", "AirTemp", "Humidity")
        ):
            return data
        # Or wrapped inside {"data": {...}}
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            inner = data.get("data")
            if any(k in inner for k in ("TrackTemp", "AirTemp", "Humidity")):
                return inner
        # Fallback: recent history buffer if available
        history = getattr(self.coordinator, "data_list", None)
        if isinstance(history, list) and history:
            last = history[-1]
            if isinstance(last, dict) and any(
                k in last for k in ("TrackTemp", "AirTemp", "Humidity")
            ):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        # Parse and set state and attributes
        track_temp = self._to_float(raw.get("TrackTemp"))
        air_temp = self._to_float(raw.get("AirTemp"))
        humidity = self._to_float(raw.get("Humidity"))
        pressure = self._to_float(raw.get("Pressure"))
        rainfall = self._to_float(raw.get("Rainfall"))
        wind_dir = self._to_float(raw.get("WindDirection"))
        wind_speed = self._to_float(raw.get("WindSpeed"))

        # Try to extract a timestamp from the payload; if absent, infer measurement time as now
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
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                self._last_timestamped_dt = ts
            else:
                # No explicit timestamp; do not assign measurement_time
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

        # No staleness handling: keep last known value until a new payload arrives

    # No stale scheduling required for Track Weather

    # No stale timeout handler

    # Use default attributes storage; do not force placeholders

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        if raw is None:
            # Keep last known values; just log an update
            with suppress(Exception):
                getLogger(__name__).debug(
                    "TrackWeather: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            self._safe_write_ha_state()
            return
        self._apply_payload(raw)
        self._safe_write_ha_state()

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None

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

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_native_value = None
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
        # Prefer coordinator's latest if present, otherwise restore last state
        raw = self._extract_current()
        initial = self._normalize(raw)
        updated = raw is not None
        if initial is not None:
            self._attr_native_value = initial
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
        self.async_write_ha_state()

    def _normalize(self, raw: dict | None) -> str | None:
        return normalize_track_status(raw)

    def _extract_current(self) -> dict | None:
        # Coordinator stores last payload for TrackStatus
        data = self.coordinator.data
        if not data:
            # Fallback: some ws updates may only land in data_list initially
            with suppress(Exception):
                hist = getattr(self.coordinator, "data_list", None)
                if isinstance(hist, list) and hist:
                    last = hist[-1]
                    if isinstance(last, dict):
                        return last
            # Final fallback: integration-level latest cache
            with suppress(Exception):
                cache = self.hass.data.get(LATEST_TRACK_STATUS)
                if isinstance(cache, dict):
                    return cache
            return None
        # Expect either direct dict or wrapper with 'data'
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
        # Return stored value so restored/initialized state is honored until an update arrives
        return self._attr_native_value

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self.async_write_ha_state()
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
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {}

    def _clear_state(self) -> None:
        self._attr_native_value = None


class F1TopThreePositionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live Top Three sensor for a single position (P1, P2 eller P3).

    - State: TLA (t.ex. VER) för vald position när Withheld är False.
    - Attribut: withhold-flagga och fält för just den positionen.
    """

    def __init__(
        self,
        coordinator,
        sensor_name,
        unique_id,
        entry_id,
        device_name,
        position_index: int,
    ):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        # 0-baserat index: 0=P1, 1=P2, 2=P3
        self._position_index = max(0, min(2, int(position_index or 0)))
        # Enkelt ikonval; P1 kan få "full" trophy
        if self._position_index == 0:
            self._attr_icon = "mdi:trophy"
        else:
            self._attr_icon = "mdi:trophy-outline"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

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
        # Rate-limita skrivningar till max var 5:e sekund
        try:
            import time as _time

            lw = getattr(self, "_last_write_ts", None)
            now = _time.time()
            if lw is None or (now - lw) >= 5.0:
                setattr(self, "_last_write_ts", now)
                self._safe_write_ha_state()
            else:
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    setattr(self, "_pending_write", True)
                    delay = max(0.0, 5.0 - (now - lw)) if lw is not None else 5.0

                    def _do_write(_):
                        try:
                            setattr(self, "_last_write_ts", _time.time())
                            self._safe_write_ha_state()
                        finally:
                            setattr(self, "_pending_write", False)

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

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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
            self.async_write_ha_state()

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

        # Find the most recent grip-related message
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
            self.async_write_ha_state()

    def _map_status(self, raw: dict | None) -> str | None:
        if not raw:
            return None
        # Prefer explicit string in Status, fall back to Message
        message = str(raw.get("Status") or raw.get("Message") or "").strip()
        started_hint = str(raw.get("Started") or "").strip()

        # Stateless mapping based only on this payload.
        if message == "Started":
            return "live"

        if message == "Finished":
            # A qualifying part or the session segment ended.
            # Reset internal memory defensively.
            self._started_flag = None
            return "finished"

        if message == "Finalised":
            # Session finalised without requiring a prior "Finished".
            self._started_flag = None
            return "finalised"

        if message == "Ends":
            # Session officially ends. Clear any sticky state.
            self._started_flag = None
            return "ended"

        if message == "Inactive":
            # Planned qualifying break vs. suspension vs. pre-session
            if started_hint == "Finished":
                # Planned pause between quali segments
                self._started_flag = None
                return "break"
            if started_hint == "Started":
                # Tie-break using latest TrackStatus: if not RED, treat as live
                try:
                    cache = self.hass.data.get(LATEST_TRACK_STATUS)
                    track_state = (
                        normalize_track_status(cache)
                        if isinstance(cache, dict)
                        else None
                    )
                except Exception:
                    track_state = None
                if track_state and track_state != "RED":
                    return "live"
                # Red flag / suspended while session is considered started
                return "suspended"
            # Not started yet
            return "pre"

        if message == "Aborted":
            # Aborted within an already started session is a suspension-like state
            if started_hint == "Started":
                # Tie-break using latest TrackStatus: if not RED, treat as live
                try:
                    cache = self.hass.data.get(LATEST_TRACK_STATUS)
                    track_state = (
                        normalize_track_status(cache)
                        if isinstance(cache, dict)
                        else None
                    )
                except Exception:
                    track_state = None
                if track_state and track_state != "RED":
                    return "live"
                return "suspended"
            # Otherwise treat like pre (no live running yet)
            return "pre"

        # Fallback: unknown values behave like pre-session
        return "pre"

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self.async_write_ha_state()
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
        self.async_write_ha_state()

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


class F1SessionClockBaseSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Base sensor for derived session clock values."""

    _value_key: str = ""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
        if not isinstance(value, int) or value < 0:
            return None
        hours = value // 3600
        minutes = (value % 3600) // 60
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

    def _handle_coordinator_update(self) -> None:
        state = self._extract_state()
        if not isinstance(state, dict):
            return

        value = self._extract_value(state)
        source_quality = str(state.get("source_quality") or "").strip()
        if value is None and source_quality == "unavailable":
            # Keep restored value during startup/reconnect until a useful payload arrives.
            self._safe_write_ha_state()
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
        self._safe_write_ha_state()

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


class F1SessionTimeRemainingSensor(F1SessionClockBaseSensor):
    """Official session time remaining based on ExtrapolatedClock."""

    _value_key = "clock_remaining_s"

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-sand"

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["clock_total_s"] = state.get("clock_total_s")
        return attrs


class F1SessionTimeElapsedSensor(F1SessionClockBaseSensor):
    """Official session elapsed time based on ExtrapolatedClock."""

    _value_key = "clock_elapsed_s"

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-outline"

    def _build_attrs(self, state: dict, value: int | None) -> dict:
        attrs = super()._build_attrs(state, value)
        attrs["clock_total_s"] = state.get("clock_total_s")
        attrs["clock_remaining_s"] = state.get("clock_remaining_s")
        return attrs


class F1RaceTimeToThreeHourLimitSensor(F1SessionClockBaseSensor):
    """Time remaining until the FIA 3-hour race duration cap."""

    _value_key = "race_three_hour_remaining_s"

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car-clock"

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


class F1CurrentSessionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live sensor reporting current session label (e.g., Practice 1, Qualifying/Q1, Sprint Qualifying/SQ1, Sprint, Race).

    - State: compact label string
    - Attributes: full session metadata from SessionInfo (Type, Name, Number, Meeting, Circuit, Start/End),
                  session_part (numeric), resolved_label, and raw payloads; includes live status from SessionStatus if available.
    - Behavior: restores last state on restart; respects global live delay via coordinator.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Wire listeners first so _live_status() reflects current coordinator state
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        # Also listen to SessionStatus so we can clear state when session ends
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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
                    if end_iso:
                        end_dt = datetime.datetime.fromisoformat(
                            str(end_iso).replace("Z", "+00:00")
                        )
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
                        now_utc = datetime.datetime.now(datetime.timezone.utc)
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
        # No dedicated history usage; SessionInfo snapshots have no high-frequency heartbeat like others
        return None

    def _resolve_label(self, info: dict) -> tuple[str | None, dict]:
        t = str(info.get("Type") or "").strip()
        name = str(info.get("Name") or "").strip()
        num = info.get("Number")
        try:
            num_i = int(num) if num is not None else None
        except Exception:
            num_i = None

        # Try detect session part from consolidated drivers coordinator if available
        session_part = None
        try:
            drivers_data = (
                self.hass.data.get(DOMAIN, {})
                .get(self._entry_id, {})
                .get("drivers_coordinator")
            )
            if drivers_data and hasattr(drivers_data, "data"):
                sd = drivers_data.data or {}
                session = sd.get("session") or {}
                session_part = session.get("part")
        except Exception:
            session_part = None

        label = None
        if t == "Practice":
            label = f"Practice {num_i}" if num_i else (name or "Practice")
        elif t == "Qualifying":
            # Aggregate all Q1/Q2/Q3 into "Qualifying"; treat Sprint Shootout as Sprint Qualifying
            nm = name.lower()
            is_sprint_quali = nm.startswith("sprint qualifying") or nm.startswith(
                "sprint shootout"
            )
            label = "Sprint Qualifying" if is_sprint_quali else "Qualifying"
        elif t == "Race":
            # Some events report Sprint/Sprint Qualifying under Type "Race" via Name
            nm = name.lower()
            if nm.startswith("sprint qualifying") or nm.startswith("sprint shootout"):
                label = "Sprint Qualifying"
            elif nm.startswith("sprint"):
                label = "Sprint"
            else:
                label = name or "Race"
        else:
            # Fallback: use Name then Type
            label = name or t or None

        meta = {
            "type": t or None,
            "name": name or None,
            "number": num_i,
            "session_part": session_part,
        }
        return label, meta

    def _live_status(self) -> str | None:
        try:
            if self._status_coordinator and isinstance(
                self._status_coordinator.data, dict
            ):
                d = self._status_coordinator.data
                return str(d.get("Status") or d.get("Message") or "").strip()
        except Exception:
            return None
        return None

    def _apply_payload(self, raw: dict, allow_clear: bool = True) -> None:
        label, meta = self._resolve_label(raw or {})
        status = self._live_status()
        # Treat session as ended by explicit status; only use EndDate as a soft fallback with grace
        ended = str(status or "").strip() in ("Finished", "Finalised", "Ends")
        with suppress(Exception):
            end_iso = raw.get("EndDate")
            if end_iso and not ended:
                end_dt = datetime.datetime.fromisoformat(
                    str(end_iso).replace("Z", "+00:00")
                )
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                # Consider EndDate only if we are well past it and no active/green status is present
                if now_utc >= (end_dt + datetime.timedelta(minutes=5)):
                    st = str(status or "").strip()
                    if st not in ("Started", "Green", "GreenFlag"):
                        ended = True
        active = str(status or "").strip() == "Started"
        desired_state = None
        if label in ("Qualifying", "Sprint Qualifying"):
            desired_state = None if ended else label
        else:
            desired_state = label if active else None
        # On startup we may not yet have live status; avoid clearing to unknown
        if desired_state is None and not allow_clear:
            # Do not substitute the label on startup for ended/inactive sessions; keep prior value only
            desired_state = self._attr_native_value
        self._attr_native_value = desired_state
        attrs = dict(meta)
        # Merge common metadata
        with suppress(Exception):
            meeting = raw.get("Meeting") or {}
            circuit = (
                meeting.get("Circuit") if isinstance(meeting, dict) else None
            ) or {}
            attrs.update(
                {
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
        # Include live status and activity flag
        with suppress(Exception):
            attrs["live_status"] = status
            attrs["active"] = active
            if not active and label:
                attrs["last_label"] = label
        self._attr_extra_state_attributes = attrs
        with suppress(Exception):
            getLogger(__name__).debug(
                "CurrentSession apply: label=%s status=%s ended=%s active=%s",
                label,
                status,
                ended,
                active,
            )

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self.async_write_ha_state()
            return
        if raw is None:
            with suppress(Exception):
                getLogger(__name__).debug(
                    "CurrentSession: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            return
        self._apply_payload(raw)
        self.async_write_ha_state()

    def _handle_status_update(self) -> None:
        # Re-evaluate state based on latest status (may clear on Ends/Finished/Finalised)
        raw = self._extract_current() or {}
        if not self._handle_stream_state(True):
            return
        if not self._is_stream_active():
            self.async_write_ha_state()
            return
        self._apply_payload(raw)
        with suppress(Exception):
            getLogger(__name__).debug(
                "CurrentSession: Status update at %s -> state=%s, live_status=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
                self._live_status(),
            )
        self.async_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}


class F1RaceControlSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Expose the latest Race Control message as an easy-to-use sensor."""

    _history_limit = 5

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
        if event_id and self._last_event_id == event_id and not force:
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
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                utc_str = dt.astimezone(datetime.timezone.utc).isoformat(
                    timespec="seconds"
                )
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

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_event_id = None
        self._history = []
        self._sequence = 0


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

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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

        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
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
        if reason == "init":
            return
        if not is_live:
            self._clear_state()
            self._safe_write_ha_state()

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

        # Check for time/lap deleted
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

        # Check for BLACK AND WHITE flag warning
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

        # Check for penalty
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
        violation = {
            "utc": utc,
            "lap": lap,
            "turn": turn,
            "type": violation_type,
        }

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

    def _handle_coordinator_update(self) -> None:
        messages = getattr(self.coordinator, "data_list", None)
        updated = isinstance(messages, list) and len(messages) > 0

        if not self._handle_stream_state(updated):
            return

        if not self._is_stream_active():
            self._safe_write_ha_state()
            return

        if not isinstance(messages, list):
            return

        # Process any new messages
        changed = False
        for msg in messages:
            if isinstance(msg, dict) and self._process_message(msg):
                changed = True

        if changed:
            self._update_attributes()
            self._safe_write_ha_state()

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
    r"\d+ (?:SECOND )?STOP/?GO PENALTY|REPRIMAND \([^)]+\))\s+"
    r"FOR CAR (\d+) \(([A-Z]{2,3})\)",
    re.IGNORECASE,
)

_PENALTY_SERVED = re.compile(
    r"FIA STEWARDS:\s*PENALTY SERVED",
    re.IGNORECASE,
)

_WILL_BE_INVESTIGATED_AFTER = re.compile(
    r"WILL BE INVESTIGATED AFTER THE RACE",
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

    # NFI decisions expire after this many seconds
    NFI_EXPIRY_SECONDS = 300  # 5 minutes

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-search"
        self._attr_native_value = 0
        # Internal state: keyed by incident key for matching
        self._noted: dict[str, dict] = {}
        self._under_investigation: dict[str, dict] = {}
        self._nfi: dict[str, dict] = {}  # Includes nfi_utc for expiry
        self._penalties: list[dict] = []
        self._processed_ids: set[str] = set()
        self._live_state_unsub = None
        self._session_time: datetime.datetime | None = (
            None  # Track latest message time for NFI expiry
        )
        self._attr_extra_state_attributes = {
            "noted": [],
            "under_investigation": [],
            "no_further_action": [],
            "penalties": [],
            "last_update": None,
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

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
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

        # Signal stream state
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
        self._attr_extra_state_attributes = attrs
        last_update = attrs.get("last_update")
        if last_update:
            with suppress((ValueError, TypeError)):
                parsed = dt_util.parse_datetime(last_update)
                if parsed is not None:
                    self._session_time = parsed

    def _handle_live_state(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        if not is_live:
            self._clear_state()
            self._safe_write_ha_state()

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

        # Skip messages without investigation/penalty keywords
        if not any(
            kw in message_upper
            for kw in [
                "NOTED",
                "INVESTIGATION",
                "PENALTY",
                "REPRIMAND",
                "NO FURTHER",
            ]
        ):
            return False

        # Skip track limits deletions/warnings (handled by TrackLimitsSensor)
        # But process track limits PENALTY and track limits NOTED/INVESTIGATION
        if "TRACK LIMITS" in message_upper:
            if (
                "PENALTY" not in message_upper
                and "INVESTIGATION" not in message_upper
                and "NOTED" not in message_upper
            ):
                return False
            # Skip track limits deletions (TIME DELETED, LAP DELETED)
            if "DELETED" in message_upper:
                return False

        msg_id = self._build_message_id(msg)
        if msg_id in self._processed_ids:
            return False
        self._processed_ids.add(msg_id)

        utc = msg.get("Utc") or msg.get("utc")
        lap = msg.get("Lap")

        # Track session time for NFI expiry (works correctly during replay)
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

        # Check for PENALTY SERVED - remove from penalties list
        if _PENALTY_SERVED.search(message_text):
            if drivers:
                tlas_set = set(driver_tlas)
                self._penalties = [
                    p for p in self._penalties if p.get("driver") not in tlas_set
                ]
            return True

        # Check for penalty issued
        match = _PENALTY_ISSUED.search(message_text)
        if match:
            penalty_text = match.group(1).upper()
            racing_number = match.group(2)
            tla = match.group(3).upper()

            # Remove from noted and under_investigation
            # Use partial match since penalty message only mentions one driver
            # but original incident might have multiple (e.g., BEA/LAW collision)
            key_noted = self._find_incident_containing_driver(tla, self._noted)
            if key_noted:
                del self._noted[key_noted]

            key_inv = self._find_incident_containing_driver(
                tla, self._under_investigation
            )
            if key_inv:
                del self._under_investigation[key_inv]

            # Add to penalties list
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

        # Check for NO FURTHER INVESTIGATION / NO FURTHER ACTION
        if _NO_FURTHER_INVESTIGATION.search(message_text):
            if drivers:
                # Find and move from noted or under_investigation to nfi
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

                # Create NFI entry with expiry timestamp
                nfi_key = self._make_incident_key(driver_tlas, location, reason)
                self._nfi[nfi_key] = {
                    "utc": incident.get("utc") if incident else utc,
                    "lap": incident.get("lap") if incident else lap,
                    "drivers": sorted(driver_tlas),
                    "racing_numbers": racing_numbers,
                    "location": location,
                    "reason": reason,
                    "nfi_utc": utc,  # When NFI was issued, for expiry
                }
            return True

        # Check for UNDER INVESTIGATION
        if _UNDER_INVESTIGATION.search(message_text):
            if drivers:
                # Find in noted and move to under_investigation
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
                # If not found in noted, might be a direct "UNDER INVESTIGATION"
                # (shouldn't happen normally, but handle it)
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

        # Check for WILL BE INVESTIGATED AFTER THE RACE
        if _WILL_BE_INVESTIGATED_AFTER.search(message_text):
            if drivers:
                # Find and move to under_investigation with after_race flag
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
                    # Direct after-race investigation
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

        # Check for UPDATE: INCIDENT NOTED - update existing noted incident
        is_update = message_upper.startswith("UPDATE:")
        if _INCIDENT_NOTED.search(message_text):
            if drivers:
                if is_update:
                    # Find existing incident by drivers and update reason
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
                            "reason": reason,  # Updated reason
                        }
                        return True

                # New NOTED incident
                new_key = self._make_incident_key(driver_tlas, location, reason)
                # Check if already exists (avoid duplicates)
                existing = self._find_incident_by_drivers(driver_tlas, self._noted)
                if existing and reason is None:
                    # Don't overwrite existing with reason-less entry
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
        # Expire old NFI items
        self._expire_nfi_items()

        # State = actionable items count
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
        }

    def _handle_coordinator_update(self) -> None:
        messages = getattr(self.coordinator, "data_list", None)
        updated = isinstance(messages, list) and len(messages) > 0

        if not self._handle_stream_state(updated):
            return

        if not self._is_stream_active():
            self._safe_write_ha_state()
            return

        if not isinstance(messages, list):
            return

        # Process any new messages
        changed = False
        for msg in messages:
            if isinstance(msg, dict) and self._process_message(msg):
                changed = True

        # Check for NFI expiry even if no new messages
        if self._expire_nfi_items():
            changed = True

        if changed:
            self._update_attributes()
            self._safe_write_ha_state()

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
        }


class F1TeamRadioSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor exposing the latest Team Radio clip.

    - State: latest clip UTC timestamp (ISO8601, TIMESTAMP device_class)
    - Attributes: racing_number, path, received_at, sequence, history, raw_message
    """

    _history_limit = 20

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
            if self._is_stream_active():
                last = await self.async_get_last_state()
                if last and last.state not in (None, "unknown", "unavailable"):
                    # Restore last timestamp state as string
                    self._attr_native_value = last.state
                    self._attr_extra_state_attributes = dict(
                        getattr(last, "attributes", {}) or {}
                    )
                    hist = self._attr_extra_state_attributes.get("history")
                    if isinstance(hist, list):
                        self._history = [
                            dict(item)
                            for item in hist[: self._history_limit]
                            if isinstance(item, dict)
                        ]
                    self._last_utc = self._attr_extra_state_attributes.get("utc")
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        # TeamRadioCoordinator exposes {"latest": {...}, "history": [...]}
        if isinstance(data, dict):
            latest = data.get("latest")
            if isinstance(latest, dict):
                return latest
        return None

    def _cleanup_string(self, value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_utc(self, utc_str: str | None) -> str | None:
        text = self._cleanup_string(utc_str)
        if not text:
            return None
        try:
            dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
        except Exception:
            return text

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
        if utc_norm and self._last_utc == utc_norm and not force:
            return

        racing_number = self._cleanup_string(payload.get("RacingNumber"))
        path = self._cleanup_string(payload.get("Path"))
        clip_url = None

        # 1) Försök använda statisk root från replay-dumpen (development-läge)
        static_root = self._cleanup_string(
            payload.get("_static_root") or payload.get("static_root")
        )
        if static_root and path:
            clip_url = f"{static_root.rstrip('/')}/{path.lstrip('/')}"

        # 2) Fallback: bygg URL från LiveSession-window (live-läge)
        if clip_url is None:
            try:
                if self.hass and path:
                    reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
                    live_supervisor = (
                        reg.get("live_supervisor") if isinstance(reg, dict) else None
                    )
                    window = getattr(live_supervisor, "current_window", None)
                    base_path = getattr(window, "path", None)
                    if isinstance(base_path, str) and base_path:
                        # Index.json "Path" can be either:
                        # - "2025/2025-12-07_Abu_Dhabi_Grand_Prix/2025-12-07_Race/"
                        # - "2025-12-07_Abu_Dhabi_Grand_Prix/2025-12-07_Race/"
                        # Ensure we have the year segment when missing so the resulting URL is usable.
                        cleaned_base = base_path.strip("/")
                        year = None
                        try:
                            if isinstance(reg, dict):
                                session_coord = reg.get("session_coordinator")
                                year = getattr(session_coord, "year", None)
                        except Exception:
                            year = None
                        try:
                            if cleaned_base and not re.match(
                                r"^\d{4}/", f"{cleaned_base}/"
                            ):
                                if year and str(year).isdigit():
                                    cleaned_base = f"{int(year)}/{cleaned_base}"
                        except Exception:
                            # Keep best-effort base if regex/year parsing fails
                            cleaned_base = base_path.strip("/")
                        root = f"{STATIC_BASE}/{cleaned_base}"
                        clip_url = f"{root}/{path.lstrip('/')}"
            except Exception:
                clip_url = None

        received_at = dt_util.utcnow().isoformat(timespec="seconds")

        self._sequence += 1

        attrs = {
            "utc": utc_norm,
            "received_at": received_at,
            "racing_number": racing_number,
            "path": path,
            "clip_url": clip_url,
            "sequence": self._sequence,
            "raw_message": payload,
        }

        history_entry = {
            "utc": utc_norm,
            "racing_number": racing_number,
            "path": path,
            "clip_url": clip_url,
        }
        self._history.insert(0, history_entry)
        self._history = self._history[: self._history_limit]
        attrs["history"] = [dict(item) for item in self._history]

        self._attr_native_value = utc_norm
        self._attr_extra_state_attributes = attrs
        self._last_utc = utc_norm

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._history = []
        self._sequence = 0
        self._last_utc = None


class F1PitStopsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live pit stops for all cars (aggregated).

    - State: total pit stops (int)
    - Attributes: cars (dict keyed by racing number), last_update
    """

    _unrecorded_attributes = frozenset({"cars"})

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car-wrench"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"cars": {}, "last_update": None}
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

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
            else:
                self._clear_state()
        self._handle_stream_state(updated)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        total = payload.get("total_stops")
        cars = payload.get("cars")
        last_update = payload.get("last_update")

        try:
            total_int = int(total) if total is not None else 0
        except Exception:
            try:
                total_int = int(float(str(total)))
            except Exception:
                total_int = 0

        # Avoid unnecessary writes
        if (not force) and self._attr_native_value == total_int:
            with suppress(Exception):
                prev_cars = (self._attr_extra_state_attributes or {}).get("cars")
                if prev_cars == cars:
                    return
        self._attr_native_value = total_int
        self._attr_extra_state_attributes = {
            "cars": cars if isinstance(cars, dict) else {},
            "last_update": last_update,
        }

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        updated = payload is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        if payload is None:
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"cars": {}, "last_update": None}


class F1ChampionshipPredictionDriversSensor(_ChampionshipPredictionBase):
    """Predicted Drivers Championship winner (P1).

    - State: predicted P1 driver TLA (string) when available
    - Attributes: predicted_driver_p1, drivers, last_update
    """

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

        if (not force) and self._attr_native_value == tla:
            return

        self._attr_native_value = tla
        self._attr_extra_state_attributes = {
            "predicted_driver_p1": pred if isinstance(pred, dict) else None,
            "drivers": drivers if isinstance(drivers, dict) else {},
            "last_update": last_update,
        }


class F1ChampionshipPredictionTeamsSensor(_ChampionshipPredictionBase):
    """Predicted Constructors Championship winner (P1).

    - State: predicted P1 team name (string)
    - Attributes: predicted_team_p1, teams, last_update
    """

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

        if (not force) and self._attr_native_value == team_name:
            return

        self._attr_native_value = team_name
        self._attr_extra_state_attributes = {
            "predicted_team_p1": pred if isinstance(pred, dict) else None,
            "teams": teams if isinstance(teams, dict) else {},
            "last_update": last_update,
        }


class F1RaceLapCountSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live race lap count based on LapCount coordinator.

    - State: current lap (int)
    - Attributes: total_laps (if present), measurement_time, measurement_age_seconds, received_at, raw
    - Restore: Remembers last value/attributes on restart and keeps them until new feed data arrives.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
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
                                t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                            self._last_timestamped_dt = t_ref
                        if t_ref is None:
                            ra = self._attr_extra_state_attributes.get("received_at")
                            if isinstance(ra, str) and ra:
                                t_ref = datetime.datetime.fromisoformat(
                                    ra.replace("Z", "+00:00")
                                )
                                if t_ref.tzinfo is None:
                                    t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
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
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                self._last_timestamped_dt = ts
        self._attr_native_value = curr
        self._last_received_utc = now_utc
        # Preserve last known total_laps if not present in this payload to avoid transient 'unknown'
        prev_total = None
        try:
            prev_total = (self._attr_extra_state_attributes or {}).get("total_laps")
        except Exception:
            prev_total = None
        if total is None:
            total = prev_total
        self._attr_extra_state_attributes = {
            "total_laps": total,
        }

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
                            t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
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
        with suppress(Exception):
            now_utc = dt_util.utcnow()
            t_ref = None
            mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
            if isinstance(mt, str) and mt:
                try:
                    t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                    if t_ref.tzinfo is None:
                        t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
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
                self._safe_write_ha_state()

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
        raw = self._extract_current()
        updated = raw is not None
        if not self._handle_stream_state(updated):
            return
        if not self._is_stream_active():
            self._safe_write_ha_state()
            return
        if raw is None:
            with suppress(Exception):
                getLogger(__name__).debug(
                    "RaceLapCount: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            return
        self._apply_payload(raw)
        self._safe_write_ha_state()

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        with suppress(Exception):
            if self._stale_timer:
                self._stale_timer()
                self._stale_timer = None


class F1DriverListSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live driver list sensor.

    - State: number of drivers in attributes
    - Attributes: drivers: [ { racing_number, tla, name, first_name, last_name, team, team_color, headshot_small, headshot_large, reference } ]
    - Behavior: restores last known state; logs only on change; respects consolidated drivers coordinator.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator (only if it has real driver data) or restore.
        #
        # LiveDriversCoordinator intentionally clears its consolidated state when
        # the live window ends to avoid briefly showing stale timing data at the
        # start of a new session. For `sensor.f1_driver_list` we *do* want to keep
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
                setattr(self, "_last_write_ts", now)
                self._safe_write_ha_state()
            else:
                # Schedule a delayed write at the 60s boundary if not already pending
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    setattr(self, "_pending_write", True)
                    delay = max(0.0, 60.0 - (now - lw)) if lw is not None else 60.0
                    from homeassistant.helpers.event import async_call_later as _later

                    def _do_write(_):
                        try:
                            setattr(self, "_last_write_ts", _time.time())
                            self._safe_write_ha_state()
                        finally:
                            setattr(self, "_pending_write", False)

                    _later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data or {}
        drivers = (data.get("drivers") or None) if isinstance(data, dict) else None
        if not isinstance(drivers, dict) or not drivers:
            return False
        # Build normalized list sorted by racing number (numeric if possible)
        items = []
        for rn, info in drivers.items():
            ident = (info.get("identity") or {}) if isinstance(info, dict) else {}
            try:
                team_color = ident.get("team_color")
                if (
                    isinstance(team_color, str)
                    and team_color
                    and not team_color.startswith("#")
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
            reg = (hass.data.get(DOMAIN, {}) or {}).get(self._entry_id)
            if not isinstance(reg, dict):
                return False
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
            self._attr_extra_state_attributes = {
                "drivers": items,
                "source": "ergast",
            }
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

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:tire"
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
            ident = (info.get("identity") or {}) if isinstance(info, dict) else {}
            tyres = (info.get("tyres") or {}) if isinstance(info, dict) else {}

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
                    and not team_color.startswith("#")
                ):
                    team_color = f"#{team_color}"
            except Exception:
                team_color = ident.get("team_color")

            # Derive short/colour codes
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
                    "position": position,
                    "compound": compound,
                    "compound_short": compound_short,
                    "compound_color": compound_color,
                    "new": is_new,
                    "stint_laps": stint_laps,
                }
            )

        def _rn_key(v):
            val = str(v.get("racing_number") or "")
            return (int(val) if val.isdigit() else 9999, val)

        # Stable ordering by car number
        items.sort(key=_rn_key)

        # State is the number of drivers we expose in the list
        self._attr_native_value = len(items)
        self._attr_extra_state_attributes = {"drivers": items}
        return True

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    @property
    def state(self):
        return self._attr_native_value


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

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-bar"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data or {}
        if not isinstance(data, dict):
            return False
        tyre_stats = data.get("tyre_statistics", {}) if isinstance(data, dict) else {}
        if not isinstance(tyre_stats, dict) or not tyre_stats:
            return False

        fastest_compound = tyre_stats.get("fastest_compound")
        fastest_time = tyre_stats.get("fastest_time")
        fastest_time_secs = tyre_stats.get("fastest_time_secs")
        deltas = tyre_stats.get("deltas", {})
        start_compounds = tyre_stats.get("start_compounds", [])
        compounds_raw = tyre_stats.get("compounds", {})

        # Enrich compounds with color info
        compounds = {}
        for comp_name, comp_data in compounds_raw.items():
            comp_copy = dict(comp_data)
            comp_copy["compound_color"] = self._COMPOUND_COLOR.get(comp_name)
            compounds[comp_name] = comp_copy

        self._attr_native_value = fastest_compound
        self._attr_extra_state_attributes = {
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
                "in_pit": False,
                "pit_out": False,
                "retired": False,
                "stopped": False,
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

    _unrecorded_attributes = frozenset({"drivers"})
    _PIT_OUT_HOLD_SECONDS = 6.0

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:podium"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "drivers": [],
            "total_laps": None,
            "fastest_lap": None,
        }
        self._last_write_ts: float | None = None
        self._pending_write: bool = False
        self._pit_out_until: dict[str, float] = {}
        self._pit_out_last: dict[str, bool] = {}
        self._session_info_coordinator = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        # Subscribe to SessionInfo for accurate session type/name gating
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            self._session_info_coordinator = reg.get("session_info_coordinator")
            if self._session_info_coordinator is not None:
                rem_info = self._session_info_coordinator.async_add_listener(
                    self._handle_session_info_update
                )
                self.async_on_remove(rem_info)
        except Exception:
            self._session_info_coordinator = None

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
                return session_type, session_name
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
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            replay_controller = (
                reg.get("replay_controller") if isinstance(reg, dict) else None
            )
            if replay_controller is None:
                return None, None
            session_manager = getattr(replay_controller, "session_manager", None)
            if session_manager is None:
                return None, None
            selected = getattr(session_manager, "selected_session", None)
            if selected is None:
                return None, None
            session_type = getattr(selected, "session_type", None)
            session_name = getattr(selected, "session_name", None)
            if session_type or session_name:
                return session_type, session_name
        except Exception:
            return None, None
        return None, None

    def _get_session_name_from_window(self) -> tuple[str | None, str | None]:
        """Fallback to live window metadata when SessionInfo is unavailable."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            live_supervisor = (
                reg.get("live_supervisor") if isinstance(reg, dict) else None
            )
            window = getattr(live_supervisor, "current_window", None)
            session_name = getattr(window, "session_name", None)
            if isinstance(session_name, str) and session_name:
                return None, session_name
        except Exception:
            return None, None
        return None, None

    @staticmethod
    def _is_race_or_sprint(session_type: str | None, session_name: str | None) -> bool:
        joined = f"{session_type or ''} {session_name or ''}".lower()
        if "sprint" in joined and "qualifying" not in joined:
            return True
        return "race" in joined

    def _normalize_restored_attributes(self, attrs: dict) -> dict:
        attrs.setdefault("drivers", [])
        attrs.setdefault("total_laps", None)
        attrs.setdefault("fastest_lap", None)
        drivers = attrs.get("drivers")
        if isinstance(drivers, list):
            for drv in drivers:
                if not isinstance(drv, dict):
                    continue
                drv.setdefault("fastest_lap", False)
                drv.setdefault("fastest_lap_time", None)
                drv.setdefault("fastest_lap_time_secs", None)
                drv.setdefault("fastest_lap_lap", None)
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
        fastest = data.get("fastest_lap") if allow_fastest else None
        fastest_rn = None
        if isinstance(fastest, dict):
            fastest_rn = str(fastest.get("racing_number") or "").strip() or None
        if fastest_rn is None:
            fastest = None

        # Build output structure
        drivers_out = {}
        for rn, info in drivers_raw.items():
            identity = info.get("identity", {})
            lap_history = info.get("lap_history", {})
            timing = info.get("timing", {})

            # Normalize team color
            team_color = identity.get("team_color")
            if (
                isinstance(team_color, str)
                and team_color
                and not team_color.startswith("#")
            ):
                team_color = f"#{team_color}"

            status, status_attrs = self._derive_driver_status(
                rn, timing, default_on_track=default_on_track
            )
            is_fastest = bool(allow_fastest and fastest_rn == rn)
            drivers_out[rn] = {
                "racing_number": rn,
                "tla": identity.get("tla"),
                "name": identity.get("name"),
                "team": identity.get("team"),
                "team_color": team_color,
                "grid_position": lap_history.get("grid_position"),
                "current_position": _extract_driver_position(info),
                "laps": lap_history.get("laps", {}),
                "completed_laps": lap_history.get(
                    "completed_laps", lap_history.get("last_recorded_lap", 0)
                ),
                "status": status,
                "fastest_lap": is_fastest,
                "fastest_lap_time": fastest.get("time") if is_fastest else None,
                "fastest_lap_time_secs": (
                    fastest.get("time_secs") if is_fastest else None
                ),
                "fastest_lap_lap": fastest.get("lap") if is_fastest else None,
                **status_attrs,
            }

        # Sort drivers by position: current_position if available, else grid_position
        def position_sort_key(drv: dict) -> tuple:
            current = drv.get("current_position")
            grid = drv.get("grid_position")
            # Use current_position if available, otherwise grid_position
            pos = current if current is not None else grid
            # Convert to int for proper numeric sorting, fallback to high value
            try:
                return (0, int(pos))
            except (TypeError, ValueError):
                return (1, 0)  # Drivers without position go last

        # Convert to list and sort to preserve order in Home Assistant
        drivers_list = sorted(drivers_out.values(), key=position_sort_key)

        self._attr_native_value = lap_current
        self._attr_extra_state_attributes = {
            "drivers": drivers_list,
            "total_laps": lap_total,
            "fastest_lap": dict(fastest) if isinstance(fastest, dict) else None,
        }
        return True

    def _is_replay_active(self) -> bool:
        """Return True when replay mode is playing/paused."""
        reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
            self._entry_id, {}
        ) or {}
        replay_controller = reg.get("replay_controller")
        if replay_controller is None:
            return False
        try:
            from .replay_mode import ReplayState

            return replay_controller.state in (
                ReplayState.PLAYING,
                ReplayState.PAUSED,
            )
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
        if default_on_track and not has_timing:
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

        return status, {
            "in_pit": in_pit if (has_timing or default_on_track) else None,
            "pit_out": pit_out_recent if (has_timing or default_on_track) else None,
            "retired": retired if (has_timing or default_on_track) else None,
            "stopped": stopped if (has_timing or default_on_track) else None,
        }

    def _clear_state(self) -> None:
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            "drivers": [],
            "total_laps": None,
            "fastest_lap": None,
        }

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

            def _do_write(_now):
                try:
                    self._last_write_ts = _time.time()
                    self._safe_write_ha_state()
                finally:
                    self._pending_write = False

            async_call_later(self.hass, delay, _do_write)

    @property
    def state(self):
        return self._attr_native_value
