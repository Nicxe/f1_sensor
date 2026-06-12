from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
import zlib

import pytest

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker
from custom_components.f1_sensor.replay_mode import (
    ReplayController,
    ReplaySessionManager,
)
from custom_components.f1_sensor.track_map import (
    TRACK_MAP_FALLBACK_STATE_REPLAY_V2,
    TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG,
    TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z,
    TRACK_MAP_POSITION_STREAM,
    TRACK_MAP_REPLAY_GEOMETRY_SOURCE,
    TRACK_MAP_SOURCE_LIVE,
    TRACK_MAP_SOURCE_REPLAY,
    TRACK_MAP_STATIC_GEOMETRY_SOURCE,
    TRACK_MAP_STATUS_ACTIVE,
    TRACK_MAP_STATUS_STALE,
    TrackMapPosition,
    TrackMapReplayAdapter,
    TrackMapStore,
    parse_position_z_line,
    track_map_positions_to_payload,
)

BASE_TIME = datetime(2026, 5, 3, 16, 6, 45, 695110, tzinfo=UTC)


class FakeBus:
    def __init__(self) -> None:
        self._subs: dict[str, list] = {}

    def subscribe(self, stream: str, callback):
        self._subs.setdefault(stream, []).append(callback)

        def _unsub() -> None:
            callbacks = self._subs.get(stream, [])
            if callback in callbacks:
                callbacks.remove(callback)

        return _unsub

    def emit(self, stream: str, payload: dict) -> None:
        for callback in list(self._subs.get(stream, [])):
            callback(payload)

    async def async_close(self) -> None:
        return None


class FakeTimerHandle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeLoop:
    def __init__(self) -> None:
        self.now = 0.0
        self.handles: list[FakeTimerHandle] = []

    def time(self) -> float:
        return self.now

    def call_later(self, _delay: float, _callback) -> FakeTimerHandle:
        handle = FakeTimerHandle()
        self.handles.append(handle)
        return handle


class _Response:
    status = 200

    def __init__(self, text: str) -> None:
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def text(self) -> str:
        return self._text


class _Http:
    def __init__(self, text: str) -> None:
        self._text = text
        self.get_calls: list[str] = []

    def get(self, url: str):
        self.get_calls.append(url)
        return _Response(self._text)


def _encoded_position_payload(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return base64.b64encode(compressed).decode()


def _json_stream_line(data: dict, offset: str = "00:00:04.951") -> str:
    return f'{offset}"{_encoded_position_payload(data)}"'


def _position_payload(entries: dict) -> dict:
    return {
        "Position": [
            {
                "Timestamp": "2026-05-03T16:06:45.6951105Z",
                "Entries": entries,
            }
        ]
    }


def _session_payload() -> dict:
    return {
        "Key": "101",
        "Name": "Race",
        "Type": "Race",
        "Path": "2026/Test/Race",
        "Meeting": {
            "Key": "55",
            "Name": "Test Grand Prix",
            "Circuit": {"Key": "999", "ShortName": "Test"},
        },
    }


def _static_session_payload() -> dict:
    payload = _session_payload()
    payload["Meeting"]["Circuit"] = {
        "Key": "151",
        "ShortName": "Miami",
    }
    return payload


def test_track_map_replay_adapter_feeds_store_and_geometry() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(
        store,
        bus,
        geometry_rebuild_frames=1,
        geometry_min_driver_points=1,
    )
    adapter.start()
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "1": {"Status": "OnTrack", "X": 100, "Y": 200, "Z": 0},
                    "4": {"Status": "OnTrack", "X": 150, "Y": 250, "Z": 1},
                }
            )
        )
    )

    bus.emit("SessionInfo", _session_payload())
    bus.emit(
        "DriverList",
        {
            "1": {
                "RacingNumber": "1",
                "Tla": "VER",
                "FullName": "Max Verstappen",
                "TeamColour": "#3671C6",
            }
        },
    )
    bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload(positions))

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["session"]["session_key"] == "101"
    assert snapshot["track"]["source"] == TRACK_MAP_REPLAY_GEOMETRY_SOURCE
    assert snapshot["track"]["circuit_key"] == "999"
    assert snapshot["drivers"][0]["racing_number"] == "1"
    assert snapshot["drivers"][0]["name"] == "Max Verstappen"
    assert snapshot["drivers"][0]["team_color"] == "3671C6"
    diagnostics = store.diagnostics(now=BASE_TIME + timedelta(seconds=1))
    assert diagnostics["geometry_source"] == TRACK_MAP_REPLAY_GEOMETRY_SOURCE
    assert diagnostics["circuit_key"] == "999"
    assert diagnostics["circuit_id"] is None
    assert diagnostics["fallback_state"] == TRACK_MAP_FALLBACK_STATE_REPLAY_V2

    adapter.reset_for_replay()
    assert store.snapshot(now=BASE_TIME + timedelta(seconds=1))["session"] is None


