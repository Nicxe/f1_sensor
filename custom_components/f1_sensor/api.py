import asyncio
import logging
from typing import Any, Dict, Optional

import async_timeout
from aiohttp import ClientSession, ClientResponse

_LOGGER = logging.getLogger(__name__)


class F1ApiClient:
    """Client for interacting with the Jolpica F1 API."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform a HTTP GET request with retries on rate limiting."""
        retries = 3
        delay = 1
        for attempt in range(retries):
            try:
                async with async_timeout.timeout(10):
                    response: ClientResponse = await self._session.get(url, params=params)
                if response.status == 429:
                    if attempt < retries - 1:
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                return await response.json()
            except Exception as err:
                if attempt >= retries - 1:
                    _LOGGER.error("API request failed: %s", err)
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        return {}

    async def async_get(self, url: str) -> Dict[str, Any]:
        """Return JSON response from API."""
        return await self._request(url)

    async def async_get_paginated(self, url: str) -> Dict[str, Any]:
        """Fetch all pages for endpoints that support pagination."""
        limit = 100
        params = {"limit": limit, "offset": 0}
        data = await self._request(url, params)
        total = int(data.get("MRData", {}).get("total", 0))
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        offset = limit
        while len(races) < total:
            params["offset"] = offset
            page = await self._request(url, params)
            races.extend(page.get("MRData", {}).get("RaceTable", {}).get("Races", []))
            offset += limit
        if "RaceTable" in data.get("MRData", {}):
            data["MRData"]["RaceTable"]["Races"] = races
        return data
