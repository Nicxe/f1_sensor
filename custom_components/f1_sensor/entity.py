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
            try:
                self.schedule_update_ha_state()
            except Exception:
                pass
