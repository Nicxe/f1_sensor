"""Coordinator handling the TrackStatus feed."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .race_control import _is_session_active

LOGGER = logging.getLogger(__name__)


@dataclass
class TrackStatusCoordinator(DataUpdateCoordinator):
    """Polls the TrackStatus stream and exposes the latest value."""

    hass: HomeAssistant
    url: str
    session_index: Dict[str, Any]

    def __post_init__(self) -> None:
        super().__init__(
            self.hass,
            LOGGER,
            name="F1 Track Status Coordinator",
            update_interval=timedelta(seconds=5),
        )
        self._session = async_get_clientsession(self.hass)
        self._last_byte = 0
        self._last_new: datetime | None = None
        self._status: str | None = None
        self._finished = False

    CODE_MAP = {
        1: "GREEN",
        2: "SINGLE_YELLOW",
        3: "DOUBLE_YELLOW",
        4: "SAFETY_CAR",
        5: "VIRTUAL_SAFETY_CAR",
        6: "RED_FLAG",
        7: "TRACK_CLEAR",
    }

    async def async_close(self, *_: Any) -> None:  # pragma: no cover - placeholder
        return

    async def _async_update_data(self) -> Dict[str, Any]:
        if self._finished:
            return {"track_status": self._status, "timestamp": self._last_new}

        try:
            async with async_timeout.timeout(10):
                resp = await self._session.get(
                    self.url, headers={"Range": f"bytes={self._last_byte}-"}
                )
                if resp.status not in (200, 206):
                    raise UpdateFailed(f"TrackStatus fetch failed: {resp.status}")
                data_bytes = await resp.read()
        except Exception as err:  # pragma: no cover - network errors
            raise UpdateFailed(f"Error fetching track status data: {err}") from err

        if not data_bytes:
            now = datetime.now(timezone.utc)
            active = await _is_session_active(self.session_index)
            if (
                not active
                and self._last_new
                and (now - self._last_new).total_seconds() > 60
            ):
                LOGGER.debug("No new track status bytes for 60s, stopping updates")
                self._finished = True
            return {"track_status": self._status, "timestamp": self._last_new}

        self._last_new = datetime.now(timezone.utc)
        self._last_byte += len(data_bytes)
        text = data_bytes.decode(errors="ignore")

        status = self._status
        for line in text.splitlines():
            if not line:
                continue
            line = line.lstrip("\ufeff")
            json_start = line.find("{")
            if json_start == -1:
                continue
            try:
                data = json.loads(line[json_start:])
            except Exception:
                continue
            code = data.get("Status")
            if isinstance(code, str) and code.isdigit():
                code = int(code)
            if isinstance(code, int):
                mapped = self.CODE_MAP.get(code)
                if mapped:
                    status = mapped

        self._status = status
        return {"track_status": self._status, "timestamp": self._last_new}
