import datetime
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import F1BaseEntity
from .helpers import normalize_track_status
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    data = hass.data[DOMAIN][entry.entry_id]
    base = entry.data.get("sensor_name", "F1")
    enabled = entry.data.get("enabled_sensors", [])

    sensors = []
    if "race_week" in enabled:
        sensors.append(
            F1RaceWeekSensor(
                data["race_coordinator"],
                f"{base}_race_week",
                f"{entry.entry_id}_race_week",
                entry.entry_id,
                base,
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

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator, name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-range"
        self._attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None, None

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = datetime.datetime.now(datetime.timezone.utc)

        for race in races:
            date = race.get("date")
            time = race.get("time") or "00:00:00Z"
            dt_str = f"{date}T{time}".replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            if dt > now:
                return dt, race
        return None, None

    @property
    def is_on(self):
        next_race_dt, _ = self._get_next_race()
        if not next_race_dt:
            return False
        now = datetime.datetime.now(datetime.timezone.utc)
        start_of_week = now - datetime.timedelta(days=now.weekday())
        end_of_week = start_of_week + datetime.timedelta(
            days=6, hours=23, minutes=59, seconds=59
        )
        return start_of_week.date() <= next_race_dt.date() <= end_of_week.date()

    @property
    def state(self):
        return self.is_on

    @property
    def extra_state_attributes(self):
        next_race_dt, race = self._get_next_race()
        now = datetime.datetime.now(datetime.timezone.utc)
        days = None
        race_name = None
        if next_race_dt:
            delta = next_race_dt.date() - now.date()
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
        try:
            from homeassistant.components.binary_sensor import BinarySensorDeviceClass

            self._attr_device_class = BinarySensorDeviceClass.SAFETY
        except Exception:
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
        self._attr_extra_state_attributes = {"track_status": state, "raw": payload}
        if ts:
            self._last_ts = ts

    def _handle_coordinator_update(self) -> None:
        self._update_from_track_status()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    @property
    def state(self):
        return self.is_on
