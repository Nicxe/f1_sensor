"""Replay normalization revisions and archive identity are load boundaries."""

import asyncio
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.entity_component import EntityComponent
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor import replay_mode
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.replay_mode import (
    ReplaySession,
    ReplaySessionManager,
    ReplayState,
)
from custom_components.f1_sensor.sensor import F1TrackStatusSensor
from custom_components.f1_sensor.signalr import LiveBus


def _session():
    return ReplaySession(
        year=2026,
        meeting_key=1,
        meeting_name="Test",
        session_key=2,
        session_name="Practice",
        session_type="Practice",
        path="2026/test/practice",
        start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_utc=None,
    )


def _manager(hass, tmp_path):
    manager = ReplaySessionManager(hass, "entry", AsyncMock())
    manager._cache_dir = tmp_path
    manager._download_streams = ("SessionInfo", "SessionStatus")
    return manager


def _cache(tmp_path, session, *, normalization_version=None):
    directory = tmp_path / session.unique_id
    directory.mkdir(exist_ok=True)
    frames = directory / "frames.jsonl"
    frames.write_text('{"t":123456,"s":"SessionStatus","p":{"Status":"Started"}}\n')
    metadata = {
        "cache_version": replay_mode.CACHE_VERSION,
        "session_id": session.unique_id,
        "total_frames": 1,
        "duration_ms": 123456,
        "session_started_at_ms": 123456,
        "streams": ["LapCount"],
    }
    if normalization_version is not None:
        metadata["normalization_version"] = normalization_version
    index = directory / "index.json"
    index.write_text(json.dumps(metadata))
    return frames, index


def _mock_download(hass, manager, monkeypatch, payloads):
    async def download(_url, stream, destination):
        rows = payloads.get(stream, [])
        content = "".join(
            json.dumps({"t": t, "s": stream, "p": p}) + "\n" for t, p in rows
        )
        if rows:
            await hass.async_add_executor_job(destination.write_text, content)
        return len(rows)

    mocked = AsyncMock(side_effect=download)
    monkeypatch.setattr(manager, "_download_stream_to_file", mocked)
    return mocked


async def test_old_parser_cache_is_downloaded_again_and_then_reused(
    hass, tmp_path, monkeypatch
):
    manager = _manager(hass, tmp_path)
    session = _session()
    _cache(tmp_path, session)
    download = _mock_download(
        hass,
        manager,
        monkeypatch,
        {
            "SessionInfo": [(0, {"Key": 2, "Meeting": {"Key": 1}})],
            "SessionStatus": [(123, {"Status": "Started"})],
        },
    )
    index = await manager._download_and_index_session(session)
    assert download.await_count == 2
    assert index.duration_ms == 123
    assert index.session_started_at_ms == 123
    assert (
        json.loads(index.index_file.read_text())["normalization_version"]
        == replay_mode.NORMALIZATION_VERSION
    )
    download.reset_mock()
    again = await manager._download_and_index_session(session)
    assert again.duration_ms == 123
    download.assert_not_awaited()


@pytest.mark.parametrize("first_completed", ["SessionInfo", "SessionStatus"])
async def test_equal_timestamp_order_is_independent_of_download_completion(
    hass, tmp_path, monkeypatch, first_completed
):
    manager = _manager(hass, tmp_path)
    first_done = asyncio.Event()
    payloads = {
        "SessionInfo": [{"Key": 2}, {"Meeting": {"Key": 1}}],
        "SessionStatus": [{"Status": "Started"}],
    }

    async def download(_url, stream, destination):
        if stream != first_completed:
            await first_done.wait()
        content = "".join(
            json.dumps({"t": 123, "s": stream, "p": payload}) + "\n"
            for payload in payloads[stream]
        )
        await hass.async_add_executor_job(destination.write_text, content)
        if stream == first_completed:
            first_done.set()
        return len(payloads[stream])

    monkeypatch.setattr(manager, "_download_stream_to_file", download)
    index = await manager._download_and_index_session(_session())
    rows = [json.loads(line) for line in index.frames_file.read_text().splitlines()]
    assert [(row["s"], row["p"]) for row in rows] == [
        ("SessionInfo", {"Key": 2}),
        ("SessionInfo", {"Meeting": {"Key": 1}}),
        ("SessionStatus", {"Status": "Started"}),
    ]
    assert index.archive_identity["status"] == "matched"


