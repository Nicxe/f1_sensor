"""Behavior tests for the season calendar platform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor import calendar as calendar_platform
from custom_components.f1_sensor.calendar import F1SeasonCalendar
from custom_components.f1_sensor.const import DOMAIN


def _coordinator(data, *, success=True):
    return SimpleNamespace(data=data, last_update_success=success)


def _entity(data) -> F1SeasonCalendar:
    return F1SeasonCalendar(_coordinator(data), "uid", "entry", "F1")


def test_parse_session_datetime_defaults_and_rejects_invalid_values() -> None:
    assert calendar_platform._parse_session_datetime("2026-09-01", None) == datetime(
        2026, 9, 1, tzinfo=UTC
    )
    assert calendar_platform._parse_session_datetime(
        "2026-09-01", "12:30:00Z"
    ) == datetime(2026, 9, 1, 12, 30, tzinfo=UTC)
    assert calendar_platform._parse_session_datetime(None, "12:30:00Z") is None
    assert calendar_platform._parse_session_datetime("bad", "time") is None


async def test_calendar_setup_honors_disabled_and_missing_coordinator(hass) -> None:
    add_entities = Mock()
    entry = SimpleNamespace(
        entry_id="entry",
        data={"sensor_name": "F1", "disabled_sensors": ["calendar"]},
        options={},
        runtime_data=None,
    )
    await calendar_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    entry.data["disabled_sensors"] = []
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    await calendar_platform.async_setup_entry(hass, entry, add_entities)
    add_entities.assert_not_called()

    hass.data[DOMAIN][entry.entry_id]["race_coordinator"] = _coordinator({})
    await calendar_platform.async_setup_entry(hass, entry, add_entities)
    added = add_entities.call_args.args[0]
    assert len(added) == 1
    assert added[0].entity_id == "calendar.f1_season_calendar"


def test_calendar_builds_sorts_filters_and_caches_events() -> None:
    now = datetime.now(UTC)
    race_date = (now + timedelta(days=2)).date().isoformat()
    past_date = (now - timedelta(days=3)).date().isoformat()
    data = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "season": "2026",
                        "round": "2",
                        "raceName": "Future Grand Prix",
                        "date": race_date,
                        "time": "14:00:00Z",
                        "FirstPractice": {"date": race_date, "time": "09:00:00Z"},
                        "SecondPractice": "invalid",
                        "ThirdPractice": {"date": "bad", "time": "bad"},
                        "SprintQualifying": {
                            "date": race_date,
                            "time": "10:30:00Z",
                        },
                        "Circuit": {
                            "circuitName": "Test Circuit",
                            "Location": {"locality": "City", "country": "Country"},
                        },
                    },
                    {
                        "season": "2026",
                        "round": "1",
                        "date": past_date,
                        "Circuit": {"Location": {}},
                    },
                ]
            }
        }
    }
    entity = _entity(data)

    events = entity._build_events()
    assert [event.summary for event in events] == [
        "Unknown Grand Prix - Race",
        "Future Grand Prix - Practice 1",
        "Future Grand Prix - Sprint Qualifying",
        "Future Grand Prix - Race",
    ]
    assert events[1].location == "Test Circuit, City, Country"
    assert events[1].uid == "f1_2026_2_FirstPractice"
    assert events[2].end - events[2].start == timedelta(minutes=45)
    assert entity._build_events() is events
    assert entity.event == events[1]
    assert entity.available is True


async def test_calendar_range_and_empty_data_behavior(hass) -> None:
    entity = _entity(None)
    assert entity._build_events() == []
    assert entity.event is None
    entity.coordinator.last_update_success = False
    assert entity.available is False

    start = datetime(2026, 9, 1, tzinfo=UTC)
    entity.coordinator.data = {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "raceName": "Grand Prix",
                        "date": "2026-09-01",
                        "time": "12:00:00Z",
                    }
                ]
            }
        }
    }
    assert (
        len(await entity.async_get_events(hass, start, start + timedelta(days=1))) == 1
    )
    assert (
        await entity.async_get_events(
            hass, start + timedelta(days=2), start + timedelta(days=3)
        )
        == []
    )
