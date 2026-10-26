"""Track status remains usable through recorded qualifying phase changes."""

from copy import deepcopy
import json
import logging
from pathlib import Path
from types import SimpleNamespace

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import (
    SessionStatusCoordinator,
    TrackStatusCoordinator,
    _reset_replay_sensitive_coordinator_state,
)
from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
)
from custom_components.f1_sensor.live_data_models import SessionStatusModel
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager
from custom_components.f1_sensor.sensor import (
    F1SessionStatusSensor,
    F1TrackStatusSensor,
)

_LOGGER = logging.getLogger(__name__)


@pytest.fixture
def qualifying_frames():
    """Use selected original messages in their recorded stream order."""
    return json.loads(
        (Path(__file__).parent / "fixtures/us_2026_qualifying_q2_q3.json").read_text()
    )["frames"]


@pytest.fixture
def qualifying_reconnect_snapshots():
    """Reconstruct full snapshots from the recorded incremental history."""
    return json.loads(
        (
            Path(__file__).parent / "fixtures/us_2026_qualifying_reconnect.json"
        ).read_text()
    )["snapshots"]


def _setup_sources(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    session = SimpleNamespace(data={})
    status = SessionStatusCoordinator(hass, session)
    track = TrackStatusCoordinator(hass, session)
    info = DataUpdateCoordinator(hass, _LOGGER, name="session_info")
    data = {
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
        "session_status_coordinator": status,
        "track_status_coordinator": track,
        "session_info_coordinator": info,
        "live_state": SimpleNamespace(is_live=True, reason="replay"),
    }
    hass.data[DOMAIN] = {
        entry.entry_id: data,
        "no_spoiler_manager": NoSpoilerModeManager(hass),
    }
    return entry, status, track, info, data


async def _apply_frame(hass, frame, status, track, info):
    stream, payload = frame["stream"], frame["payload"]
    if stream == "SessionInfo":
        info.async_set_updated_data(payload)
        status._on_session_info_context(payload)
    elif stream == "SessionData":
        status._on_session_data_context(payload)
    elif stream == "TrackStatus":
        track._on_bus_message(payload)
    else:
        assert stream == "SessionStatus"
        status._on_bus_message(payload)
    await hass.async_block_till_done()


async def _add_sensors(hass, entry, status, track):
    sensors = (
        F1SessionStatusSensor(status, "session_status", entry.entry_id, "F1"),
        F1TrackStatusSensor(track, "track_status", entry.entry_id, "F1"),
    )
    component = EntityComponent(_LOGGER, "sensor", hass)
    await component.async_add_entities(sensors)
    await hass.async_block_till_done()
    return sensors


async def test_recorded_q2_to_q3_keeps_track_status_without_new_track_frame(
    hass, qualifying_frames
):
    """A Q3 announcement must not reinterpret Q2's finish as the session end."""
    entry, status, track, info, data = _setup_sources(hass)
    for frame in qualifying_frames[:4]:
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    owner = CardDataStore(hass, entry, data)
    assert hass.states.get(track_sensor.entity_id).state == "CLEAR"

    expected = ("break", "break", "break", "live", "finished", "finalised", "ended")
    try:
        for frame, expected_status in zip(qualifying_frames[4:], expected, strict=True):
            await _apply_frame(hass, frame, status, track, info)
            assert hass.states.get(status_sensor.entity_id).state == expected_status, (
                frame
            )
            assert hass.states.get(track_sensor.entity_id).state == (
                "CLEAR" if expected_status in {"break", "live"} else STATE_UNAVAILABLE
            ), frame
            if frame["stream"] == "SessionData":
                assert (
                    owner.snapshot("session_context")["context"]["qualifying_part"] == 3
                )
    finally:
        await owner.async_close()


@pytest.mark.parametrize(
    "duplicate",
    [
        {"Status": "Finished", "Started": "Finished"},
        {"Message": "Finished", "Started": "Finished"},
    ],
)
async def test_duplicate_q2_finish_does_not_end_announced_q3(
    hass, qualifying_frames, duplicate
):
    """A repeated status snapshot cannot move an observed finish into Q3."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in qualifying_frames[:5]:
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    await _apply_frame(hass, qualifying_frames[5], status, track, info)
    status._on_bus_message(duplicate)
    await hass.async_block_till_done()
    assert hass.states.get(status_sensor.entity_id).state == "break"
    assert hass.states.get(track_sensor.entity_id).state == "CLEAR"

    for frame in qualifying_frames[7:9]:
        await _apply_frame(hass, frame, status, track, info)
    assert hass.states.get(status_sensor.entity_id).state == "finished"
    assert hass.states.get(track_sensor.entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize("context_first", [False, True])
async def test_final_q3_reconnect_resolves_late_context_for_entity_and_projection(
    hass, qualifying_frames, context_first
):
    """Either snapshot order must resolve a genuine final Q3 status."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in qualifying_frames[:2]:
        await _apply_frame(hass, frame, status, track, info)
    if context_first:
        await _apply_frame(hass, qualifying_frames[5], status, track, info)
    await _apply_frame(hass, qualifying_frames[8], status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    model = SessionStatusModel(status, None, entry.entry_id, None)
    initial_status = "finished" if context_first else "break"
    assert hass.states.get(status_sensor.entity_id).state == initial_status
    assert model.snapshot().value == initial_status

    if not context_first:
        await _apply_frame(hass, qualifying_frames[5], status, track, info)
    assert hass.states.get(status_sensor.entity_id).state == "finished"
    assert model.snapshot().value == "finished"
    assert hass.states.get(track_sensor.entity_id).state == STATE_UNAVAILABLE


@pytest.mark.parametrize("reset_kind", ["replay", "window_end"])
async def test_qualifying_status_ownership_resets_before_next_session(
    hass, qualifying_frames, qualifying_reconnect_snapshots, reset_kind
):
    """A new session must inherit neither observed nor pending Q3 context."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in (qualifying_frames[0], qualifying_frames[5], qualifying_frames[7]):
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, _track_sensor = await _add_sensors(hass, entry, status, track)
    # The full context announces Q3's finish before its raw status arrives.
    await _apply_frame(
        hass, qualifying_reconnect_snapshots["q3_finished"], status, track, info
    )
    assert hass.states.get(status_sensor.entity_id).state == "live"

    if reset_kind == "replay":
        _reset_replay_sensitive_coordinator_state(status)
    else:
        status._handle_live_state(False, "window-ended")
    assert status.status_qualifying_part is None
    assert status.qualifying_part is None
    assert status.data is None

    await _apply_frame(hass, qualifying_frames[0], status, track, info)
    status._on_session_data_context({"Series": {"0": {"QualifyingPart": 1}}})
    status._on_bus_message(qualifying_frames[4]["payload"])
    await hass.async_block_till_done()
    assert hass.states.get(status_sensor.entity_id).state == "break"


@pytest.mark.parametrize("context_first", [False, True])
@pytest.mark.parametrize(
    ("snapshot_key", "expected_status"),
    [("q3_announced", "break"), ("q3_finished", "finished")],
)
async def test_reconnect_history_locates_finish_when_q3_transitions_were_missed(
    hass,
    qualifying_frames,
    qualifying_reconnect_snapshots,
    context_first,
    snapshot_key,
    expected_status,
):
    """Full chronology distinguishes identical Q2 and Q3 Finished snapshots."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in qualifying_frames[:5]:
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    assert hass.states.get(status_sensor.entity_id).state == "break"

    snapshot = qualifying_reconnect_snapshots[snapshot_key]
    duplicate_status = qualifying_frames[8 if expected_status == "finished" else 4]
    reconnect_frames = (
        (snapshot, duplicate_status) if context_first else (duplicate_status, snapshot)
    )
    for frame in reconnect_frames:
        await _apply_frame(hass, frame, status, track, info)
    assert status.qualifying_part == 3
    assert hass.states.get(status_sensor.entity_id).state == expected_status
    assert hass.states.get(track_sensor.entity_id).state == (
        "CLEAR" if expected_status == "break" else STATE_UNAVAILABLE
    )


@pytest.mark.parametrize(
    "missing_evidence",
    ["missing_status_time", "invalid_status_time", "missing_part_times"],
)
async def test_reconnect_without_valid_chronology_preserves_observed_q2_finish(
    hass, qualifying_frames, qualifying_reconnect_snapshots, missing_evidence
):
    """An incomplete history must not manufacture a final-session finish."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in qualifying_frames[:5]:
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    snapshot = deepcopy(qualifying_reconnect_snapshots["q3_finished"])
    payload = snapshot["payload"]
    if missing_evidence == "missing_part_times":
        for part in payload["Series"]:
            part.pop("Utc")
    elif missing_evidence == "missing_status_time":
        payload["StatusSeries"][-1].pop("Utc")
    else:
        payload["StatusSeries"][-1]["Utc"] = "invalid"
    await _apply_frame(hass, snapshot, status, track, info)
    await _apply_frame(hass, qualifying_frames[8], status, track, info)
    assert hass.states.get(status_sensor.entity_id).state == "break"
    assert hass.states.get(track_sensor.entity_id).state == "CLEAR"


async def test_reconnect_history_corrects_sparse_q3_finish_and_restores_track(
    hass, qualifying_frames, qualifying_reconnect_snapshots
):
    """Authoritative history can correct a sparse snapshot back to a Q2 break."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in (
        qualifying_frames[0],
        qualifying_frames[1],
        qualifying_frames[5],
        qualifying_frames[4],
    ):
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    model = SessionStatusModel(status, None, entry.entry_id, None)
    assert hass.states.get(status_sensor.entity_id).state == "finished"
    assert hass.states.get(track_sensor.entity_id).state == STATE_UNAVAILABLE
    assert model.snapshot().value == "finished"

    await _apply_frame(
        hass, qualifying_reconnect_snapshots["q3_announced"], status, track, info
    )
    assert status.qualifying_part == 3
    assert hass.states.get(status_sensor.entity_id).state == "break"
    assert hass.states.get(track_sensor.entity_id).state == "CLEAR"
    assert model.snapshot().value == "break"


async def test_fresh_reconnect_history_precedes_finished_snapshot_during_q2_break(
    hass, qualifying_frames, qualifying_reconnect_snapshots
):
    """A full context snapshot may arrive before the first raw status."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in (
        qualifying_frames[0],
        qualifying_frames[1],
        qualifying_reconnect_snapshots["q3_announced"],
        qualifying_frames[4],
    ):
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    assert status.qualifying_part == 3
    assert hass.states.get(status_sensor.entity_id).state == "break"
    assert hass.states.get(track_sensor.entity_id).state == "CLEAR"


@pytest.mark.parametrize(
    "invalid_evidence",
    ["missing_status_time", "invalid_status_time", "invalid_latest_part_time"],
)
async def test_invalid_reconnect_history_cannot_reopen_observed_q3_finish(
    hass, qualifying_frames, qualifying_reconnect_snapshots, invalid_evidence
):
    """An invalid latest timestamp must not select an older Q2 finish."""
    entry, status, track, info, _data = _setup_sources(hass)
    for frame in qualifying_frames[:9]:
        await _apply_frame(hass, frame, status, track, info)
    status_sensor, track_sensor = await _add_sensors(hass, entry, status, track)
    assert hass.states.get(status_sensor.entity_id).state == "finished"
    snapshot = deepcopy(qualifying_reconnect_snapshots["q3_finished"])
    payload = snapshot["payload"]
    if invalid_evidence == "invalid_latest_part_time":
        payload["Series"][-1]["Utc"] = "invalid"
    elif invalid_evidence == "missing_status_time":
        payload["StatusSeries"][-1].pop("Utc")
    else:
        payload["StatusSeries"][-1]["Utc"] = "invalid"
    await _apply_frame(hass, snapshot, status, track, info)
    assert hass.states.get(status_sensor.entity_id).state == "finished"
    assert hass.states.get(track_sensor.entity_id).state == STATE_UNAVAILABLE