@pytest.mark.parametrize("failure", ["offline", "scan", "index_write"])
async def test_failed_rebuild_preserves_prior_cache_and_other_sessions(
    hass, tmp_path, monkeypatch, failure
):
    manager = _manager(hass, tmp_path)
    session = _session()
    frames, index = _cache(tmp_path, session)
    before = (frames.read_bytes(), index.read_bytes())
    other = tmp_path / "2026_3_4"
    other.mkdir()
    (other / "keep").write_text("other session")
    _mock_download(
        hass,
        manager,
        monkeypatch,
        {}
        if failure == "offline"
        else {
            "SessionInfo": [(0, {"Key": 2, "Meeting": {"Key": 1}})],
            "SessionStatus": [(123, {"Status": "Started"})],
        },
    )
    if failure == "scan":
        monkeypatch.setattr(
            manager,
            "_scan_merged_frames_sync",
            lambda *_: (_ for _ in ()).throw(RuntimeError("scan failed")),
        )
    if failure == "index_write":
        monkeypatch.setattr(
            manager,
            "_write_json_file",
            lambda *_: (_ for _ in ()).throw(OSError("disk full")),
        )
    manager._selected_session = session
    await manager.async_load_session()
    assert manager.state == ReplayState.SELECTED
    assert manager.get_loaded_index() is None
    assert manager.download_error
    assert (frames.read_bytes(), index.read_bytes()) == before
    assert (other / "keep").read_text() == "other session"
    assert sorted(p.name for p in frames.parent.iterdir()) == [
        "frames.jsonl",
        "index.json",
    ]


@pytest.mark.parametrize(
    ("payloads", "status"),
    [
        ([(0, {"Key": 2, "Meeting": {"Key": 1}})], "matched"),
        ([(0, {"Key": "2"}), (1, {"Meeting": {"Key": "1"}})], "matched"),
        ([(0, {"ArchiveStatus": {"Status": "Complete"}})], "missing"),
        ([], "missing"),
        (
            [(0, {"Key": 2, "Meeting": {"Key": 1}}), (1, {"Name": "Practice"})],
            "matched",
        ),
        ([(0, {"Key": 99})], "conflict"),
        ([(0, {"Key": 2, "Meeting": {"Key": 9}})], "conflict"),
        ([(0, {"Key": 2}), (1, {"Key": 3})], "conflict"),
    ],
)
async def test_archive_identity_checked_before_ready(
    hass, tmp_path, monkeypatch, payloads, status
):
    manager = _manager(hass, tmp_path)
    session = _session()
    _mock_download(
        hass,
        manager,
        monkeypatch,
        {
            "SessionInfo": payloads,
            "SessionStatus": [(2, {"Status": "Started"})],
        },
    )
    manager._selected_session = session
    await manager.async_load_session()
    if status == "conflict":
        assert manager.state == ReplayState.SELECTED
        assert manager.get_loaded_index() is None
        assert (
            manager._get_snapshot()["download_error_code"]
            == "archive_identity_conflict"
        )
        assert not (tmp_path / session.unique_id / "index.json").exists()
    else:
        assert manager.state == ReplayState.READY
        assert manager._get_snapshot()["archive_identity"]["status"] == status


async def test_mislabeled_cache_is_replaced_and_old_identity_revision_is_scanned(
    hass, tmp_path, monkeypatch
):
    manager = _manager(hass, tmp_path)
    session = _session()
    frames, index = _cache(
        tmp_path, session, normalization_version=replay_mode.NORMALIZATION_VERSION
    )
    data = json.loads(index.read_text())
    data["session_id"] = "2026_1_99"
    index.write_text(json.dumps(data))
    download = _mock_download(
        hass,
        manager,
        monkeypatch,
        {
            "SessionInfo": [(0, {"Key": 2, "Meeting": {"Key": 1}})],
            "SessionStatus": [(123, {"Status": "Started"})],
        },
    )
    loaded = await manager._download_and_index_session(session)
    assert download.await_count == 2
    assert loaded.archive_identity["status"] == "matched"
    data = json.loads(index.read_text())
    data.pop("identity_version")
    index.write_text(json.dumps(data))
    loaded.frames_file.write_text('{"t":0,"s":"SessionInfo","p":{"Key":99}}\n')
    download.reset_mock()
    with pytest.raises(replay_mode.ReplayArchiveError, match="identity conflicts"):
        await manager._download_and_index_session(session)
    download.assert_not_awaited()


async def test_cancelled_archive_build_removes_pending_files(
    hass, tmp_path, monkeypatch
):
    manager = _manager(hass, tmp_path)
    session = _session()
    frames, index = _cache(tmp_path, session)
    before = (frames.read_bytes(), index.read_bytes())
    entered = asyncio.Event()

    async def blocked(*_):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "_download_stream_to_file", blocked)
    task = asyncio.create_task(manager._download_and_index_session(session))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (frames.read_bytes(), index.read_bytes()) == before
    assert sorted(p.name for p in frames.parent.iterdir()) == [
        "frames.jsonl",
        "index.json",
    ]


