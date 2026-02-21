from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)


class StoredReferenceController:
    """Persist and broadcast a string reference value."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        storage_key: str,
        default: str,
        allowed: set[str],
        log_label: str,
        storage_version: int = 1,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(hass, storage_version, storage_key)
        self._default = default
        self._allowed = allowed
        self._log_label = log_label
        self._value: str = default
        self._listeners: list[Callable[[str], None]] = []
        self._save_task: asyncio.Task | None = None
        self._loaded = False

    @property
    def current(self) -> str:
        return self._value

    async def async_initialize(self, fallback: Any) -> str:
        """Load stored reference and fall back to default if missing."""
        initial = self._normalize(fallback)
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            stored_value = self._normalize(stored.get("reference"))
            if stored_value:
                initial = stored_value
        self._value = initial
        self._loaded = True
        await self._async_commit()
        return self._value

    async def async_set_reference(
        self, value: Any, *, source: str | None = None
    ) -> str:
        new_value = self._normalize(value)
        if new_value == self._value:
            return self._value
        self._value = new_value
        if source:
            _LOGGER.debug("%s updated via %s: %s", self._log_label, source, new_value)
        await self._async_commit()
        self._notify_listeners()
        return self._value

    def add_listener(self, listener: Callable[[str], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        try:
            listener(self._value)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("%s listener raised during initial sync", self._log_label)

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
                _LOGGER.debug("%s listener raised", self._log_label, exc_info=True)

    async def _async_commit(self) -> None:
        if not self._loaded:
            return
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
            self._save_task = None

        async def _save() -> None:
            try:
                await self._store.async_save({"reference": self._value})
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to persist %s", self._log_label, exc_info=True)

        self._save_task = self._hass.async_create_task(_save())

    def _normalize(self, value: Any) -> str:
        if value in self._allowed:
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in self._allowed:
                return lowered
        return self._default
