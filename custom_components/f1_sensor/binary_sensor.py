import datetime
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_OPERATION_MODE,
    CONF_RACE_WEEK_START_DAY,
    CONF_RACE_WEEK_SUNDAY_START,
    DEFAULT_RACE_WEEK_START_DAY,
    DEFAULT_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    RACE_WEEK_START_MONDAY,
    RACE_WEEK_START_SUNDAY,
)
from .entity import F1BaseEntity, F1AuxEntity
from .helpers import normalize_track_status
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

RACE_SWITCH_GRACE = datetime.timedelta(hours=3)


def _normalize_race_week_start(data: dict) -> str:
    value = data.get(CONF_RACE_WEEK_START_DAY)
    if value in (RACE_WEEK_START_MONDAY, RACE_WEEK_START_SUNDAY):
        return value
    legacy = data.get(CONF_RACE_WEEK_SUNDAY_START)
    if isinstance(legacy, bool):
        return RACE_WEEK_START_SUNDAY if legacy else RACE_WEEK_START_MONDAY
    if legacy in (RACE_WEEK_START_MONDAY, RACE_WEEK_START_SUNDAY):
        return legacy
    return DEFAULT_RACE_WEEK_START_DAY

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    data = hass.data[DOMAIN][entry.entry_id]
    base = entry.data.get("sensor_name", "F1")
    enabled = entry.data.get("enabled_sensors", [])
    race_week_start = _normalize_race_week_start(entry.data)

    sensors = []
    # Useful for power users/automations even when dev UI is disabled.
    if "live_timing_diagnostics" in enabled:
        sensors.append(
            F1LiveTimingOnlineBinarySensor(
                hass,
                entry.entry_id,
                base,
            )
        )
    if "race_week" in enabled:
        sensors.append(
            F1RaceWeekSensor(
                data["race_coordinator"],
                f"{base}_race_week",
                f"{entry.entry_id}_race_week",
                entry.entry_id,
                base,
                race_week_start=race_week_start,
            )
        )
    if "safety_car" in enabled:
        coord = data.get("track_status_coordinator")
        if coord:
            sensors.append(
                F1SafetyCarBinarySensor(
                    coord,
                    f"{base}_safety_car",
                    f"{entry.entry_id}_safety_car",
                    entry.entry_id,
                    base,
                )
            )
    async_add_entities(sensors, True)