async def test_index_publish_failure_never_pairs_old_index_with_new_frames(
    hass, tmp_path, monkeypatch
):
    manager = _manager(hass, tmp_path)
    session = _session()
    frames, index = _cache(tmp_path, session)
    before = frames.read_bytes(), index.read_bytes()
    _mock_download(
        hass, manager, monkeypatch, {"SessionStatus": [(123, {"Status": "Started"})]}
    )
    replace = Path.replace

    def fail_publication(path, target):
        if path.name == "index.json" and path.parent.name.startswith(".build-"):
            raise OSError("index publication failed")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_publication)
    with pytest.raises(OSError, match="publication failed"):
        await manager._download_and_index_session(session)
    assert (frames.read_bytes(), index.read_bytes()) == before
    assert sorted(path.name for path in frames.parent.iterdir()) == [
        "frames.jsonl",
        "index.json",
    ]


@pytest.mark.parametrize("change_session", [False, True])
async def test_superseded_load_cannot_replace_newer_cache_or_ready_index(
    hass, tmp_path, monkeypatch, change_session
):
    manager = _manager(hass, tmp_path)
    session = _session()
    manager._selected_session = session
    entered = asyncio.Event()
    release = threading.Event()
    scanner = manager._scan_merged_frames_sync
    loop = asyncio.get_running_loop()
    calls = 0

    def scan(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(5)
        return scanner(*args)

    monkeypatch.setattr(manager, "_scan_merged_frames_sync", scan)
    payloads = {"SessionStatus": [(123, {"Status": "Started"})]}
    _mock_download(hass, manager, monkeypatch, payloads)
    old = asyncio.create_task(manager.async_load_session())
    await entered.wait()
    try:
        payloads["SessionStatus"] = [(456, {"Status": "Started"})]
        if change_session:
            next_session = _session()
            next_session.session_key = 3
            manager._available_sessions = [session, next_session]
            await manager.async_select_session(next_session.unique_id)
        await manager.async_load_session()
        published = manager.get_loaded_index()
        assert published.duration_ms == 456
        release.set()
        await old
        assert manager.get_loaded_index() is published
        assert json.loads(published.index_file.read_text())["duration_ms"] == 456
        assert (
            json.loads(published.index_file.read_text())["frames_file"]
            == published.frames_file.name
        )
    finally:
        release.set()
        await old


@pytest.mark.parametrize("cancel_load", [False, True])
async def test_session_selection_waits_for_started_atomic_cache_switch(
    hass, tmp_path, monkeypatch, cancel_load
):
    manager = _manager(hass, tmp_path)
    selected = _session()
    next_session = _session()
    next_session.session_key = 3
    manager._available_sessions = [selected, next_session]
    manager._selected_session = selected
    _mock_download(
        hass, manager, monkeypatch, {"SessionStatus": [(123, {"Status": "Started"})]}
    )
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    commit = manager._commit_replay_cache_sync

    def blocked_commit(*args):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        commit(*args)

    monkeypatch.setattr(manager, "_commit_replay_cache_sync", blocked_commit)
    loading = asyncio.create_task(manager.async_load_session())
    await entered.wait()
    selecting = asyncio.create_task(
        manager.async_select_session(next_session.unique_id)
    )
    try:
        await asyncio.sleep(0)
        assert not selecting.done()
        if cancel_load:
            loading.cancel()
        release.set()
        await selecting
        await asyncio.gather(loading, return_exceptions=True)
        assert manager.selected_session is next_session
        assert manager.get_loaded_index() is None
        assert manager.state == ReplayState.SELECTED
        index = json.loads((tmp_path / selected.unique_id / "index.json").read_text())
        assert index["duration_ms"] == 123
        assert (tmp_path / selected.unique_id / index["frames_file"]).exists()
        assert not list((tmp_path / selected.unique_id).glob(".build-*"))
    finally:
        release.set()
        await asyncio.gather(loading, selecting, return_exceptions=True)


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"Key": 2}, "missing"),
        ({"Meeting": {"Key": 1}}, "missing"),
        ({"Key": True, "Meeting": {"Key": True}}, "missing"),
        ({"Key": "", "SessionKey": "  ", "MeetingKey": False}, "missing"),
        ({"Key": "02", "SessionKey": 2, "Meeting": {"Key": "01"}}, "matched"),
        ({"Key": 2, "SessionKey": 3, "MeetingKey": 1}, "conflict"),
        ({"Key": 2, "MeetingKey": 1, "Meeting": {"Key": 3}}, "conflict"),
    ],
)
def test_identity_partial_boolean_and_alias_contract(hass, tmp_path, payload, status):
    manager = _manager(hass, tmp_path)
    frames = tmp_path / "identity.jsonl"
    frames.write_text(json.dumps({"t": 0, "s": "SessionInfo", "p": payload}) + "\n")
    if status == "conflict":
        with pytest.raises(replay_mode.ReplayArchiveError):
            manager._scan_merged_frames_sync(frames, None, _session())
    else:
        assert (
            manager._scan_merged_frames_sync(frames, None, _session())[
                "archive_identity"
            ]["status"]
            == status
        )


