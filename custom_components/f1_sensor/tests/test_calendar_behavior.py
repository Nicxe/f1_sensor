"""Behavior tests for the season calendar platform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from homeassistant.components.calendar.const import DATA_COMPONENT
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.f1_sensor import calendar as calendar_platform
from custom_components.f1_sensor.calendar import F1SeasonCalendar
from custom_components.f1_sensor.const import DOMAIN


def _coordinator(data, *, success=True):
    return SimpleNamespace(data=data, last_update_success=success)


def _entity(data) -> F1SeasonCalendar:
    return F1SeasonCalendar(_coordinator(data), "uid", "entry", "F1")


@pytest.mark.parametrize("time", [None, "", " ", "bad", "24:00:00Z", "12:00:00"])
def test_calendar_does_not_invent_a_start_for_missing_or_invalid_time(time) -> None:
    assert calendar_platform._parse_session_datetime("2026-09-01", time) is None


def test_parse_session_datetime_preserves_published_times() -> None:
    assert calendar_platform._parse_session_datetime(
        "2026-09-01", "00:00:00Z"
    ) == datetime(2026, 9, 1, tzinfo=UTC)
    assert calendar_platform._parse_session_datetime(
        "2026-09-01", "12:30:00Z"
    ) == datetime(2026, 9, 1, 12, 30, tzinfo=UTC)
    assert calendar_platform._parse_session_datetime(None, "12:30:00Z") is None
    assert calendar_platform._parse_session_datetime("bad", "time") is None
    assert calendar_platform._parse_session_datetime("2026-02-30", "12:00:00Z") is None
    assert calendar_platform._parse_session_datetime(
        "2026-09-01", "15:30:00+03:00"
    ) == datetime(2026, 9, 1, 12, 30, tzinfo=UTC)


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
        "Future Grand Prix - Practice 1",
        "Future Grand Prix - Sprint Qualifying",
        "Future Grand Prix - Race",
    ]
    assert events[0].location == "Test Circuit, City, Country"
    assert events[0].uid == "f1_2026_2_FirstPractice"
    assert events[1].end - events[1].start == timedelta(minutes=45)
    assert entity._build_events() is events
    assert entity.event == events[0]
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


async def test_calendar_unknown_then_published_and_moved_start_keeps_identity(
    hass, freezer
) -> None:
    freezer.move_to("2026-10-24T22:00:00Z")
    race = {"season": "2026", "round": "1", "date": "2026-10-25"}
    entity = _entity({"MRData": {"RaceTable": {"Races": [race]}}})
    zone = ZoneInfo("Europe/Stockholm")
    start = datetime(2026, 10, 25, tzinfo=zone)
    end = datetime(2026, 10, 26, tzinfo=zone)
    assert await entity.async_get_events(hass, start, end) == []
    assert entity.event is None
    for time in ("00:00:00Z", "02:30:00Z"):
        entity.coordinator.data = {
            "MRData": {"RaceTable": {"Races": [{**race, "time": time}]}}
        }
        events = await entity.async_get_events(hass, start, end)
        assert len(events) == 1
        assert events[0].uid == "f1_2026_1_Race"
        assert events[0].start == datetime.fromisoformat(f"2026-10-25T{time}")
        assert entity.event == events[0]


@pytest.mark.parametrize(("time", "expected_calls"), [(None, 0), ("00:00:00Z", 1)])
async def test_calendar_automation_only_fires_for_a_published_midnight(
    hass, freezer, time, expected_calls
) -> None:
    """Exercise HA's calendar trigger, including a genuine midnight control."""
    freezer.move_to("2026-10-24T23:55:00Z")
    await hass.config.async_set_time_zone("Europe/Stockholm")
    assert await async_setup_component(hass, "calendar", {})
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="Schedule"
    )
    coordinator.async_set_updated_data(
        {
            "MRData": {
                "RaceTable": {
                    "Races": [
                        {
                            "season": "2026",
                            "round": "1",
                            "date": "2026-10-25",
                            "time": time,
                        }
                    ]
                }
            }
        }
    )
    entity = F1SeasonCalendar(coordinator, "calendar_date_test", "entry", "F1")
    await hass.data[DATA_COMPONENT].async_add_entities([entity])
    calls = []

    async def record(call):
        calls.append(call)

    hass.services.async_register("test", "record", record)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": "published_calendar_start",
                    "alias": "Published calendar start",
                    "triggers": [
                        {
                            "trigger": "calendar",
                            "entity_id": entity.entity_id,
                            "event": "start",
                        }
                    ],
                    "actions": [{"action": "test.record"}],
                }
            ]
        },
    )
    await hass.async_block_till_done()
    freezer.move_to("2026-10-25T00:01:00Z")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert len(calls) == expected_calls
    await hass.services.async_call(
        "automation",
        "turn_off",
        {"entity_id": "automation.published_calendar_start"},
        blocking=True,
    )
    await hass.data[DATA_COMPONENT]._async_reset()
