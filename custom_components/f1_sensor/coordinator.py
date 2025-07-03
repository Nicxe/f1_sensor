import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import F1ApiClient

_LOGGER = logging.getLogger(__name__)


class F1DataCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for F1 API."""

    def __init__(self, hass: HomeAssistant, client: F1ApiClient, url: str, name: str, paginated: bool = False) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(minutes=15),
        )
        self._client = client
        self._url = url
        self._paginated = paginated

    async def _async_update_data(self):
        try:
            if self._paginated:
                return await self._client.async_get_paginated(self._url)
            return await self._client.async_get(self._url)
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}") from err