def test_track_map_replay_adapter_rejects_all_zero_ontrack_frame() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(store, bus)
    adapter.start()
    bus.emit("SessionInfo", _static_session_payload())
    bus.emit(
        "DriverList",
        {
            "1": {"RacingNumber": "1", "Tla": "VER"},
            "4": {"RacingNumber": "4", "Tla": "NOR"},
        },
    )
    bus.emit(
        TRACK_MAP_POSITION_STREAM,
        track_map_positions_to_payload(
            [
                TrackMapPosition("1", BASE_TIME, 100, 200, 0, "OnTrack"),
                TrackMapPosition("4", BASE_TIME, 300, 400, 0, "OnTrack"),
            ]
        ),
    )

    bus.emit(
        TRACK_MAP_POSITION_STREAM,
        track_map_positions_to_payload(
            [
                TrackMapPosition(
                    "1",
                    BASE_TIME + timedelta(seconds=1),
                    0,
                    0,
                    0,
                    "OnTrack",
                ),
                TrackMapPosition(
                    "4",
                    BASE_TIME + timedelta(seconds=1),
                    0,
                    0,
                    0,
                    "OnTrack",
                ),
            ]
        ),
    )

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_STALE
    assert snapshot["stale"] is True
    assert [(driver["x"], driver["y"]) for driver in snapshot["drivers"]] == [
        (100, 200),
        (300, 400),
    ]
    assert all(driver["stale"] is True for driver in snapshot["drivers"])

    bus.emit(
        TRACK_MAP_POSITION_STREAM,
        track_map_positions_to_payload(
            [
                TrackMapPosition(
                    "1",
                    BASE_TIME + timedelta(seconds=2),
                    0,
                    0,
                    0,
                    "OffTrack",
                ),
                TrackMapPosition(
                    "4",
                    BASE_TIME + timedelta(seconds=2),
                    500,
                    600,
                    0,
                    "OnTrack",
                ),
            ]
        ),
    )

    recovered = store.snapshot(now=BASE_TIME + timedelta(seconds=2))

    assert recovered["status"] == TRACK_MAP_STATUS_ACTIVE
    assert recovered["stale"] is False
    assert [(driver["x"], driver["y"]) for driver in recovered["drivers"]] == [
        (0, 0),
        (500, 600),
    ]


def test_track_map_adapter_marks_auth_live_positions_as_live_source() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(
        store,
        bus,
        position_source_resolver=lambda: TRACK_MAP_SOURCE_LIVE,
    )
    adapter.start()
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload({"1": {"Status": "OnTrack", "X": 100, "Y": 200, "Z": 7}})
        )
    )

    bus.emit("SessionInfo", _static_session_payload())
    bus.emit(
        "DriverList",
        {"1": {"RacingNumber": "1", "Tla": "VER", "TeamColour": "#3671C6"}},
    )
    bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload(positions))

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))
    diagnostics = store.diagnostics(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["source"] == TRACK_MAP_SOURCE_LIVE
    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["track"]["source"] == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert snapshot["drivers"][0]["z"] == 7
    assert diagnostics["source"] == TRACK_MAP_SOURCE_LIVE
    assert diagnostics["fallback_state"] == TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG


def test_track_map_replay_adapter_builds_geometry_from_one_driver() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(store, bus, geometry_rebuild_frames=1)
    adapter.start()
    bus.emit("SessionInfo", _session_payload())

    for index in range(4):
        positions = parse_position_z_line(
            _json_stream_line(
                _position_payload(
                    {
                        "1": {
                            "Status": "OnTrack",
                            "X": 10 + index * 10,
                            "Y": 5 + index * 5,
                            "Z": 0,
                        },
                        "4": {
                            "Status": "OnTrack",
                            "X": 1000 + index * 10,
                            "Y": 1000 + index * 5,
                            "Z": 0,
                        },
                    }
                ),
                offset=f"00:00:0{index}.000",
            )
        )
        bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload(positions))

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["track"]["points"] == [[10, 5], [20, 10], [30, 15], [40, 20]]


