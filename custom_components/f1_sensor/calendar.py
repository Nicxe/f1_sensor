"""F1 Season Calendar entity for Home Assistant."""

from __future__ import annotations

import datetime
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import F1BaseEntity

_LOGGER = logging.getLogger(__name__)

# Estimated session durations in minutes.
SESSION_DURATIONS: dict[str, int] = {
    "FirstPractice": 60,
    "SecondPractice": 60,
    "ThirdPractice": 60,
    "Qualifying": 60,
    "SprintQualifying": 45,
    "Sprint": 35,
    "Race": 120,
}

SESSION_LABELS: dict[str, str] = {
    "FirstPractice": "Practice 1",
    "SecondPractice": "Practice 2",
    "ThirdPractice": "Practice 3",
    "Qualifying": "Qualifying",
    "SprintQualifying": "Sprint Qualifying",
    "Sprint": "Sprint",
    "Race": "Race",
}

# Chronological order within a race weekend.
SESSION_ORDER: list[str] = [
    "FirstPractice",
    "SecondPractice",
    "ThirdPractice",
    "SprintQualifying",
    "Sprint",
    "Qualifying",
    "Race",
]


def _parse_session_datetime(
    date_str: str | None, time_str: str | None
) -> datetime.datetime | None:
    """Parse Ergast date + time strings into a UTC-aware datetime."""
    if not date_str:
        return None
    if not time_str:
        time_str = "00:00:00Z"
    iso = f"{date_str}T{time_str}".replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the F1 Season Calendar from a config entry."""
    disabled = set(entry.data.get("disabled_sensors") or [])
    if "calendar" in disabled:
        return

    data = hass.data[DOMAIN][entry.entry_id]
    race_coordinator = data.get("race_coordinator")
    if race_coordinator is None:
        return

    base = entry.data.get("sensor_name", "F1")
    async_add_entities(
        [
            F1SeasonCalendar(
                coordinator=race_coordinator,
                unique_id=f"{entry.entry_id}_f1_season_calendar",
                entry_id=entry.entry_id,
                device_name=base,
            )
        ]
    )


class F1SeasonCalendar(F1BaseEntity, CalendarEntity):
    """Calendar entity showing all F1 sessions for the current season."""

    _device_category = "race"
    _attr_icon = "mdi:calendar-month"
    _attr_translation_key = "season_calendar"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._cached_events: list[CalendarEvent] = []
        self._cached_data_id: int | None = None

    # -- availability --------------------------------------------------------

    @property
    def available(self) -> bool:
        """Calendar is available whenever the coordinator has data."""
        return self.coordinator.last_update_success

    # -- calendar interface --------------------------------------------------

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        now = datetime.datetime.now(datetime.UTC)
        events = self._build_events()
        for ev in events:
            if ev.start <= now < ev.end:
                return ev
        for ev in events:
            if ev.start > now:
                return ev
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = self._build_events()
        return [ev for ev in events if ev.end > start_date and ev.start < end_date]

    # -- internal ------------------------------------------------------------

    def _build_events(self) -> list[CalendarEvent]:
        """Build CalendarEvent list from coordinator race data.

        Results are cached and only rebuilt when coordinator data changes.
        """
        data = self.coordinator.data
        data_id = id(data)
        if data_id == self._cached_data_id and self._cached_events:
            return self._cached_events

        events: list[CalendarEvent] = []
        if not data:
            self._cached_events = events
            self._cached_data_id = data_id
            return events

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])

        for race in races:
            race_name = race.get("raceName", "Unknown Grand Prix")
            season = race.get("season", "")
            rnd = race.get("round", "")
            circuit = race.get("Circuit", {})
            loc = circuit.get("Location", {})

            location_str = ", ".join(
                filter(
                    None,
                    [
                        circuit.get("circuitName"),
                        loc.get("locality"),
                        loc.get("country"),
                    ],
                )
            )
            description = f"Round {rnd} of the {season} Formula 1 Season"

            for key in SESSION_ORDER:
                if key == "Race":
                    dt = _parse_session_datetime(race.get("date"), race.get("time"))
                else:
                    session_data = race.get(key)
                    if not session_data or not isinstance(session_data, dict):
                        continue
                    dt = _parse_session_datetime(
                        session_data.get("date"), session_data.get("time")
                    )

                if dt is None:
                    continue

                duration = SESSION_DURATIONS.get(key, 60)
                events.append(
                    CalendarEvent(
                        start=dt,
                        end=dt + datetime.timedelta(minutes=duration),
                        summary=f"{race_name} - {SESSION_LABELS[key]}",
                        description=description,
                        location=location_str,
                        uid=f"f1_{season}_{rnd}_{key}",
                    )
                )

        events.sort(key=lambda e: e.start)
        self._cached_events = events
        self._cached_data_id = data_id
        return events
