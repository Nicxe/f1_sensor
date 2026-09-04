"""Branch coverage for track-map geometry and adapter safeguards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor.track_map import (
    TRACK_MAP_FALLBACK_STATE_CUSTOM_GEOMETRY,
    TRACK_MAP_FALLBACK_STATE_NO_SESSION,
    TRACK_MAP_FALLBACK_STATE_REPLAY_V2,
    TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z,
    TRACK_MAP_POSITION_STREAM,
    TRACK_MAP_REPLAY_GEOMETRY_SOURCE,
    TrackGeometry,
    TrackMapBounds,
    TrackMapPosition,
    TrackMapReplayAdapter,
    TrackMapSessionMetadata,
    TrackMapStore,
    _bounds_from_points,
    _coerce_int,
    _downsample_points,
    _extract_driver_list_payload,
    _geometry_heading,
    _location_context_confidence,
    _location_description,
    _normalize_racing_number,
    _parse_utc,
    _position_geometry_context,
    _session_metadata_from_payload,
    _split_geometry_position_segments,
    _thin_geometry_points,
    _track_map_fallback_state,
    track_map_positions_to_payload,
)

NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def _position(
    racing_number: str,
    x: int,
    y: int,
    *,
    seconds: int = 0,
    status: str = "OnTrack",
) -> TrackMapPosition:
    return TrackMapPosition(
        racing_number,
        NOW + timedelta(seconds=seconds),
        x,
        y,
        0,
        status,
    )


def test_track_map_numeric_metadata_and_fallback_helpers() -> None:
    assert _downsample_points(((0, 0),), 0) == ()
    assert _downsample_points(((0, 0), (1, 1)), 1) == ((0, 0),)
    assert _bounds_from_points([]) is None
    assert _normalize_racing_number(True) is None
    assert _normalize_racing_number(0) is None
    assert _normalize_racing_number(4) == "4"
    assert _coerce_int(True) is None
    assert _coerce_int(4.0) == 4
    assert _coerce_int(4.2) is None
    assert _coerce_int(" ") is None
    assert _coerce_int("bad") is None
    assert _coerce_int([]) is None
    assert _extract_driver_list_payload({"DriverList": {"4": {}}}) == {"4": {}}
    assert _extract_driver_list_payload({"Lines": {"4": {}}}) == {"4": {}}
    assert _session_metadata_from_payload(None) is None
    metadata = _session_metadata_from_payload(
        {
            "SessionInfo": {
                "Key": 10,
                "Name": "Race",
                "Meeting": {"Circuit": {"Key": 151, "ShortName": "Miami"}},
            }
        }
    )
    assert metadata.session_key == "10"
    assert metadata.circuit_short_name == "Miami"
    assert _parse_utc(datetime(2026, 9, 1, 12)) == NOW
    assert _parse_utc(" ", default=NOW) == NOW
    assert _parse_utc("bad", default=NOW) == NOW

    assert _track_map_fallback_state(None, None) == TRACK_MAP_FALLBACK_STATE_NO_SESSION
    session = TrackMapSessionMetadata(session_key="session")
    assert _track_map_fallback_state(session, None) == (
        TRACK_MAP_FALLBACK_STATE_WAITING_FOR_REPLAY_POSITION_Z
    )
    replay_geometry = TrackGeometry(
        points=((0, 0), (1, 1)),
        bounds=TrackMapBounds(0, 1, 0, 1),
        source=TRACK_MAP_REPLAY_GEOMETRY_SOURCE,
    )
    assert _track_map_fallback_state(session, replay_geometry) == (
        TRACK_MAP_FALLBACK_STATE_REPLAY_V2
    )
    custom_geometry = TrackGeometry(
        points=((0, 0), (1, 1)),
        bounds=TrackMapBounds(0, 1, 0, 1),
        source="custom",
    )
    assert _track_map_fallback_state(session, custom_geometry) == (
        TRACK_MAP_FALLBACK_STATE_CUSTOM_GEOMETRY
    )


def test_track_map_geometry_edge_and_location_helpers() -> None:
    short = tuple(_position("4", index, 0, seconds=index) for index in range(5))
    assert _split_geometry_position_segments(short) == (short,)
    same = tuple(_position("4", 0, 0, seconds=index) for index in range(6))
    assert _split_geometry_position_segments(same) == (same,)
    jumped = (
        _position("4", 0, 0),
        _position("4", 100, 0, seconds=1),
        _position("4", 200, 0, seconds=2),
        _position("4", 10000, 0, seconds=3),
        _position("4", 10100, 0, seconds=4),
        _position("4", 10200, 0, seconds=5),
    )
    assert len(_split_geometry_position_segments(jumped)) == 2
    assert _geometry_heading(short, len(short) - 1, forward=True) is None
    assert _geometry_heading(short, 0, forward=False) is None
    duplicate = (
        _position("4", 0, 0),
        _position("4", 0, 0, seconds=1),
    )
    assert _geometry_heading(duplicate, 0, forward=True) is None

    points = tuple((index, 0) for index in range(600))
    thinned = _thin_geometry_points(points, 100)
    assert thinned[0] == points[0]
    assert thinned[-1] == points[-1]
    assert len(thinned) < len(points)

    degenerate = TrackGeometry(
        points=((0, 0), (0, 0)),
        bounds=TrackMapBounds(0, 0, 0, 0),
        source="test",
    )
    assert _position_geometry_context(_position("4", 1, 1), None) == {}
    assert _position_geometry_context(_position("4", 1, 1), degenerate) == {}
    assert (
        _location_context_confidence(
            stale=True,
            status_context={},
            geometry_context={},
            fallback_state=TRACK_MAP_FALLBACK_STATE_NO_SESSION,
        )
        == "low"
    )
    assert (
        _location_context_confidence(
            stale=False,
            status_context={"pit_lane": True},
            geometry_context={},
            fallback_state=TRACK_MAP_FALLBACK_STATE_NO_SESSION,
        )
        == "high"
    )
    assert (
        _location_context_confidence(
            stale=False,
            status_context={"off_track": True},
            geometry_context={},
            fallback_state=TRACK_MAP_FALLBACK_STATE_NO_SESSION,
        )
        == "medium"
    )
    assert _location_description({"pit_lane": True}, {}) == "pit lane"
    assert _location_description({"off_track": True}, {"sector": 2}) == (
        "off track, sector 2"
    )
    assert _location_description({"on_track": True}, {}) == "on track"
    assert _location_description({"normalized": None}, {}) is None


class _Bus:
    def __init__(self, *, fail=False) -> None:
        self.fail = fail
        self.callbacks = {}

    def subscribe(self, stream, callback):
        if self.fail:
            raise RuntimeError("subscribe failed")
        self.callbacks[stream] = callback
        return Mock()


def test_track_map_adapter_start_guards_and_payload_filters() -> None:
    store = TrackMapStore("entry")
    adapter = TrackMapReplayAdapter(store, object())
    adapter.start()
    assert adapter._unsubs == []
    adapter._closed = True
    adapter.start()

    failing = TrackMapReplayAdapter(store, _Bus(fail=True))
    failing.start()
    assert failing._unsubs == []

    bus = _Bus()
    replay_manager = SimpleNamespace(add_listener=Mock(side_effect=RuntimeError))
    replay_controller = SimpleNamespace(session_manager=replay_manager)
    adapter = TrackMapReplayAdapter(store, bus, replay_controller=replay_controller)
    adapter.start()
    adapter.start()
    assert set(bus.callbacks) == {
        "SessionInfo",
        "DriverList",
        TRACK_MAP_POSITION_STREAM,
    }
    adapter._on_session_info("bad")
    adapter._on_driver_list("bad")
    adapter._on_position_z({})
    adapter._on_replay_state("bad")
    adapter._geometry_sample_limit = 0
    adapter._extend_geometry_positions([_position("4", 1, 1)])


def test_track_map_adapter_delay_queue_guards_and_direct_delivery(monkeypatch) -> None:
    store = TrackMapStore("entry")
    adapter = TrackMapReplayAdapter(
        store,
        _Bus(),
        hass=SimpleNamespace(loop=None),
        position_source_resolver=lambda: "live",
    )
    callback = Mock()
    adapter._delay = 1
    monkeypatch.setattr(
        "custom_components.f1_sensor.track_map.time.monotonic", lambda: 0
    )
    adapter._queue_live_payload(callback, {"ok": 1})
    assert callback.called
    adapter._queue_live_payload(Mock(side_effect=RuntimeError), {"bad": True})

    adapter._closed = True
    adapter._delay_queue.append((0, callback, {}))
    adapter._drain_delay_queue()
    assert adapter._delay_queue == adapter._delay_queue.__class__()
    adapter._closed = False
    adapter._position_source_resolver = lambda: "replay"
    adapter._delay_queue.append((0, callback, {}))
    adapter._drain_delay_queue()
    assert not adapter._delay_queue

    adapter._position_source_resolver = lambda: "live"
    adapter._delay_queue_handle = Mock()
    adapter._cancel_delay_queue_timer()
    assert adapter._delay_queue_handle is None


def test_track_map_adapter_replay_index_invalid_and_valid_frames(tmp_path) -> None:
    frames = tmp_path / "frames.jsonl"
    payload = track_map_positions_to_payload(
        [
            _position("4", 0, 0),
            _position("4", 10, 10, status="OffTrack"),
            _position("4", 100, 100, seconds=1),
            _position("4", 200, 200, seconds=2),
        ]
    )
    frames.write_text(
        "\n".join(
            [
                "",
                "bad json",
                json.dumps({"s": "Other", "p": payload}),
                json.dumps({"s": TRACK_MAP_POSITION_STREAM, "p": payload}),
            ]
        ),
        encoding="utf-8",
    )
    store = TrackMapStore("entry")
    store.update_session_info({"Key": "session", "Meeting": {"Circuit": {"Key": "x"}}})
    adapter = TrackMapReplayAdapter(
        store,
        _Bus(),
        geometry_min_driver_points=2,
    )
    geometry = adapter._build_geometry_from_replay_index(
        SimpleNamespace(frames_file=frames)
    )
    assert geometry is not None
    assert geometry.source == TRACK_MAP_REPLAY_GEOMETRY_SOURCE
    assert (
        adapter._build_geometry_from_replay_index(
            SimpleNamespace(frames_file=tmp_path / "missing")
        )
        is None
    )


async def test_track_map_adapter_replay_prepare_interpolation_and_close(
    hass, monkeypatch
) -> None:
    store = TrackMapStore("entry")
    bus = _Bus()
    delay_remove = Mock()
    delay_controller = SimpleNamespace(add_listener=Mock(return_value=delay_remove))
    adapter = TrackMapReplayAdapter(
        store,
        bus,
        hass=hass,
        delay_controller=delay_controller,
        position_source_resolver=lambda: "replay",
        geometry_min_driver_points=2,
    )
    adapter.start()
    geometry = TrackGeometry(
        points=((0, 0), (10, 10)),
        bounds=TrackMapBounds(0, 10, 0, 10),
        source="test",
    )
    adapter._build_geometry_from_replay_index = Mock(return_value=geometry)
    await adapter.async_prepare_replay_index(SimpleNamespace())
    assert store.geometry is geometry
    assert adapter._geometry_preloaded is True

    adapter._replay_state = "playing"
    monkeypatch.setattr(adapter, "_loop_time", lambda: 10.0)
    adapter._on_position_z(
        track_map_positions_to_payload(
            [_position("4", 100, 100), _position("81", 200, 200)]
        )
    )
    assert store.source == "replay"
    assert adapter._position_segments
    assert adapter._interpolation_handle is not None

    adapter._last_driver_sample_at["4"] = 9.0
    adapter._set_interpolation_targets([_position("4", 110, 110)], 10.0)
    assert adapter._driver_sample_interval_seconds == 1.0
    assert adapter._interpolation_duration() > 0
    adapter._interpolation_handle.cancel()
    adapter._run_interpolation_tick()

    adapter._on_replay_state({"state": "paused"})
    assert adapter._position_segments == {}
    adapter._on_replay_state("bad")
    adapter._on_position_z({"Entries": []})

    adapter._geometry_positions_by_driver = {"4": [_position("4", 1, 1)]}
    adapter._geometry_sample_count = 1
    adapter._position_frame_count = 1
    adapter.reset_for_replay()
    assert adapter._geometry_positions_by_driver == {}
    await adapter.async_close()
    delay_remove.assert_called_once()
    assert adapter._unsubs == []

    closed = TrackMapReplayAdapter(store, bus, hass=hass)
    closed._closed = True
    await closed.async_prepare_replay_index(SimpleNamespace())


def test_track_map_adapter_delay_overflow_session_switch_and_store_guards(
    monkeypatch,
) -> None:
    store = TrackMapStore("entry")
    loop = SimpleNamespace(call_later=Mock(return_value=Mock()), time=lambda: 5.0)
    adapter = TrackMapReplayAdapter(
        store,
        _Bus(),
        hass=SimpleNamespace(loop=loop),
        position_source_resolver=lambda: "live",
    )
    adapter._delay = 1
    monkeypatch.setattr(
        "custom_components.f1_sensor.track_map.MAX_TRACK_MAP_DELAY_QUEUE_ITEMS",
        1,
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.track_map.time.monotonic", lambda: 10.0
    )
    first = Mock()
    second = Mock()
    adapter._queue_live_payload(first, {"first": True})
    adapter._queue_live_payload(second, {"second": True})
    assert adapter._delay_queue_dropped == 1
    adapter.set_delay(0)
    second.assert_called_once()

    adapter._on_session_info({"Key": "one", "Meeting": {"Circuit": {"Key": "circuit"}}})
    adapter._position_segments["4"] = Mock()
    adapter._geometry_positions_by_driver["4"] = [_position("4", 1, 1)]
    adapter._on_session_info({"Key": "two", "Meeting": {"Circuit": {"Key": "circuit"}}})
    assert adapter._position_segments == {}
    assert adapter._geometry_positions_by_driver == {}
    adapter._on_driver_list({"4": {"RacingNumber": "4", "Tla": "NOR"}})

    unavailable = TrackMapPosition("4", NOW, 0, 0, 0, "Unavailable")
    adapter._on_position_z(track_map_positions_to_payload([unavailable]))
    assert store.is_stale(NOW) is False

    adapter._interpolation_source = "replay"
    adapter._replay_state = "playing"
    adapter._interpolation_handle = Mock()
    adapter._schedule_interpolation_tick()
    adapter._cancel_interpolation_timer()
    assert adapter._interpolation_handle is None
    assert adapter._loop_time() == 5.0

    store.update_positions([_position("4", 10, 10)], source="live")
    store.mark_positions_unavailable(source="live")
    assert store.is_stale(NOW) is True
    store.mark_positions_unavailable(source="live")
    store.update_replay_state("playing")
    store.update_replay_state("playing")
    assert store.source == "live"
    assert store.location_context("missing") is None
    assert store.location_context(True) is None
