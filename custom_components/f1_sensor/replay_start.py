from __future__ import annotations
from contextlib import suppress

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_REPLAY_START_REFERENCE,
    DOMAIN,
    REPLAY_START_REFERENCE_FORMATION,
    REPLAY_START_REFERENCE_SESSION,
)

_LOGGER = logging.getLogger(__name__)


class ReplayStartReferenceController:
    """Persist and broadcast the replay start reference selection."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        storage_version: int = 1,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(
            hass,
            storage_version,
            f"{DOMAIN}_{entry_id}_replay_start_reference_v{storage_version}",
        )
        self._value: str = DEFAULT_REPLAY_START_REFERENCE
        self._listeners: list[Callable[[str], None]] = []
        self._save_task: asyncio.Task | None = None
        self._loaded = False

    @property
    def current(self) -> str:
        """Return current replay start reference."""
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
        """Persist and broadcast a new replay start reference."""
        new_value = self._normalize(value)
        if new_value == self._value:
            return self._value
        self._value = new_value
        if source:
            _LOGGER.debug(
                "Replay start reference updated via %s: %s",
                source,
                new_value,
            )
        await self._async_commit()
        self._notify_listeners()
        return self._value

    def add_listener(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Register callback invoked whenever the reference changes."""
        self._listeners.append(listener)
        try:
            listener(self._value)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Replay start reference listener raised during initial sync",
                exc_info=True,
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
                _LOGGER.debug("Replay start reference listener raised", exc_info=True)

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
                _LOGGER.debug("Failed to persist replay start reference", exc_info=True)

        self._save_task = self._hass.async_create_task(_save())

    def _normalize(self, value: Any) -> str:
        if value in (
            REPLAY_START_REFERENCE_SESSION,
            REPLAY_START_REFERENCE_FORMATION,
        ):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in (
                REPLAY_START_REFERENCE_SESSION,
                REPLAY_START_REFERENCE_FORMATION,
            ):
                return lowered
        return DEFAULT_REPLAY_START_REFERENCE
