"""Race Trace provenance belongs to the received frame, never its publisher."""

from copy import deepcopy
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.f1_sensor import race_trace_observation
from custom_components.f1_sensor.live_delay import LiveDelayController
from custom_components.f1_sensor.race_trace_observation import (
    RaceTraceObservationSource,
    consumed_observation,
)
from custom_components.f1_sensor.signalr import LiveBus, timing_source_payload


@pytest.mark.parametrize("takeover_at", ["connect", "message", "retry"])
async def test_native_reader_cannot_dispatch_or_retry_after_replay_claim(
    hass, monkeypatch, takeover_at
):
    """A native client keeps its own origin even if the source owner changes."""
    source = ["live"]
    bus = LiveBus(hass, AsyncMock(), requested_streams={"SessionInfo"})
    bus.configure_observations(
        "entry", None, lambda: "race-a", source_provider=lambda: source[0]
    )
    received = []
    bus.subscribe("SessionInfo", received.append)

    async def connect():
        if takeover_at == "connect":
            source[0] = "replay"
        if takeover_at == "retry" and source[0] == "live":
            raise TimeoutError

    async def messages():
        source[0] = "replay"
        yield {"M": [{"M": "feed", "A": ["SessionInfo", {"Key": 9999}]}]}

    async def retry(_reason):
        if takeover_at == "retry" and source[0] == "live":
            source[0] = "replay"
        else:
            bus._running = False

    client = SimpleNamespace(
        ensure_connection=connect, messages=messages, close=AsyncMock()
    )
    create = Mock(return_value=client)
    monkeypatch.setattr(bus, "_create_client", create)
    monkeypatch.setattr(bus, "_wait_before_retry", retry)
    bus._running = True
    await bus._run()
    assert received == []
    assert create.call_count == 1
    client.close.assert_awaited_once()
    assert bus._running is False


def _stamp(stamper, stream="TimingData", payload=None, **changes):
    options = {
        "source": "live",
        "replay_session_id": None,
        "delay_epoch": 0,
        "delay_seconds": 0,
    }
    options.update(changes)
    return stamper.stamp(
        stream,
        payload or {"_f1_source_time": 100.0, "_f1_source_domain": "utc"},
        **options,
    )


def test_context_hash_is_reused_while_each_observation_owns_its_context(monkeypatch):
    sha256 = Mock(wraps=hashlib.sha256)
    monkeypatch.setattr(
        race_trace_observation, "hashlib", SimpleNamespace(sha256=sha256)
    )
    source = RaceTraceObservationSource("entry-a")
    _stamp(source, "SessionInfo", {"Key": 123})
    first = _stamp(source)["_f1_observation"]
    token = first["context"]["token"]
    first["context"]["session_id"] = "mutated"
    second = _stamp(source)["_f1_observation"]
    assert sha256.call_count == 1
    assert second["context"]["session_id"] == "123"
    assert second["context"]["token"] == token
    assert second["cursor"]["sequence"] == first["cursor"]["sequence"] + 1

    delayed = _stamp(source, delay_epoch=1, delay_seconds=40)["_f1_observation"]
    assert sha256.call_count == 2
    assert delayed["context"]["token"] != token


def test_received_context_is_stable_across_late_consumption_and_cached_delivery():
    source = RaceTraceObservationSource("entry-a")
    _stamp(source, "SessionInfo", {"Key": 123, "Type": "Race"})
    frame = _stamp(source)
    observation = consumed_observation(frame, delay_epoch=0, delay_seconds=0)
    assert observation["status"] == "ready"
    assert observation["context"]["session_id"] == "123"
    assert observation["timing_as_of"] == {
        "sequence": 2,
        "source_time_ms": 100000,
        "time_domain": "utc",
    }
    saved = deepcopy(frame)
    _stamp(source, "SessionInfo", {"Key": 124})
    assert frame == saved
    assert (
        consumed_observation(frame, delay_epoch=1, delay_seconds=30)["status"]
        == "pending"
    )
    assert (
        consumed_observation(frame, delay_epoch=2, delay_seconds=0)["status"]
        == "pending"
    )
    source.reset()
    _stamp(source, "SessionInfo", {"Key": 123})
    assert (
        _stamp(source)["_f1_observation"]["context"]["token"]
        != observation["context"]["token"]
    )