def test_track_map_replay_adapter_interpolates_positions_while_playing() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    store.update_session_info(_session_payload())
    adapter = TrackMapReplayAdapter(store, FakeBus())
    first = TrackMapPosition("1", BASE_TIME, 100, 50, 0, "OnTrack")
    second = TrackMapPosition(
        "1",
        BASE_TIME + timedelta(seconds=1),
        200,
        150,
        0,
        "OnTrack",
    )

    adapter._replay_state = "playing"
    adapter._set_interpolation_targets([first], 0.0)
    adapter._publish_interpolated_positions(0.0)
    adapter._set_interpolation_targets([second], 0.5)
    adapter._publish_interpolated_positions(1.05)

    driver = store.snapshot(now=BASE_TIME + timedelta(seconds=2))["drivers"][0]

    assert driver["x"] == 150
    assert driver["y"] == 100


def test_track_map_adapter_interpolates_live_positions() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    store.update_session_info(_session_payload())
    loop = FakeLoop()
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(
        store,
        bus,
        hass=SimpleNamespace(loop=loop),
        position_source_resolver=lambda: TRACK_MAP_SOURCE_LIVE,
    )
    adapter.start()
    first = TrackMapPosition("1", BASE_TIME, 100, 50, 0, "OnTrack")
    second = TrackMapPosition(
        "1",
        BASE_TIME + timedelta(seconds=1),
        200,
        150,
        0,
        "OnTrack",
    )

    bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload([first]))
    loop.now = 0.5
    bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload([second]))
    adapter._publish_interpolated_positions(1.05, source=TRACK_MAP_SOURCE_LIVE)

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=2))
    driver = snapshot["drivers"][0]

    assert snapshot["source"] == TRACK_MAP_SOURCE_LIVE
    assert driver["x"] == 150
    assert driver["y"] == 100


def test_track_map_replay_adapter_resets_interpolation_on_source_switch() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    store.update_session_info(_session_payload())
    source = TRACK_MAP_SOURCE_LIVE
    adapter = TrackMapReplayAdapter(
        store,
        FakeBus(),
        position_source_resolver=lambda: source,
    )
    first = TrackMapPosition("1", BASE_TIME, 100, 50, 0, "OnTrack")
    replay_position = TrackMapPosition(
        "1",
        BASE_TIME + timedelta(seconds=1),
        200,
        150,
        0,
        "OnTrack",
    )

    adapter._set_interpolation_targets([first], 0.0, source=TRACK_MAP_SOURCE_LIVE)
    adapter._publish_interpolated_positions(0.0, source=TRACK_MAP_SOURCE_LIVE)
    source = TRACK_MAP_SOURCE_REPLAY
    adapter._replay_state = "playing"
    adapter._reset_interpolation_if_source_changed(source)
    adapter._set_interpolation_targets([replay_position], 0.5, source=source)
    adapter._publish_interpolated_positions(0.5, source=source)

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=2))
    driver = snapshot["drivers"][0]

    assert snapshot["source"] == TRACK_MAP_SOURCE_REPLAY
    assert driver["x"] == 200
    assert driver["y"] == 150


