"""Keep off-season dashboards useful without changing the API's season data."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace

from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor.binary_sensor import F1RaceWeekSensor
from custom_components.f1_sensor.calendar import F1SeasonCalendar
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.next_race import resolve_next_race
from custom_components.f1_sensor.sensor import F1NextRaceSensor
from custom_components.f1_sensor.static_data_models import (
    CurrentSeasonModel,
    NextRaceModel,
    TrackTimeModel,
)

_LOGGER = logging.getLogger(__name__)
_OFF_SEASON = datetime(2026, 12, 14, 12, tzinfo=UTC)
_PRELIMINARY_START = datetime(2027, 3, 14, 15, tzinfo=UTC)
_SOURCE_URL = "https://www.formula1.com/en/racing/2027/bahrain"


def _race(*, date="2026-12-13", season="2026", time="15:00:00Z") -> dict:
    """An API race whose final date may differ from the published calendar."""
    return {
        "season": season,
        "round": "23",
        "raceName": "API Grand Prix",
        "date": date,
        "time": time,
        "Circuit": {
            "circuitId": "yas_marina",
            "circuitName": "Yas Marina Circuit",
            "Location": {"locality": "Abu Dhabi", "country": "UAE"},
        },
    }


def _payload(*, season="2026", races=None) -> dict:
    return {
        "MRData": {
            "RaceTable": {
                "season": season,
                "Races": [_race()] if races is None else races,
            }
        }
    }


@pytest.mark.parametrize(
    ("now", "expected_source"),
    [
        (datetime(2026, 12, 13, 14, tzinfo=UTC), "api"),
        (datetime(2026, 12, 13, 17, 59, 59, tzinfo=UTC), "api"),
        (datetime(2026, 12, 13, 18, tzinfo=UTC), "fallback"),
    ],
)
def test_final_race_keeps_existing_three_hour_grace(now, expected_source) -> None:
    start, race = resolve_next_race(_payload(), now=now)

    assert race is not None
    if expected_source == "api":
        assert race["raceName"] == "API Grand Prix"
        assert start == datetime(2026, 12, 13, 15, tzinfo=UTC)
    else:
        assert race["season"] == "2027"
        assert start == _PRELIMINARY_START


def test_changed_finale_date_still_takes_precedence_over_fallback() -> None:
    payload = _payload(races=[_race(date="2026-12-20")])

    start, race = resolve_next_race(payload, now=_OFF_SEASON)

    assert start == datetime(2026, 12, 20, 15, tzinfo=UTC)
    assert race["raceName"] == "API Grand Prix"


@pytest.mark.parametrize("season", ["2026", "2027"])
def test_empty_api_schedule_can_use_reserve_across_new_year(season) -> None:
    payload = _payload(season=season, races=[])

    start, race = resolve_next_race(payload, now=datetime(2027, 1, 1, tzinfo=UTC))

    assert start == _PRELIMINARY_START
    assert race["raceName"] == "Bahrain Grand Prix"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"MRData": None},
        {"MRData": {"RaceTable": None}},
        {"MRData": {"RaceTable": {"season": "2026"}}},
        _payload(season="2025", races=[]),
        _payload(season="2028", races=[]),
        _payload(season="unknown", races=[]),
        _payload(races=[{"season": "2026", "date": "bad"}]),
        _payload(races=[_race(date="2025-12-13")]),
        _payload(races=[None]),
        _payload(races={}),
    ],
)
def test_unavailable_malformed_or_other_season_never_invents_next_race(payload) -> None:
    assert resolve_next_race(payload, now=datetime(2027, 1, 1, tzinfo=UTC)) == (
        None,
        None,
    )


@pytest.mark.parametrize("season", ["2026", "2027"])
def test_empty_calendar_before_new_year_does_not_prove_season_has_ended(season) -> None:
    assert resolve_next_race(_payload(season=season, races=[]), now=_OFF_SEASON) == (
        None,
        None,
    )


def test_reserve_is_provisional_has_location_and_no_fabricated_sessions() -> None:
    payload = _payload()
    original = deepcopy(payload)

    start, race = resolve_next_race(payload, now=_OFF_SEASON)

    assert start == _PRELIMINARY_START
    assert race["season"] == "2027"
    assert race["round"] == "1"
    assert race["date"] == "2027-03-14"
    assert race["time"] == "15:00:00Z"
    assert race["Circuit"]["circuitId"] == "bahrain"
    assert race["Circuit"]["circuitName"] == "Bahrain International Circuit"
    assert race["Circuit"]["Location"]["locality"] == "Sakhir"
    assert race["Circuit"]["Location"]["country"] == "Bahrain"
    assert race["schedule_source"] == "official_calendar_fallback"
    assert race["race_start_estimated"] is True
    assert race["schedule_source_url"] == _SOURCE_URL
    assert not any(
        key in race
        for key in (
            "FirstPractice",
            "SecondPractice",
            "ThirdPractice",
            "Qualifying",
            "SprintQualifying",
            "Sprint",
        )
    )
    assert payload == original

    race["Circuit"]["Location"]["locality"] = "Changed by a consumer"
    _, next_selection = resolve_next_race(payload, now=_OFF_SEASON)
    assert next_selection["Circuit"]["Location"]["locality"] == "Sakhir"


@pytest.mark.parametrize(
    ("now", "available"),
    [
        (_PRELIMINARY_START + timedelta(hours=3) - timedelta(seconds=1), True),
        (_PRELIMINARY_START + timedelta(hours=3), False),
        (datetime(2028, 1, 1, tzinfo=UTC), False),
    ],
)
def test_reserve_expires_after_its_race_grace_window(now, available) -> None:
    start, race = resolve_next_race(_payload(), now=now)

    assert (race is not None) is available
    assert start == (_PRELIMINARY_START if available else None)


def test_api_race_with_updated_date_and_time_replaces_the_reserve() -> None:
    api_race = _race(date="2027-03-21", season="2027", time="16:00:00Z")
    payload = _payload(season="2027", races=[api_race])
    original = deepcopy(payload)

    start, selected = resolve_next_race(payload, now=datetime(2027, 1, 2, tzinfo=UTC))

    assert start == datetime(2027, 3, 21, 16, tzinfo=UTC)
    assert selected["raceName"] == "API Grand Prix"
    assert payload == original


def test_published_2027_calendar_supersedes_bridge_after_moved_opener() -> None:
    payload = _payload(season="2027", races=[_race(date="2027-02-28", season="2027")])

    assert resolve_next_race(payload, now=datetime(2027, 3, 1, tzinfo=UTC)) == (
        None,
        None,
    )


async def test_sensor_and_card_projection_share_fallback_then_return_to_api(
    hass, monkeypatch, cleanup_test_entity_components
) -> None:
    monkeypatch.setattr(dt_util, "utcnow", lambda: _OFF_SEASON)
    await hass.config.async_set_time_zone("Europe/Stockholm")
    entry_id = "offseason"
    hass.data.setdefault(DOMAIN, {})[entry_id] = {}
    coordinator = DataUpdateCoordinator(hass, _LOGGER, name="Off-season test")
    coordinator.async_set_updated_data(_payload())
    sensor = F1NextRaceSensor(coordinator, f"{entry_id}_next_race", entry_id, "F1")
    component = EntityComponent(_LOGGER, "sensor", hass)
    hass.data.setdefault("_f1_sensor_test_entity_components", []).append(component)
    await component.async_add_entities([sensor])
    await hass.async_block_till_done()

    snapshot = NextRaceModel(coordinator, None, entry_id, None).snapshot()
    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state == "2027-03-14T15:00:00+00:00"
    assert snapshot.value == state.state
    for key, value in snapshot.attributes.items():
        assert state.attributes[key] == value
    assert state.attributes["race_start_local"] == "2027-03-14T18:00:00+03:00"
    assert state.attributes["race_start_estimated"] is True
    assert state.attributes["schedule_source"] == "official_calendar_fallback"
    assert state.attributes["schedule_source_url"] == _SOURCE_URL
    assert state.attributes["first_practice_start_utc"] is None
    assert state.attributes["qualifying_start_utc"] is None

    api_race = _race(date="2027-03-21", season="2027", time="16:00:00Z")
    coordinator.async_set_updated_data(_payload(season="2027", races=[api_race]))
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state.state == "2027-03-21T16:00:00+00:00"
    assert state.attributes["race_name"] == "API Grand Prix"
    assert state.attributes["schedule_source"] == "jolpica"
    assert state.attributes["race_start_estimated"] is False
    assert state.attributes["schedule_source_url"] is None


async def test_track_time_and_days_until_race_use_same_reserve(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(dt_util, "utcnow", lambda: _OFF_SEASON)
    await hass.config.async_set_time_zone("Europe/Stockholm")
    coordinator = SimpleNamespace(hass=hass, data=_payload(), last_update_success=True)
    track = TrackTimeModel(coordinator, None, "offseason", None)
    week = F1RaceWeekSensor(coordinator, "week", "offseason", "F1")

    assert track.available is True
    assert track.extra_state_attributes["timezone"] == "Asia/Bahrain"
    assert track.extra_state_attributes["circuit_locality"] == "Sakhir"
    assert week.is_on is False
    assert week.extra_state_attributes["next_race_name"] == "Bahrain Grand Prix"
    assert week.extra_state_attributes["days_until_next_race"] == 90
    assert week.extra_state_attributes["race_start_estimated"] is True
    assert (
        week.extra_state_attributes["schedule_source"] == "official_calendar_fallback"
    )
    assert week.extra_state_attributes["schedule_source_url"] == _SOURCE_URL


def test_reserve_does_not_display_previous_circuit_history(hass, monkeypatch) -> None:
    monkeypatch.setattr(dt_util, "utcnow", lambda: _OFF_SEASON)
    hass.data.setdefault(DOMAIN, {})["offseason"] = {
        "next_race_history_coordinator": SimpleNamespace(
            data={"defending_winner": {"name": "Previous circuit winner"}}
        )
    }
    coordinator = SimpleNamespace(hass=hass, data=_payload(), last_update_success=True)

    snapshot = NextRaceModel(coordinator, None, "offseason", None).snapshot()

    assert snapshot.attributes["circuit_name"] == "Bahrain International Circuit"
    assert snapshot.attributes.get("defending_winner") is None


def test_fallback_selection_leaves_raw_season_and_calendar_unchanged(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(dt_util, "utcnow", lambda: _OFF_SEASON)
    payload = _payload()
    original = deepcopy(payload)
    coordinator = SimpleNamespace(hass=hass, data=payload, last_update_success=True)

    next_race = NextRaceModel(coordinator, None, "offseason", None).snapshot()
    season = CurrentSeasonModel(coordinator, None, "offseason", None).snapshot()
    calendar = F1SeasonCalendar(coordinator, "calendar", "offseason", "F1")

    assert next_race.attributes["season"] == "2027"
    assert season.value == 1
    assert season.attributes["season"] == "2026"
    assert season.attributes["races"][0]["raceName"] == "API Grand Prix"
    events = calendar._build_events()
    assert len(events) == 1
    assert events[0].summary == "API Grand Prix - Race"
    assert events[0].start == datetime(2026, 12, 13, 15, tzinfo=UTC)
    assert payload == original


def _api_opener(*, date="2027-03-14", circuit_id="bahrain", time=None) -> dict:
    race = _race(date=date, season="2027", time=time)
    race["round"] = "1"
    race["Circuit"]["circuitId"] = circuit_id
    return race


@pytest.mark.parametrize("default_time", ["00:00:00Z", "23:59:59Z"])
def test_date_only_finale_cannot_activate_fallback_on_race_day(default_time) -> None:
    payload = _payload(races=[_race(time=None)])
    now = datetime(2026, 12, 13, 3, tzinfo=UTC)

    start, race = resolve_next_race(payload, now=now, default_time=default_time)

    if default_time == "00:00:00Z":
        assert (start, race) == (None, None)
    else:
        assert race["raceName"] == "API Grand Prix"
        assert start == datetime(2026, 12, 13, 23, 59, 59, tzinfo=UTC)


@pytest.mark.parametrize("default_time", ["00:00:00Z", "23:59:59Z"])
def test_date_only_finale_allows_fallback_after_conservative_grace(
    default_time,
) -> None:
    payload = _payload(races=[_race(time=None)])
    now = datetime(2026, 12, 14, 2, 59, 59, tzinfo=UTC)

    start, race = resolve_next_race(payload, now=now, default_time=default_time)

    assert start == _PRELIMINARY_START
    assert race["schedule_source"] == "official_calendar_fallback"


@pytest.mark.parametrize(
    "now",
    [datetime(2027, 1, 2, tzinfo=UTC), datetime(2027, 3, 14, 12, tzinfo=UTC)],
)
def test_matching_api_opener_without_time_retains_approved_provisional_target(
    hass, monkeypatch, now
) -> None:
    monkeypatch.setattr(dt_util, "utcnow", lambda: now)
    payload = _payload(season="2027", races=[_api_opener()])
    original = deepcopy(payload)
    coordinator = SimpleNamespace(hass=hass, data=payload, last_update_success=True)

    start, race = resolve_next_race(payload, now=now)
    snapshot = NextRaceModel(coordinator, None, "offseason", None).snapshot()

    assert start == _PRELIMINARY_START
    assert race["raceName"] == "API Grand Prix"
    assert snapshot.value == "2027-03-14T15:00:00+00:00"
    assert snapshot.attributes["schedule_source"] == "jolpica"
    assert snapshot.attributes["race_start_estimated"] is True
    assert payload == original

    coordinator.data = _payload(season="2027", races=[_api_opener(time="16:00:00Z")])
    confirmed = NextRaceModel(coordinator, None, "offseason", None).snapshot()
    assert confirmed.value == "2027-03-14T16:00:00+00:00"
    assert confirmed.attributes["race_start_estimated"] is False
    assert confirmed.attributes["schedule_source"] == "jolpica"


@pytest.mark.parametrize(
    ("date", "circuit_id"),
    [("2027-03-21", "bahrain"), ("2027-03-14", "yas_marina")],
)
def test_other_date_only_api_race_uses_normal_default_with_estimate_disclosure(
    hass, monkeypatch, date, circuit_id
) -> None:
    monkeypatch.setattr(dt_util, "utcnow", lambda: _OFF_SEASON)
    payload = _payload(
        season="2027", races=[_api_opener(date=date, circuit_id=circuit_id)]
    )
    original = deepcopy(payload)
    coordinator = SimpleNamespace(hass=hass, data=payload, last_update_success=True)

    snapshot = NextRaceModel(coordinator, None, "offseason", None).snapshot()

    assert snapshot.value == f"{date}T00:00:00+00:00"
    assert snapshot.attributes["circuit_id"] == circuit_id
    assert snapshot.attributes["schedule_source"] == "jolpica"
    assert snapshot.attributes["race_start_estimated"] is True
    assert payload == original