def test_snapshots_unknown_time_and_missing_session_cannot_be_ready():
    source = RaceTraceObservationSource("entry-a")
    assert (
        consumed_observation(_stamp(source), delay_epoch=0, delay_seconds=0)["status"]
        == "pending"
    )
    _stamp(source, "SessionInfo", {"Key": 123})
    for payload in (
        {"_f1_snapshot": True, "_f1_source_time": 100.0, "_f1_source_domain": "utc"},
        {"Lines": {}},
    ):
        result = consumed_observation(
            _stamp(source, payload=payload), delay_epoch=0, delay_seconds=0
        )
        assert result["status"] == "pending"
        assert result["timing_as_of"] is None


def test_replay_id_and_source_domains_are_explicit_and_driver_list_is_untouched():
    source = RaceTraceObservationSource("entry-a")
    frame = _stamp(
        source,
        source="replay",
        replay_session_id="2025_1277_9947",
        payload={"_f1_source_time": 0.0, "_f1_source_domain": "replay_offset"},
    )
    result = consumed_observation(frame, delay_epoch=0, delay_seconds=0)
    assert result["context"]["session_id"] == "2025_1277_9947"
    assert result["context"]["source"] == "replay"
    assert result["timing_as_of"]["source_time_ms"] == 0
    drivers = {"4": {"RacingNumber": "4"}}
    assert _stamp(source, "DriverList", drivers) is drivers


@pytest.mark.asyncio
async def test_delay_epoch_changes_only_for_real_changes(hass):
    controller = LiveDelayController(hass, "entry-a")
    assert controller.epoch == 0
    await controller.async_set_delay(30)
    assert controller.epoch == 1
    await controller.async_set_delay(30)
    assert controller.epoch == 1
    await controller.async_set_delay(0)
    assert controller.epoch == 2
    await controller.async_close()


def test_bus_fanout_and_cache_keep_one_observation_without_retagging(hass):
    bus = LiveBus(hass, None)
    delay = LiveDelayController(hass, "entry-a")
    bus.configure_observations("entry-a", delay, lambda: None)
    bus._dispatch("SessionInfo", {"Key": 123})
    received = []
    bus.subscribe("TimingData", received.append)
    bus._dispatch(
        "TimingData",
        timing_source_payload(
            "TimingData", {"Lines": {}}, source_utc="2025-07-06T14:00:00Z"
        ),
    )
    late = []
    bus.subscribe("TimingData", late.append)
    assert received == late
    assert received[0]["_f1_observation"]["cursor"]["time_domain"] == "utc"
    saved = deepcopy(received[0])
    bus.reset_for_replay()
    assert bus.consumed_observation(saved, 0)["status"] == "pending"
    bus._dispatch("SessionInfo", {"Key": 123})
    bus._dispatch(
        "TimingData",
        timing_source_payload(
            "TimingData", {"Lines": {}}, source_utc="2025-07-06T14:00:00Z"
        ),
    )
    assert received[0] == saved
    assert (
        received[1]["_f1_observation"]["context"]["source_epoch"]
        != saved["_f1_observation"]["context"]["source_epoch"]
    )


@pytest.mark.parametrize(
    "stream",
    ["TimingData", "TimingAppData", "TrackStatus", "PitStopSeries", "SessionInfo"],
)
def test_source_time_and_snapshot_metadata_cover_all_marker_inputs(stream):
    raw = {"value": 1}
    frame = timing_source_payload(stream, raw, source_time=1.25)
    assert frame["_f1_source_domain"] == "replay_offset"
    assert frame["_f1_source_time"] == 1.25
    assert timing_source_payload(stream, raw, snapshot=True)["_f1_snapshot"] is True
    assert raw == {"value": 1}


@pytest.mark.parametrize("milliseconds", [1001, 4162963])
def test_replay_millisecond_cursor_preserves_the_recorded_frame(milliseconds):
    source = RaceTraceObservationSource("entry")
    frame = _stamp(
        source,
        source="replay",
        replay_session_id="2025_1277_9947",
        payload={
            "_f1_source_time": milliseconds / 1000,
            "_f1_source_domain": "replay_offset",
        },
    )
    assert frame["_f1_observation"]["cursor"]["source_time_ms"] == milliseconds


@pytest.mark.parametrize("seconds", [float("nan"), float("inf"), -1.0, True, 1e308])
def test_invalid_clock_is_unverified_without_dropping_provider_data(seconds):
    source = RaceTraceObservationSource("entry")
    _stamp(source, "SessionInfo", {"Key": 123})
    frame = _stamp(
        source,
        payload={
            "Lines": {"4": {}},
            "_f1_source_time": seconds,
            "_f1_source_domain": "utc",
        },
    )
    assert frame["Lines"] == {"4": {}}
    assert (
        consumed_observation(frame, delay_epoch=0, delay_seconds=0)["status"]
        == "pending"
    )