@pytest.mark.asyncio
async def test_track_map_replay_adapter_preloads_geometry_from_replay_cache(
    tmp_path,
) -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    store.update_session_info(_session_payload())
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(store, bus, geometry_rebuild_frames=1)
    adapter.start()
    frames_file = tmp_path / "frames.jsonl"
    lines = []
    for index in range(4):
        positions = parse_position_z_line(
            _json_stream_line(
                _position_payload(
                    {
                        "1": {
                            "Status": "OnTrack",
                            "X": 10 + index * 10,
                            "Y": 5 + index * 5,
                            "Z": 0,
                        },
                        "4": {
                            "Status": "OnTrack",
                            "X": 1000 + index * 10,
                            "Y": 1000 + index * 5,
                            "Z": 0,
                        },
                    }
                ),
                offset=f"00:00:0{index}.000",
            )
        )
        lines.append(
            json.dumps(
                {
                    "t": index * 1000,
                    "s": TRACK_MAP_POSITION_STREAM,
                    "p": track_map_positions_to_payload(positions),
                }
            )
        )
    frames_file.write_text("\n".join(lines), encoding="utf-8")

    await adapter.async_prepare_replay_index(SimpleNamespace(frames_file=frames_file))
    bus.emit(
        TRACK_MAP_POSITION_STREAM,
        track_map_positions_to_payload(
            parse_position_z_line(
                _json_stream_line(
                    _position_payload(
                        {
                            "1": {"Status": "OnTrack", "X": 999, "Y": 999, "Z": 0},
                        }
                    )
                )
            )
        ),
    )

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["track"]["source"] == TRACK_MAP_REPLAY_GEOMETRY_SOURCE
    assert snapshot["track"]["circuit_key"] == "999"
    assert snapshot["track"]["points"] == [[10, 5], [20, 10], [30, 15], [40, 20]]


@pytest.mark.asyncio
async def test_track_map_replay_adapter_prefers_static_geometry_when_available(
    tmp_path,
) -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    store.update_session_info(_static_session_payload())
    adapter = TrackMapReplayAdapter(store, FakeBus(), geometry_rebuild_frames=1)
    frames_file = tmp_path / "frames.jsonl"
    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "1": {"Status": "OnTrack", "X": 10, "Y": 5, "Z": 0},
                    "4": {"Status": "OnTrack", "X": 20, "Y": 10, "Z": 0},
                }
            )
        )
    )
    frames_file.write_text(
        json.dumps(
            {
                "t": 0,
                "s": TRACK_MAP_POSITION_STREAM,
                "p": track_map_positions_to_payload(positions),
            }
        ),
        encoding="utf-8",
    )

    await adapter.async_prepare_replay_index(SimpleNamespace(frames_file=frames_file))

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))
    assert snapshot["track"]["source"] == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert snapshot["track"]["circuit_key"] == "151"
    assert snapshot["track"]["points"][0] == snapshot["track"]["points"][-1]
    assert (
        store.diagnostics(now=BASE_TIME + timedelta(seconds=1))["fallback_state"]
        == TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG
    )


def test_track_map_replay_adapter_does_not_replace_static_geometry() -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(store, bus, geometry_rebuild_frames=1)
    adapter.start()
    bus.emit("SessionInfo", _static_session_payload())

    for index in range(4):
        positions = parse_position_z_line(
            _json_stream_line(
                _position_payload(
                    {
                        "1": {
                            "Status": "OnTrack",
                            "X": 1000 + index * 10,
                            "Y": 1000 + index * 20,
                            "Z": 0,
                        },
                    }
                ),
                offset=f"00:00:0{index}.000",
            )
        )
        bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload(positions))

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["track"]["source"] == TRACK_MAP_STATIC_GEOMETRY_SOURCE
    assert snapshot["track"]["circuit_key"] == "151"
    assert (
        store.diagnostics(now=BASE_TIME + timedelta(seconds=1))["fallback_state"]
        == TRACK_MAP_FALLBACK_STATE_STATIC_CATALOG
    )