def test_identity_does_not_require_a_meeting_key_absent_from_expected_catalog(
    hass, tmp_path
):
    manager = _manager(hass, tmp_path)
    frames = tmp_path / "identity.jsonl"
    frames.write_text('{"t":0,"s":"SessionInfo","p":{"Key":2}}\n')
    expected = SimpleNamespace(
        unique_id="session-only",
        session_key=2,
        meeting_key=None,
        start_utc=_session().start_utc,
    )
    assert (
        manager._scan_merged_frames_sync(frames, None, expected)["archive_identity"][
            "status"
        ]
        == "matched"
    )


async def test_archive_time_difference_is_diagnostic_not_identity_failure(
    hass, tmp_path, monkeypatch
):
    manager = _manager(hass, tmp_path)
    _mock_download(
        hass,
        manager,
        monkeypatch,
        {
            "SessionInfo": [
                (
                    0,
                    {
                        "Key": 2,
                        "Meeting": {"Key": 1},
                        "StartDate": "2026-01-01T02:00:00Z",
                    },
                )
            ],
        },
    )
    index = await manager._download_and_index_session(_session())
    assert index.archive_identity["status"] == "matched"
    assert index.archive_identity["start_time_offset_seconds"] == 7200


async def test_conflicting_archive_never_reaches_bus_sensor_or_events_and_recovers(
    hass, tmp_path, monkeypatch
):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry")
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    availability = LiveAvailabilityTracker()
    bus = LiveBus(hass, AsyncMock(), requested_streams={"TrackStatus", "SessionInfo"})
    controller = replay_mode.ReplayController(
        hass, "entry", AsyncMock(), bus, live_state=availability
    )
    manager = controller.session_manager
    manager._cache_dir = tmp_path
    manager._download_streams = (
        "TrackStatus",
        "RaceControlMessages",
        "SessionInfo",
        "SessionStatus",
    )
    track = f1.TrackStatusCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=availability,
    )
    race_control = f1.RaceControlCoordinator(
        hass,
        session_coord=object(),
        bus=bus,
        config_entry=entry,
        live_state=availability,
    )
    await track.async_config_entry_first_refresh()
    await race_control.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "replay_controller": controller,
        "live_state": availability,
        "live_bus": bus,
        "replay_reset_callbacks": f1._build_replay_reset_callbacks(
            bus, track, race_control
        ),
    }
    sensor = F1TrackStatusSensor(track, "track-test", "entry", "F1")
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    await component.async_add_entities([sensor])
    events = []
    unsubscribe = hass.bus.async_listen(f1._RC_LOG_EVENT, events.append)
    session = _session()
    manager._available_sessions = [session]
    payloads = {
        "TrackStatus": [(0, {"Status": "5"}), (60_000, {"Status": "1"})],
        "RaceControlMessages": [
            (
                0,
                {
                    "Messages": {
                        "0": {"Message": "WRONG SESSION", "Utc": "2026-01-01T00:00:00Z"}
                    }
                },
            )
        ],
        # A conflict discovered late must still prevent all earlier frames.
        "SessionInfo": [(100, {"Key": 99, "Meeting": {"Key": 1}})],
        "SessionStatus": [(0, {"Status": "Started"})],
    }
    _mock_download(hass, manager, monkeypatch, payloads)
    try:
        await manager.async_select_session(session.unique_id)
        await controller.async_prepare_and_load_session()
        with pytest.raises(RuntimeError, match="not ready"):
            await controller.async_play()
        assert bus.get_last_payload("TrackStatus") is None
        assert track.data is None
        assert sensor.native_value is None
        assert events == []

        payloads["SessionInfo"] = [(0, {"Key": 2, "Meeting": {"Key": 1}})]
        payloads["RaceControlMessages"] = []
        await controller.async_prepare_and_load_session()
        assert manager.state == ReplayState.READY
        assert manager._get_snapshot()["download_error_code"] is None
        await controller.async_play()
        assert track.data["Status"] == "5"
        assert sensor.native_value == "RED"
        await controller.async_stop()
        availability.set_state(True, "live-Practice")
        bus.inject_message("TrackStatus", {"Status": "1"})
        await asyncio.sleep(0)
        assert track.data["Status"] == "1"
        assert sensor.native_value == "CLEAR"
        assert events == []
    finally:
        unsubscribe()
        await controller.async_close()
        await component.async_remove_entity(sensor.entity_id)
        await track.async_close()
        await race_control.async_close()
        await bus.async_close()
