"""Favourite driver selection, state projection, and automation events."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

FAVORITE_DRIVER_EVENT = f"{DOMAIN}_favorite_driver_event"
FAVORITE_DRIVER_STORAGE_VERSION = 1
FAVORITE_DRIVER_NONE = "No driver"


def _position(info: dict[str, Any]) -> int | None:
    timing = info.get("timing") if isinstance(info, dict) else None
    raw = timing.get("position") if isinstance(timing, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("Value")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _normalise_driver(racing_number: str, info: dict[str, Any]) -> dict[str, Any]:
    identity = info.get("identity") if isinstance(info.get("identity"), dict) else {}
    timing = info.get("timing") if isinstance(info.get("timing"), dict) else {}
    tyres = info.get("tyres") if isinstance(info.get("tyres"), dict) else {}
    laps = info.get("lap_history") if isinstance(info.get("lap_history"), dict) else {}
    team_color = identity.get("team_color")
    if isinstance(team_color, str) and team_color and not team_color.startswith("#"):
        team_color = f"#{team_color}"
    team_color_rgb = None
    if isinstance(team_color, str) and len(team_color.removeprefix("#")) == 6:
        with suppress(ValueError):
            value = team_color.removeprefix("#")
            team_color_rgb = [
                int(value[0:2], 16),
                int(value[2:4], 16),
                int(value[4:6], 16),
            ]
    return {
        "racing_number": str(identity.get("racing_number") or racing_number),
        "tla": str(identity.get("tla") or "").strip().upper() or None,
        "name": identity.get("name"),
        "team": identity.get("team"),
        "team_color": team_color,
        "team_color_rgb": team_color_rgb,
        "position": _position(info),
        "grid_position": laps.get("grid_position"),
        "gap_to_leader": timing.get("gap_to_leader"),
        "interval_to_position_ahead": timing.get("interval"),
        "last_lap": timing.get("last_lap"),
        "best_lap": timing.get("best_lap"),
        "in_pit": bool(timing.get("in_pit")),
        "pit_out": bool(timing.get("pit_out")),
        "pit_stops": timing.get("pit_stops"),
        "retired": bool(timing.get("retired")),
        "stopped": bool(timing.get("stopped")),
        "status_code": timing.get("status_code"),
        "compound": tyres.get("compound"),
        "stint_laps": tyres.get("stint_laps"),
        "new_tyres": tyres.get("new"),
    }


class FavoriteDriverController:
    """Persist one selected driver and project their current live state."""

    def __init__(self, hass: HomeAssistant, entry_id: str, coordinator: Any) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.coordinator = coordinator
        self._selected_tla: str | None = None
        self._snapshot: dict[str, Any] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsub_coordinator: Callable[[], None] | None = None
        self._store = Store(
            hass,
            FAVORITE_DRIVER_STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}_favorite_driver_v1",
        )

    @property
    def selected_tla(self) -> str | None:
        return self._selected_tla

    @property
    def snapshot(self) -> dict[str, Any] | None:
        return dict(self._snapshot) if self._snapshot is not None else None

    @property
    def available(self) -> bool:
        return bool(
            self._snapshot is not None and getattr(self.coordinator, "available", True)
        )

    @property
    def options(self) -> list[str]:
        values = {
            driver.get("tla")
            for driver in self._drivers()
            if isinstance(driver.get("tla"), str) and driver.get("tla")
        }
        if self._selected_tla:
            values.add(self._selected_tla)
        return sorted(values)

    async def async_load(self) -> None:
        with suppress(Exception):
            stored = await self._store.async_load()
            if isinstance(stored, dict):
                selected = str(stored.get("tla") or "").strip().upper()
                self._selected_tla = selected or None
        self._snapshot = self._selected_driver()

    @callback
    def start(self) -> None:
        if self._unsub_coordinator is None:
            self._unsub_coordinator = self.coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        self._handle_coordinator_update(emit_events=False)

    async def async_close(self) -> None:
        """Detach listeners when the config entry unloads or setup rolls back."""
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        self._listeners.clear()

    async def async_shutdown(self) -> None:
        """Compatibility alias used by focused controller tests."""
        await self.async_close()

    async def async_set_driver(self, tla: str | None) -> None:
        selected = str(tla or "").strip().upper() or None
        if selected == FAVORITE_DRIVER_NONE.upper():
            selected = None
        if selected == self._selected_tla:
            return
        self._selected_tla = selected
        self._snapshot = self._selected_driver()
        await self._store.async_save({"tla": selected})
        self._notify_listeners()

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        @callback
        def _remove() -> None:
            with suppress(ValueError):
                self._listeners.remove(listener)

        return _remove

    def _drivers(self) -> list[dict[str, Any]]:
        data = getattr(self.coordinator, "data", None)
        raw = data.get("drivers") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return []
        return [
            _normalise_driver(str(racing_number), info)
            for racing_number, info in raw.items()
            if isinstance(info, dict)
        ]

    def _selected_driver(self) -> dict[str, Any] | None:
        if not self._selected_tla:
            return None
        return next(
            (
                driver
                for driver in self._drivers()
                if driver.get("tla") == self._selected_tla
            ),
            None,
        )

    @callback
    def _handle_coordinator_update(self, *, emit_events: bool = True) -> None:
        previous = self._snapshot
        current = self._selected_driver()
        self._snapshot = current
        if emit_events and previous is not None and current is not None:
            self._emit_changes(previous, current)
        self._notify_listeners()

    @callback
    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _emit_changes(self, previous: dict[str, Any], current: dict[str, Any]) -> None:
        old_position = previous.get("position")
        new_position = current.get("position")
        if (
            isinstance(old_position, int)
            and isinstance(new_position, int)
            and new_position != old_position
        ):
            self._fire(
                "position_gained" if new_position < old_position else "position_lost",
                previous,
                current,
            )
        if not previous.get("in_pit") and current.get("in_pit"):
            self._fire("entered_pits", previous, current)
        elif previous.get("in_pit") and not current.get("in_pit"):
            self._fire("exited_pits", previous, current)
        if not previous.get("retired") and current.get("retired"):
            self._fire("retired", previous, current)

    @callback
    def _fire(
        self,
        event_type: str,
        previous: dict[str, Any],
        current: dict[str, Any],
    ) -> None:
        self.hass.bus.async_fire(
            FAVORITE_DRIVER_EVENT,
            {
                "entry_id": self.entry_id,
                "event_type": event_type,
                "driver": current,
                "previous": previous,
                "current": current,
            },
        )
