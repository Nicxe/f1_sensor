"""Coordinators for real-time SignalR feeds."""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

LOGGER = logging.getLogger(__name__)


class TrackStatusWSCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Expose the latest TrackStatus payload from SignalR."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            LOGGER,
            name="F1 TrackStatus WS Coordinator",
            update_interval=None,
        )
        self.data: Dict[str, Any] | None = None

    async def _async_update_data(self) -> Dict[str, Any] | None:
        return self.data

    async def async_close(self, *_: Any) -> None:  # pragma: no cover - placeholder
        """Cleanup when integration entry is unloaded."""
        self._async_unsub_refresh()
        self._async_unsub_shutdown()


class SessionStatusCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Expose the latest SessionStatus payload from SignalR."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            LOGGER,
            name="F1 SessionStatus Coordinator",
            update_interval=None,
        )
        self.data: Dict[str, Any] | None = None

    async def _async_update_data(self) -> Dict[str, Any] | None:
        return self.data

    async def async_close(self, *_: Any) -> None:  # pragma: no cover - placeholder
        """Cleanup when integration entry is unloaded."""
        self._async_unsub_refresh()
        self._async_unsub_shutdown()
