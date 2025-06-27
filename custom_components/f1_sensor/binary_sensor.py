from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
import datetime

from .const import (
    DOMAIN,
    SIGNAL_FLAG_UPDATE,
    SIGNAL_SC_UPDATE,
    SIGNAL_CONNECTED,
    SIGNAL_DISCONNECTED,
)
from .entity import F1BaseEntity
from .signalr_client import F1SignalRClient

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
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
    if "safety_car" in enabled and data.get("race_control_coordinator"):
        sensors.append(
            F1SafetyCarSensor(
                data["race_control_coordinator"],
                f"{base}_safety_car",
                f"{entry.entry_id}_safety_car",
                entry.entry_id,
                base,
            )
        )
    rc_coord = data.get("race_control_coordinator")
    client = getattr(rc_coord, "_client", None) if rc_coord else None
    if client:
        sensors.append(F1SignalRBinary(client))
    sensors.append(F1SignalRStatus(hass))
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
        end_of_week = start_of_week + datetime.timedelta(days=6, hours=23, minutes=59, seconds=59)
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


class F1SafetyCarSensor(F1BaseEntity, BinarySensorEntity):
    """Binary sensor indicating if Safety Car or VSC is active."""

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator, name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car"
        self._attr_device_class = BinarySensorDeviceClass.SAFETY
        self._sc_state = False

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SC_UPDATE, self._handle_sc_update)
        )

    def _handle_sc_update(self, sc_active: bool):
        self._sc_state = sc_active
        self.async_write_ha_state()

    @property
    def is_on(self):
        return self._sc_state or (self.coordinator.data or {}).get("sc_active")

    @property
    def state(self):
        return self.is_on


class F1SignalRBinary(BinarySensorEntity):
    """Shows if SignalR connection is alive."""

    _attr_name = "F1 SignalR"
    _attr_icon = "mdi:web"

    def __init__(self, client: F1SignalRClient) -> None:
        self._client = client
        self._attr_unique_id = "f1_signalr_status"

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, "f1_signalr_state", self.async_write_ha_state
            )
        )

    @property
    def is_on(self) -> bool:
        return self._client.connected and not self._client.failed

    async def async_update(self):
        return


class F1SignalRStatus(BinarySensorEntity):
    _attr_name = "F1 SignalR connected"
    _attr_icon = "mdi:web"

    def __init__(self, hass: HomeAssistant) -> None:
        self._attr_is_on = False
        async_dispatcher_connect(hass, SIGNAL_CONNECTED, self._set_on)
        async_dispatcher_connect(hass, SIGNAL_DISCONNECTED, self._set_off)

    def _set_on(self) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    def _set_off(self) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