class F1RaceWeekSensor(F1BaseEntity, BinarySensorEntity):
    """Binary sensor indicating if it's currently race week."""

    def __init__(
        self,
        coordinator,
        name,
        unique_id,
        entry_id,
        device_name,
        *,
        race_week_start: str = DEFAULT_RACE_WEEK_START_DAY,
    ):
        super().__init__(coordinator, name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-range"
        # No device class: this is not a physical presence/occupancy type sensor.
        # Using a device class here can lead to misleading UI semantics/translations.
        self._attr_device_class = None
        self._race_week_start = race_week_start

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None, None

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = dt_util.utcnow()

        for race in races:
            date = race.get("date")
            if not date:
                continue
            # If the source omits time for some reason, assume end-of-day so we
            # don't drop out of "race week" early on race day.
            time = race.get("time") or "23:59:59Z"
            dt_str = f"{date}T{time}".replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            # Consider the current race as "next" until a short grace period
            # after the scheduled start, matching `sensor.f1_next_race`.
            if (dt + RACE_SWITCH_GRACE) > now:
                return dt, race
        return None, None

    @property
    def is_on(self):
        next_race_dt, _ = self._get_next_race()
        if not next_race_dt:
            return False
        now_local = dt_util.as_local(dt_util.utcnow())
        next_race_local = dt_util.as_local(next_race_dt)

        first_weekday = (
            6 if self._race_week_start == RACE_WEEK_START_SUNDAY else 0
        )  # Monday=0..Sunday=6
        days_since_week_start = (now_local.weekday() - first_weekday) % 7
        start_of_week = now_local.date() - datetime.timedelta(days=days_since_week_start)
        end_of_week = start_of_week + datetime.timedelta(days=6)
        return start_of_week <= next_race_local.date() <= end_of_week

    @property
    def extra_state_attributes(self):
        next_race_dt, race = self._get_next_race()
        now_local = dt_util.as_local(dt_util.utcnow())
        days = None
        race_name = None
        if next_race_dt:
            next_race_local = dt_util.as_local(next_race_dt)
            delta = next_race_local.date() - now_local.date()
            days = delta.days
            race_name = race.get("raceName") if race else None
        return {
            "days_until_next_race": days,
            "next_race_name": race_name,
        }


class F1SafetyCarBinarySensor(F1BaseEntity, RestoreEntity, BinarySensorEntity):
    """Binary sensor indicating if the Safety Car or VSC is active."""

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator, name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car"
        # No device class: BinarySensorDeviceClass.SAFETY maps to "safe/unsafe"
        # semantics (OFF="safe"), which is misleading for "safety car deployed".
        self._attr_device_class = None
        self._attr_is_on = False
        self._attr_extra_state_attributes = {}
        self._last_ts: datetime.datetime | None = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.async_add_listener(self._handle_coordinator_update)
        # Prefer coordinator's latest if present
        payload, ts = self._extract_payload()
        if payload is not None:
            self._update_from_track_status()
        else:
            # Restore last state
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_is_on = last.state in (True, "on", "True", "true")
                self._attr_extra_state_attributes = {
                    **(self._attr_extra_state_attributes or {}),
                    "restored": True,
                }
        self.async_write_ha_state()

    def _extract_payload(self) -> tuple[dict | None, datetime.datetime | None]:
        data = self.coordinator.data
        if not data:
            return None, None
        payload = None
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            payload = data
        elif isinstance(data, dict) and isinstance(data.get("data"), dict):
            payload = data.get("data")
        # Try to parse a timestamp to guard against old updates
        ts_raw = None
        if isinstance(payload, dict):
            ts_raw = (
                payload.get("Utc")
                or payload.get("utc")
                or payload.get("processedAt")
                or payload.get("timestamp")
            )
        ts = None
        if ts_raw:
            try:
                ts = datetime.datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
            except Exception:  # noqa: BLE001
                ts = None
        return payload, ts

    def _update_from_track_status(self) -> None:
        payload, ts = self._extract_payload()
        if ts and self._last_ts and ts <= self._last_ts:
            _LOGGER.debug("SafetyCar: Ignored old TrackStatus (ts=%s <= last=%s): %s", ts, self._last_ts, payload)
            return
        state = normalize_track_status(payload)
        is_on = state in {"VSC", "SC"}
        _LOGGER.debug(
            "SafetyCar: Update from TrackStatus at %s -> state=%s, is_on=%s, raw=%s",
            dt_util.utcnow().isoformat(timespec="seconds"),
            state,
            is_on,
            payload,
        )
        self._attr_is_on = is_on
        self._attr_extra_state_attributes = {"track_status": state}
        if ts:
            self._last_ts = ts

    def _handle_coordinator_update(self) -> None:
        self._update_from_track_status()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._attr_is_on


class F1LiveTimingOnlineBinarySensor(F1AuxEntity, BinarySensorEntity):
    """Diagnostic connectivity sensor for the live timing transport.

    - ON: replay mode, or live timing window active with recent stream activity.
    - OFF: outside window / idle.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:access-point"

    def __init__(self, hass: HomeAssistant, entry_id: str, device_name: str) -> None:
        super().__init__(
            name=f"{device_name}_live_timing_online",
            unique_id=f"{entry_id}_live_timing_online",
            entry_id=entry_id,
            device_name=device_name,
        )
        self.hass = hass
        self._entry_id = entry_id
        self._unsub_live_state = None
        self._online_threshold_s = 90.0

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

        # Periodic update to refresh age-related attributes while running
        try:
            unsub = async_track_time_interval(
                self.hass,
                lambda *_: self._safe_write_ha_state(),
                datetime.timedelta(seconds=10),
            )
            self.async_on_remove(unsub)
        except Exception:
            pass

    def _compute_mode_and_ages(self) -> tuple[str, float | None, float | None, float | None, str | None]:
        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        operation_mode = reg.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
        live_state = reg.get("live_state")
        live_bus = reg.get("live_bus")

        is_live_window = bool(getattr(live_state, "is_live", False)) if live_state is not None else False
        reason = getattr(live_state, "reason", None) if live_state is not None else None

        if operation_mode == OPERATION_MODE_DEVELOPMENT:
            mode = "replay"
        else:
            mode = "live" if is_live_window else "idle"

        hb_age = None
        activity_age = None
        effective_age = None
        try:
            if live_bus is not None:
                hb_age = live_bus.last_heartbeat_age()
                activity_age = live_bus.last_stream_activity_age()
                effective_age = hb_age if hb_age is not None else activity_age
        except Exception:
            hb_age = activity_age = effective_age = None

        return mode, hb_age, activity_age, effective_age, reason

    @property
    def is_on(self) -> bool:
        mode, _, _, effective_age, _ = self._compute_mode_and_ages()
        if mode == "replay":
            return True
        if mode != "live":
            return False
        # If we just armed the window and haven't seen frames yet, be optimistic.
        if effective_age is None:
            return True
        return effective_age < self._online_threshold_s

    @property
    def extra_state_attributes(self):
        mode, hb_age, activity_age, effective_age, reason = self._compute_mode_and_ages()
        return {
            "mode": mode,
            "reason": reason,
            "online_threshold_s": self._online_threshold_s,
            "heartbeat_age_s": (round(hb_age, 1) if hb_age is not None else None),
            "activity_age_s": (round(activity_age, 1) if activity_age is not None else None),
            "effective_age_s": (round(effective_age, 1) if effective_age is not None else None),
        }
