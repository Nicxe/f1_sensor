from __future__ import annotations
from contextlib import suppress

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_LIVE_DELAY_REFERENCE,
    DOMAIN,
    LIVE_DELAY_REFERENCE_FORMATION,
    LIVE_DELAY_REFERENCE_SESSION,
)
from .reference_controller import StoredReferenceController

_LOGGER = logging.getLogger(__name__)


class LiveDelayController:
    """Centralizes the live delay value and notifies listeners on changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        min_seconds: int = 0,
        max_seconds: int = 300,
        storage_version: int = 1,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._min = int(min_seconds)
        self._max = int(max_seconds)
        self._store = Store(
            hass,
            storage_version,
            f"{DOMAIN}_{entry_id}_live_delay_v{storage_version}",
        )
        self._value: int = 0
        self._listeners: list[Callable[[int], None]] = []
        self._save_task: asyncio.Task | None = None
        self._loaded = False

    @property
    def current(self) -> int:
        return self._value

    async def async_initialize(self, fallback_seconds: Any) -> int:
        """Load stored delay and fall back to config option if missing."""
        initial = self._coerce(fallback_seconds)
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            stored_value = self._coerce(stored.get("seconds"))
            if stored_value is not None:
                initial = stored_value
        self._value = self._clamp(initial or 0)
        self._loaded = True
        await self._async_commit()
        return self._value

    async def async_set_delay(self, seconds: Any, *, source: str | None = None) -> int:
        """Persist and broadcast a new delay in seconds."""
        new_value = self._clamp(self._coerce(seconds) or 0)
        if new_value == self._value:
            return self._value
        self._value = new_value
        if source:
            _LOGGER.debug(
                "Live delay updated via %s: %ss",
                source,
                new_value,
            )
        await self._async_commit()
        self._notify_listeners()
        return self._value

    def add_listener(self, listener: Callable[[int], None]) -> Callable[[], None]:
        """Register callback invoked whenever the delay changes."""
        self._listeners.append(listener)
        try:
            listener(self._value)
        except Exception:  # noqa: BLE001 - defensive
            _LOGGER.debug(
                "LiveDelay listener raised during initial sync", exc_info=True
            )

        @callback
        def _remove() -> None:
            with suppress(ValueError):
                self._listeners.remove(listener)

        return _remove

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener(self._value)
            except Exception:  # noqa: BLE001
                _LOGGER.debug("LiveDelay listener raised", exc_info=True)

    async def _async_commit(self) -> None:
        if not self._loaded:
            return
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
            self._save_task = None

        async def _save() -> None:
            try:
                await self._store.async_save({"seconds": self._value})
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to persist live delay", exc_info=True)

        self._save_task = self._hass.async_create_task(_save())

    def _coerce(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _clamp(self, value: int) -> int:
        return max(self._min, min(self._max, int(value)))


class LiveDelayReferenceController(StoredReferenceController):
    """Persists the chosen reference for live delay calibration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        storage_version: int = 1,
    ) -> None:
        super().__init__(
            hass,
            entry_id,
            storage_key=f"{DOMAIN}_{entry_id}_live_delay_reference_v{storage_version}",
            default=DEFAULT_LIVE_DELAY_REFERENCE,
            allowed={
                LIVE_DELAY_REFERENCE_SESSION,
                LIVE_DELAY_REFERENCE_FORMATION,
            },
            log_label="Live delay reference",
            storage_version=storage_version,
        )
