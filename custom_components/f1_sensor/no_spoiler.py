"""No Spoiler Mode manager for the f1_sensor integration.

A single global instance controls the mode state across all config entries.
When active, all spoiler-sensitive coordinators freeze their entity state
(they still fetch and cache data internally). On deactivation, catch-up
is triggered by notifying registered entry listeners.
"""

from __future__ import annotations

from collections.abc import Callable
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

_STORAGE_KEY = "f1_sensor_no_spoiler_v1"
_STORAGE_VERSION = 1


class NoSpoilerModeManager:
    """Global manager for No Spoiler Mode state across all f1_sensor config entries.

    Persists state in HA storage so it survives restarts.  Listeners are
    called whenever the state changes; each config entry registers one listener
    to drive catch-up and supervisor wake-up on deactivation.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._active = False
        self._store: Store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
        self._listeners: list[Callable[[bool], None]] = []

    async def async_load(self) -> None:
        """Load persisted state from storage. Must be called once during async_setup."""
        try:
            data = await self._store.async_load()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to load no-spoiler state from storage", exc_info=True)
            data = None
        if isinstance(data, dict):
            self._active = bool(data.get("active", False))
        if self._active:
            _LOGGER.info("No Spoiler Mode restored as active from storage")

    @property
    def is_active(self) -> bool:
        """Return True when No Spoiler Mode is active."""
        return self._active

    def add_listener(self, callback: Callable[[bool], None]) -> Callable[[], None]:
        """Register a listener that is called when the active state changes.

        Returns an unsubscribe callable.  The callback receives the new bool value.
        """
        self._listeners.append(callback)

        def _remove() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

        return _remove

    async def async_set_active(self, active: bool) -> None:
        """Activate or deactivate No Spoiler Mode and persist the new state."""
        if self._active == active:
            return
        self._active = active
        try:
            await self._store.async_save({"active": active})
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to persist no-spoiler state", exc_info=True)
        _LOGGER.info("No Spoiler Mode %s", "activated" if active else "deactivated")
        for cb in list(self._listeners):
            try:
                cb(active)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("No-spoiler listener raised", exc_info=True)