def test_track_map_replay_adapter_handles_insufficient_position_z_for_geometry() -> (
    None
):
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(
        store,
        bus,
        geometry_rebuild_frames=1,
        geometry_min_driver_points=4,
    )
    adapter.start()
    bus.emit("SessionInfo", _session_payload())

    positions = parse_position_z_line(
        _json_stream_line(
            _position_payload(
                {
                    "1": {"Status": "OnTrack", "X": 100, "Y": 200},
                    "4": {"Status": "OffTrack", "X": 0, "Y": 0},
                }
            )
        )
    )
    bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload(positions))

    snapshot = store.snapshot(now=BASE_TIME + timedelta(seconds=1))

    assert snapshot["status"] == TRACK_MAP_STATUS_ACTIVE
    assert snapshot["track"] is None
    assert snapshot["drivers"][0]["z"] is None
    assert (
        store.diagnostics(now=BASE_TIME + timedelta(seconds=1))["fallback_state"]
        == TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z
    )


def test_track_map_replay_adapter_updates_replay_state_metadata() -> None:
    store = TrackMapStore("entry-1")
    bus = FakeBus()
    listeners = []
    session_manager = SimpleNamespace(
        add_listener=lambda callback: listeners.append(callback) or (lambda: None),
    )
    adapter = TrackMapReplayAdapter(
        store,
        bus,
        replay_controller=SimpleNamespace(session_manager=session_manager),
    )
    adapter.start()

    listeners[0]({"state": "paused"})

    assert store.snapshot(now=BASE_TIME)["replay_state"] == "paused"


@pytest.mark.asyncio
async def test_replay_controller_prepares_track_map_replay_index(
    hass, tmp_path
) -> None:
    calls = []
    adapter = SimpleNamespace(
        async_prepare_replay_index=lambda index: calls.append(index) or None,
    )
    hass.data.setdefault(DOMAIN, {})["entry-1"] = {
        "track_map_replay_adapter": adapter,
    }
    controller = ReplayController(
        hass,
        "entry-1",
        _Http(""),  # type: ignore[arg-type]
        FakeBus(),
        live_state=LiveAvailabilityTracker(),
    )
    index = SimpleNamespace(frames_file=tmp_path / "frames.jsonl")

    await controller._prepare_track_map_replay_index(index)

    assert calls == [index]


@pytest.mark.asyncio
async def test_replay_manager_downloads_position_z_with_track_map_decoder(hass) -> None:
    line = _json_stream_line(
        _position_payload({"63": {"Status": "OnTrack", "X": 10, "Y": 20, "Z": 2}})
    )
    http = _Http(line)
    manager = ReplaySessionManager(hass, "entry-1", http)  # type: ignore[arg-type]

    frames = await manager._download_stream(
        "https://livetiming.formula1.com/static/test/Position.z.jsonStream",
        TRACK_MAP_POSITION_STREAM,
    )

    assert http.get_calls
    assert len(frames) == 1
    assert frames[0].timestamp_ms == 4951
    assert frames[0].stream == TRACK_MAP_POSITION_STREAM
    assert frames[0].payload["positions"][0]["racing_number"] == "63"
    assert frames[0].payload["positions"][0]["x"] == 10


@pytest.mark.asyncio
async def test_replay_stop_resets_track_map_store(hass) -> None:
    store = TrackMapStore("entry-1", stale_after=timedelta(days=30))
    bus = FakeBus()
    adapter = TrackMapReplayAdapter(store, bus, geometry_rebuild_frames=1)
    adapter.start()
    positions = parse_position_z_line(
        _json_stream_line(_position_payload({"16": {"X": 300, "Y": 400}}))
    )
    bus.emit("SessionInfo", _session_payload())
    bus.emit(TRACK_MAP_POSITION_STREAM, track_map_positions_to_payload(positions))
    assert store.snapshot(now=BASE_TIME)["drivers"]

    controller = ReplayController(
        hass,
        "entry-1",
        _Http(""),  # type: ignore[arg-type]
        bus,
        live_state=LiveAvailabilityTracker(),
    )
    hass.data.setdefault(DOMAIN, {})["entry-1"] = {
        "track_map_replay_adapter": adapter,
    }

    await controller.async_stop()

    snapshot = store.snapshot(now=BASE_TIME)
    assert snapshot["session"] is None
    assert snapshot["drivers"] == []
