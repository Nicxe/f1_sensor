"""Regression coverage for radio history and playable clips after resets."""

from __future__ import annotations

from http import HTTPStatus
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.components.http import KEY_HASS
from homeassistant.core import State
from homeassistant.helpers.entity_component import EntityComponent
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.f1_sensor import (
    TeamRadioCoordinator,
    _build_replay_reset_callbacks,
)
from custom_components.f1_sensor.archive import F1ArchiveClient
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.replay_mode import ReplayState
from custom_components.f1_sensor.sensor import F1TeamRadioSensor
from custom_components.f1_sensor.team_radio_common import team_radio_clip_id
from custom_components.f1_sensor.team_radio_media import TeamRadioMediaView


@pytest.fixture
def captures():
    """Representative consecutive captures from the Bahrain 2026 race dump."""
    root = (
        "https://livetiming.formula1.com/static/2026/"
        "2026-10-04_Bahrain_Grand_Prix/2026-10-04_Race"
    )
    return [
        {
            "Utc": "2026-10-04T06:55:42.5759031Z",
            "RacingNumber": "16",
            "Path": "TeamRadio/LEC_16_20261004_145537.mp3",
            "_static_root": root,
        },
        {
            "Utc": "2026-10-04T06:56:14.846Z",
            "RacingNumber": "16",
            "Path": "TeamRadio/LEC_16_20261004_145606.mp3",
            "_static_root": root,
        },
        {
            "Utc": "2026-10-04T07:42:50.003Z",
            "RacingNumber": "3",
            "Path": "TeamRadio/VER_3_20261004_154219.mp3",
            "_static_root": root,
        },
    ]


@pytest.fixture
async def radio(hass, cleanup_test_entity_components):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = TeamRadioCoordinator(hass, SimpleNamespace())
    coordinator.available = True
    client = F1ArchiveClient(SimpleNamespace(), "test-token")
    client.async_get_bytes = AsyncMock(return_value=(b"ID3radio", "audio/mpeg"))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "live_state": SimpleNamespace(is_live=True, reason="replay"),
        "replay_controller": SimpleNamespace(state=ReplayState.PLAYING),
        "team_radio_coordinator": coordinator,
        "archive_client": client,
    }
    sensor = F1TeamRadioSensor(coordinator, "radio", entry.entry_id, "F1")
    sensor.entity_id = "sensor.test_team_radio"
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    hass.data.setdefault("_f1_sensor_test_entity_components", []).append(component)
    yield SimpleNamespace(
        entry=entry,
        coordinator=coordinator,
        sensor=sensor,
        component=component,
        client=client,
    )
    await coordinator.async_close()


async def _assert_history(hass, radio, expected):
    await hass.async_block_till_done()
    state = hass.states.get(radio.sensor.entity_id)
    assert state is not None
    history = state.attributes.get("history", [])
    assert [item["path"] for item in history] == [item["Path"] for item in expected]
    for item in history:
        clip_id = item["clip_url"].rsplit("/", 1)[-1].split("?", 1)[0]
        response = await TeamRadioMediaView().get(
            SimpleNamespace(app={KEY_HASS: hass}), radio.entry.entry_id, clip_id
        )
        assert response.status == HTTPStatus.OK
    return state


@pytest.mark.parametrize(
    "rebuilt_index", [None, 0, 2], ids=["empty", "backward", "forward"]
)
async def test_radio_reset_removes_unplayable_history(
    hass, radio, captures, rebuilt_index
):
    await radio.component.async_add_entities([radio.sensor])
    for capture in captures[:2]:
        radio.coordinator._on_bus_message({"Captures": [capture]})
    await _assert_history(hass, radio, list(reversed(captures[:2])))

    for reset in _build_replay_reset_callbacks(radio.coordinator):
        reset()
    state = await _assert_history(hass, radio, [])
    assert state.state == "unknown"
    assert not state.attributes.get("clip_url")

    if rebuilt_index is not None:
        capture = captures[rebuilt_index]
        radio.coordinator._on_bus_message({"Captures": [capture]})
        state = await _assert_history(hass, radio, [capture])
        assert state.attributes["sequence"] == 1


async def test_radio_startup_does_not_restore_unresolvable_clips(hass, radio):
    mock_restore_cache(
        hass,
        [
            State(
                radio.sensor.entity_id,
                "2026-10-04T06:56:14+00:00",
                {
                    "utc": "2026-10-04T06:56:14+00:00",
                    "clip_url": "/stale",
                    "history": [{"path": "stale.mp3", "clip_url": "/stale"}],
                },
            )
        ],
    )
    await radio.component.async_add_entities([radio.sensor])
    state = await _assert_history(hass, radio, [])
    assert state.state == "unknown"
    assert not state.attributes.get("clip_url")


async def test_radio_history_uses_current_store_on_startup_and_updates(
    hass, radio, captures
):
    radio.coordinator._on_bus_message({"Captures": captures[:2]})
    await radio.component.async_add_entities([radio.sensor])
    await _assert_history(hass, radio, list(reversed(captures[:2])))

    # A checkpoint can re-inject the same capture; history must remain unique.
    radio.coordinator._on_bus_message({"Captures": [captures[1]]})
    await _assert_history(hass, radio, list(reversed(captures[:2])))
    radio.coordinator._history_limit = 1
    radio.coordinator._on_bus_message({"Captures": [captures[2]]})
    await _assert_history(hass, radio, [captures[2]])


async def test_radio_historical_transcription_refreshes_without_repeating_latest(
    hass, radio, captures
):
    radio.coordinator._on_bus_message({"Captures": captures[:2]})
    await radio.component.async_add_entities([radio.sensor])
    before = await _assert_history(hass, radio, list(reversed(captures[:2])))
    radio.coordinator.set_transcription(
        team_radio_clip_id(captures[0]),
        {"status": "completed", "text": "Understood"},
    )
    after = await _assert_history(hass, radio, list(reversed(captures[:2])))
    assert after.attributes["history"][1]["transcription_text"] == "Understood"
    assert after.attributes["history"][1]["transcription_status"] == "completed"
    assert after.attributes["sequence"] == before.attributes["sequence"]
    assert after.attributes["received_at"] == before.attributes["received_at"]


async def test_radio_distinct_clips_with_same_timestamp_update_latest(
    hass, radio, captures
):
    await radio.component.async_add_entities([radio.sensor])
    first, second = captures[:2]
    second = {**second, "Utc": first["Utc"]}
    radio.coordinator._on_bus_message({"Captures": [first]})
    radio.coordinator._on_bus_message({"Captures": [second]})
    state = await _assert_history(hass, radio, [second, first])
    assert state.attributes["path"] == second["Path"]
    assert state.attributes["sequence"] == 2


async def test_radio_history_keeps_twenty_newest_playable_captures(
    hass, radio, captures
):
    batch = [
        {**captures[0], "Path": f"TeamRadio/LEC_16_{index}.mp3"} for index in range(25)
    ]
    radio.coordinator._on_bus_message({"Captures": batch})
    await radio.component.async_add_entities([radio.sensor])
    await _assert_history(hass, radio, list(reversed(batch[-20:])))
