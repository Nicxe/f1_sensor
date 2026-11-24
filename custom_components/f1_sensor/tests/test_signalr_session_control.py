"""Keep lifecycle event provenance at the raw transport boundary."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor.signalr import LiveBus


@pytest.mark.parametrize("stream", ["SessionStatus", "SessionData"])
def test_control_updates_retain_source_time(hass, stream):
    """A delayed lifecycle event can be ordered without using its receipt time."""
    bus = LiveBus(hass, AsyncMock())
    data = {"Status": "Ends"} if stream == "SessionStatus" else {"StatusSeries": {}}
    original = deepcopy(data)
    event = {"M": [{"M": "feed", "A": [stream, data, "2026-11-07T20:32:43.555Z"]}]}

    assert bus._process_payload(event)

    received = bus.get_last_payload(stream)
    assert received["_f1_source_utc"] == "2026-11-07T20:32:43.555000+00:00"
    assert received["_f1_source_domain"] == "utc"
    assert received["_f1_source_time"] == pytest.approx(1794083563.555)
    assert data == original


def test_control_snapshot_is_identified_and_session_arrives_first(hass):
    """A cached status arrives with its session identity and dated history available."""
    bus = LiveBus(hass, AsyncMock())
    received = []
    for stream in ("SessionInfo", "SessionStatus", "SessionData", "TrackStatus"):
        bus.subscribe(stream, lambda data, name=stream: received.append((name, data)))
    snapshot = {
        "TrackStatus": {"Status": "1", "Message": "AllClear"},
        "SessionStatus": {"Status": "Inactive", "Started": "Started"},
        "SessionData": {
            "StatusSeries": {
                "4": {"Utc": "2026-11-01T19:09:00.471Z", "SessionStatus": "Inactive"}
            }
        },
        "SessionInfo": {"Key": 11404, "Name": "Race"},
    }
    original = deepcopy(snapshot)

    assert bus._process_payload({"R": snapshot})

    assert [name for name, _ in received] == [
        "SessionInfo",
        "SessionData",
        "TrackStatus",
        "SessionStatus",
    ]
    for _, data in received:
        assert data["_f1_snapshot"] is True
        assert "_f1_source_utc" not in data
    assert snapshot == original
