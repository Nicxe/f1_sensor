from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class F1BaseEntity(CoordinatorEntity):
    """Common base entity for F1 sensors."""

    def __init__(self, coordinator, name, unique_id, entry_id, device_name):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._device_name,
            "manufacturer": "Nicxe",
            "model": "F1 Sensor",
        }
