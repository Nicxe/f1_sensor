"""Regressions from the 25 October race's saved No Further Action chronology."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.util import dt as dt_util
import pytest

from custom_components.f1_sensor import live_data_models as models
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.sensor import F1InvestigationsSensor


@pytest.fixture
def race_messages():
    fixture = Path(__file__).parent / "fixtures" / "race-20261025-nfi-chronology.json"
    return json.loads(fixture.read_text())["messages"]


def build_model(hass, messages):
    coordinator = SimpleNamespace(
        hass=hass,
        data={},
        data_list=deepcopy(messages),
        last_update_success=True,
        available=True,
    )
    hass.data[DOMAIN] = {
        "entry": {
            "live_state": SimpleNamespace(is_live=True, reason="live"),
            "live_bus": SimpleNamespace(last_stream_activity_age=lambda: 0),
            "session_info_coordinator": SimpleNamespace(
                data={"Key": 11396, "Type": "Race"}
            ),
            "session_status_coordinator": SimpleNamespace(data={"Status": "Started"}),
        }
    }
    return models.InvestigationsModel(coordinator, None, "entry", None)


def first_nfi_prefix(messages):
    for index, message in enumerate(messages):
        if "CAR 5 (BOR) NO FURTHER ACTION" in message["Message"]:
            return messages[: index + 1]
    raise AssertionError("The recorded BOR NFI must be present")


def test_runtime_snapshot_handles_real_nfi_without_an_optional_entity(
    hass, race_messages
):
    model = build_model(hass, first_nfi_prefix(race_messages))
    snapshot = model.snapshot()
    assert snapshot.value == 3
    assert snapshot.attributes["no_further_action"][0]["drivers"] == ["BOR"]
    assert (
        snapshot.attributes["no_further_action"][0]["nfi_utc"] == "2026-10-25T20:25:12"
    )
    assert not hass.states.async_all()


@pytest.mark.parametrize(
    "source_elapsed, expected_nfi", [(0, 1), (299, 1), (300, 1), (301, 0)]
)
def test_runtime_nfi_expiry_preserves_five_minute_source_clock_boundary(
    hass, race_messages, source_elapsed, expected_nfi
):
    prefix = first_nfi_prefix(race_messages)
    model = build_model(hass, prefix)
    first = model.snapshot()
    unaffected = {
        key: deepcopy(first.attributes[key])
        for key in ("noted", "under_investigation", "penalties")
    }
    # Advance the existing session clock only; wall time must not expire replay decisions.
    model._session_time = dt_util.parse_datetime(prefix[-1]["Utc"]) + timedelta(
        seconds=source_elapsed
    )
    with patch.object(
        models.dt_util, "utcnow", return_value=datetime(2050, 1, 1, tzinfo=UTC)
    ):
        snapshot = model.snapshot()
    assert len(snapshot.attributes["no_further_action"]) == expected_nfi
    assert snapshot.value == first.value
    assert {key: snapshot.attributes[key] for key in unaffected} == unaffected


def test_real_chronology_matches_legacy_entity_without_mutating_other_data(
    hass, race_messages
):
    model = build_model(hass, [])
    sensor = F1InvestigationsSensor(
        model.coordinator, "legacy-reference", "entry", "F1"
    )
    original = deepcopy(race_messages)
    attributes = ("noted", "under_investigation", "no_further_action", "penalties")
    for message in race_messages:
        model.coordinator.data_list.append(deepcopy(message))
        model.coordinator.data = deepcopy(message)
        sensor._process_message(deepcopy(message))
        sensor._update_attributes()
        snapshot = model.snapshot()
        assert snapshot.value == sensor.state
        assert {key: snapshot.attributes[key] for key in attributes} == {
            key: sensor.extra_state_attributes[key] for key in attributes
        }
    assert race_messages == original


def test_non_nfi_chronology_already_works_before_the_resolution(hass, race_messages):
    model = build_model(hass, first_nfi_prefix(race_messages)[:-1])
    snapshot = model.snapshot()
    assert snapshot.value == 4
    assert snapshot.attributes["no_further_action"] == []
    assert snapshot.attributes["noted"]
    assert snapshot.attributes["under_investigation"]
    assert snapshot.attributes["penalties"]
