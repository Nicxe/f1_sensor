"""Warm shared static sources only when sensors or card modules need them."""

import asyncio
from time import monotonic

from homeassistant.core import HomeAssistant, callback

# Parent sources must be ready before derived history, forecasts and documents.
STATIC_SOURCE_STAGES = (
    ("race_coordinator",),
    (
        "driver_coordinator",
        "constructor_coordinator",
        "last_race_coordinator",
        "season_results_coordinator",
        "sprint_results_coordinator",
    ),
    (
        "next_race_history_coordinator",
        "race_weather_coordinator",
        "lap_position_progression_coordinator",
        "fia_documents_coordinator",
    ),
)
STATIC_SOURCE_ORDER = tuple(name for stage in STATIC_SOURCE_STAGES for name in stage)


class CardDataSources:
    """Share lazy first reads while coordinator listeners own periodic polling."""

    def __init__(
        self, hass: HomeAssistant, sources: dict, sensor_sources: set[str]
    ) -> None:
        self.hass = hass
        self.sources = {
            key: sources[key]
            for key in STATIC_SOURCE_ORDER
            if sources.get(key) is not None
        }
        self.sensor_sources = sensor_sources & self.sources.keys()
        self.required = set(self.sensor_sources)
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
        if "race_coordinator" in pending | self._queued | self._preparing:
            pending.update(
                acquired & {"next_race_history_coordinator", "race_weather_coordinator"}
            )
        self._queued.update(pending)
        for name in ("next_race_history_coordinator", "race_weather_coordinator"):
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
            self._task = self.hass.async_create_task(
                self._async_prepare(), eager_start=False
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
                for stage in STATIC_SOURCE_STAGES:
                    await asyncio.gather(
                        *(
                            self._async_prepare_source(name)
                            for name in stage
                            if name in names
                        )
                    )
        finally:
            self._preparing.clear()
            self._task = None

    async def _async_prepare_source(self, name: str) -> None:
        if name not in self.required:
            return
        if name in {"next_race_history_coordinator", "race_weather_coordinator"}:
            self.sources[name].async_start()
        await self.sources[name].async_request_refresh()
        self.mark_updated(name)

    async def async_close(self) -> None:
        """Cancel outstanding first reads on unload; keep no background worker."""
        self.closed = True
        self._queued.clear()
        if self._task is not None:
            task = self._task
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.required.clear()
