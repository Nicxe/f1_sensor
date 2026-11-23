"""Warm shared static sources only when sensors or card modules need them."""

import asyncio
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

STATIC_SOURCE_ORDER = (
    "race_coordinator",
    "driver_coordinator",
    "constructor_coordinator",
    "last_race_coordinator",
    "season_results_coordinator",
    "sprint_results_coordinator",
    "next_race_history_coordinator",
    "race_weather_coordinator",
    "lap_position_progression_coordinator",
    "fia_documents_coordinator",
)
STATIC_SOURCE_PARENTS = {
    "season_results_coordinator": ("race_coordinator",),
    "next_race_history_coordinator": ("race_coordinator",),
    "race_weather_coordinator": ("race_coordinator",),
    "lap_position_progression_coordinator": (
        "race_coordinator",
        "season_results_coordinator",
        "sprint_results_coordinator",
    ),
    "fia_documents_coordinator": ("race_coordinator",),
}
DEMAND_OWNED_STATIC_SOURCES = (
    "next_race_history_coordinator",
    "race_weather_coordinator",
    "lap_position_progression_coordinator",
    "fia_documents_coordinator",
)


class CardDataSources:
    """Share lazy first reads while coordinator listeners own periodic polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        sources: dict,
        sensor_sources: set[str],
        *,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        self.hass = hass
        self._config_entry = config_entry
        self.sources = {
            key: sources[key]
            for key in STATIC_SOURCE_ORDER
            if sources.get(key) is not None
        }
        self.sensor_sources = sensor_sources & self.sources.keys()
        for name in self.sensor_sources:
            # The platform can register before this coordinator has a payload.
            self.sources[name].requires_initial_data = True
        self.required: set[str] = set()
        self._refreshed = {
            name: monotonic()
            for name, source in self.sources.items()
            if source.data is not None
        }
        self._queued: set[str] = set()
        self._preparing: set[str] = set()
        self._task = None
        self.closed = False

    @callback
    def reconcile(self, card_sources: set[str]) -> None:
        """Acquire data without adding a permanent polling consumer."""
        if self.closed:
            return
        desired = self.sensor_sources | (card_sources & self.sources.keys())
        acquired = desired - self.required
        pending = {name for name in acquired if self._needs_refresh(name)}
        preparing = pending | self._queued | self._preparing
        for name in STATIC_SOURCE_ORDER:
            if name in acquired and preparing.intersection(
                STATIC_SOURCE_PARENTS.get(name, ())
            ):
                pending.add(name)
                preparing.add(name)
        self._queued.update(pending)
        for name in DEMAND_OWNED_STATIC_SOURCES:
            source = self.sources.get(name)
            if source is None:
                continue
            if name in desired:
                if name not in self._queued | self._preparing:
                    source.async_start()
            elif name in self.required:
                source.async_stop()
        self.required = desired
        if self._queued and self._task is None:
            if self._config_entry is None:
                self._task = self.hass.async_create_task(
                    self._async_prepare(), eager_start=False
                )
            else:
                self._task = self._config_entry.async_create_background_task(
                    self.hass,
                    self._async_prepare(),
                    "Warm F1 static data sources",
                    eager_start=False,
                )

    def _needs_refresh(self, name: str) -> bool:
        source = self.sources[name]
        interval = getattr(source, "update_interval", None)
        max_age = interval.total_seconds() if interval is not None else 3600
        return (
            source.data is None
            or not source.last_update_success
            or monotonic() - self._refreshed.get(name, float("-inf")) >= max_age
        )

    @callback
    def mark_updated(self, name: str) -> None:
        """Track successful reads without retaining another polling listener."""
        if (
            name in self.sources
            and self.sources[name].data is not None
            and self.sources[name].last_update_success
        ):
            self._refreshed[name] = monotonic()

    def is_needed(self, source) -> bool:
        """Filter catch-up requests for static sources without current demand."""
        return any(
            name in self.required
            for name, value in self.sources.items()
            if value is source
        )

    async def _async_prepare(self) -> None:
        try:
            while self._queued:
                names = self._queued
                self._queued = set()
                self._preparing = names
                tasks = {}
                async with asyncio.TaskGroup() as group:
                    for name in STATIC_SOURCE_ORDER:
                        if name not in names:
                            continue
                        parents = tuple(
                            tasks[parent]
                            for parent in STATIC_SOURCE_PARENTS.get(name, ())
                            if parent in tasks
                        )
                        tasks[name] = group.create_task(
                            self._async_prepare_source(name, parents)
                        )
        finally:
            self._preparing.clear()
            self._task = None

    async def _async_prepare_source(
        self, name: str, parents: tuple[asyncio.Task[None], ...]
    ) -> None:
        for parent in parents:
            await parent
        if name not in self.required:
            return
        source = self.sources[name]
        if name in DEMAND_OWNED_STATIC_SOURCES:
            source.async_start()
        await source.async_refresh()
        if (
            name == "fia_documents_coordinator"
            and name in self.sensor_sources
            and source.data is None
            and not source.last_update_success
        ):
            source.async_set_updated_data(source.build_empty_result())
        self.mark_updated(name)

    async def async_close(self) -> None:
        """Cancel outstanding first reads on unload; keep no background worker."""
        self.closed = True
        self._queued.clear()
        if self._task is not None:
            task = self._task
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for name in DEMAND_OWNED_STATIC_SOURCES:
            if name in self.required:
                self.sources[name].async_stop()
        self.required.clear()
