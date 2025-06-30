import datetime

from homeassistant.components.binary_sensor import (BinarySensorDeviceClass,
                                                    BinarySensorEntity)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import F1BaseEntity


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
        sensors.append(
            F1SafetyCarBinarySensor(
                data.get("race_control_coordinator"),
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


class SafetyCarStateMachine:
    """State machine for safety car messages."""

    def __init__(self) -> None:
        self.sc_active: bool = False

    def handle_message(self, msg: dict) -> bool:
        if msg.get("Category") != "SafetyCar":
            return self.sc_active

        status = msg.get("Status")
        if status == "DEPLOYED":
            self.sc_active = True
        elif status in ("ENDED",):
            self.sc_active = False
        return self.sc_active


class F1SafetyCarBinarySensor(F1BaseEntity, BinarySensorEntity):
    """Binary sensor indicating if the Safety Car or VSC is active."""

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator, name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car"
        try:
            from homeassistant.components.binary_sensor import \
                BinarySensorDeviceClass

            self._attr_device_class = BinarySensorDeviceClass.SAFETY
        except Exception:
            self._attr_device_class = None
        self._machine = SafetyCarStateMachine()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.coordinator.async_add_listener(self._handle_coordinator_update)
        if self.coordinator.data:
            self._machine.handle_message(self.coordinator.data)

    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            self._machine.handle_message(self.coordinator.data)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._machine.sc_active

    @property
    def state(self):
        return self.is_on
