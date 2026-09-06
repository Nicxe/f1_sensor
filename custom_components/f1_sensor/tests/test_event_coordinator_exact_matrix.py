"""Exact event coordinator branches for Race Control and incident handling."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.f1_sensor import IncidentCoordinator, RaceControlCoordinator
from custom_components.f1_sensor.incident_detection import (
    DATA_QUALITY_BOOTSTRAP,
    DATA_QUALITY_LIVE,
    DriverMetadata,
    IncidentChange,
    IncidentLocationContext,
    IncidentSignal,
    RaceControlContext,
    SessionMetadata,
    TrackStatusContext,
)


class _Bus:
    def __init__(self, *, fail=False) -> None:
        self.callbacks = {}
        self.removers = []
        self.fail = fail

    def subscribe(self, stream, callback):
        if self.fail:
            raise RuntimeError("subscribe")
        self.callbacks[stream] = callback
        remover = Mock()
        self.removers.append(remover)
        return remover


def _change(now: datetime) -> IncidentChange:
    return IncidentChange(
        incident_id="incident-4",
        phase="confirmed",
        confidence="high",
        reason="stopped",
        driver=DriverMetadata("4", tla="NOR"),
        session=SessionMetadata(
            session_key="race", session_name="Race", session_type="race"
        ),
        track_status=TrackStatusContext("YELLOW"),
        race_control=RaceControlContext("Yellow"),
        location=IncidentLocationContext(status="OnTrack"),
        signals=("timing_stopped",),
        started_at=now,
        updated_at=now,
        data_quality=DATA_QUALITY_LIVE,
    )


async def test_race_control_exact_queue_debug_failure_and_cleanup(
    hass, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="custom_components.f1_sensor")
    delay_remove = Mock()
    live_remove = Mock()
    delay = SimpleNamespace(add_listener=Mock(return_value=delay_remove))
    live = SimpleNamespace(add_listener=Mock(return_value=live_remove))
    bus = _Bus()
    coordinator = RaceControlCoordinator(
        hass,
        SimpleNamespace(data={}),
        bus=bus,
        delay_controller=delay,
        live_state=live,
    )
    monkeypatch.setattr(
        DataUpdateCoordinator,
        "async_config_entry_first_refresh",
        AsyncMock(),
    )
    await coordinator.async_config_entry_first_refresh()
    assert "RaceControlMessages" in bus.callbacks

    coordinator._seen_ids_order = deque(maxlen=1)
    coordinator._seen_ids_set = {"old"}
    coordinator._seen_ids_order.append("old")
    coordinator._startup_cutoff = datetime.now(UTC) - timedelta(hours=1)
    coordinator._on_bus_message(
        {"Utc": "2099-09-01T12:00:00", "Message": "New message"}
    )
    await hass.async_block_till_done()
    assert "old" not in coordinator._seen_ids_set
    assert coordinator.data["Message"] == "New message"

    coordinator._delay = 5
    coordinator._schedule_deliver({"Message": "queued"})
    assert coordinator._deliver_handles
    coordinator.set_delay(0)
    coordinator._handle_live_state(True, "no-spoiler")
    assert coordinator._deliver_handles == []

    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )

    def _fail_event(*_args, **_kwargs):
        raise RuntimeError("event bus")

    monkeypatch.setattr(type(hass.bus), "async_fire", _fail_event)
    coordinator._deliver({"Category": "Flag", "Flag": "YELLOW", "Message": "Yellow"})
    assert coordinator.data["Flag"] == "YELLOW"

    coordinator._deliver_handles = [Mock(), Mock()]
    await coordinator.async_close()
    delay_remove.assert_called_once()
    live_remove.assert_called_once()
    assert all(remover.called for remover in bus.removers)

    missing_bus = RaceControlCoordinator(hass, SimpleNamespace(data={}))
    await missing_bus.async_config_entry_first_refresh()
    assert missing_bus._unsub is None


async def test_incident_exact_subscription_signal_state_reset_and_location(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        DataUpdateCoordinator,
        "async_config_entry_first_refresh",
        AsyncMock(),
    )
    bus = _Bus()
    coordinator = IncidentCoordinator(hass, object(), bus=bus)
    await coordinator.async_config_entry_first_refresh()
    assert "TimingData" in bus.callbacks

    failed = IncidentCoordinator(hass, object(), bus=_Bus(fail=True))
    await failed.async_config_entry_first_refresh()
    assert failed._unsubs == []

    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    session = SessionMetadata(session_key="race", session_name="Race")
    driver = DriverMetadata("4", tla="NOR")
    signals = [
        IncidentSignal("session_context", now, session_key="race", session=session),
        IncidentSignal(
            "driver_metadata",
            now,
            session_key="race",
            driver=driver,
            session=session,
        ),
    ]
    change = _change(now)
    monkeypatch.setattr(
        "custom_components.f1_sensor.normalize_stream", Mock(return_value=signals)
    )
    coordinator._detector.process_signals = Mock(return_value=[change])
    coordinator._handle_stream_payload(
        "SessionInfo", {}, observed_at=now, data_quality=DATA_QUALITY_LIVE
    )
    assert coordinator._session_metadata.session_key == "race"
    assert coordinator._drivers["4"].tla == "NOR"
    assert coordinator.data["latest_phase"] == "confirmed"

    before = len(coordinator._published_event_keys)
    coordinator._publish_change(change)
    assert len(coordinator._published_event_keys) == before
    coordinator._published_event_order = deque(maxlen=1)
    coordinator._published_event_keys = {("old", "old", "old", "old", "old")}
    coordinator._published_event_order.append(("old", "old", "old", "old", "old"))
    newer = _change(now + timedelta(seconds=1))
    coordinator._publish_change(newer)
    assert len(coordinator._published_event_keys) == 1

    monkeypatch.setattr(
        "custom_components.f1_sensor.normalize_stream", Mock(return_value=[])
    )
    coordinator._handle_stream_payload(
        "TimingData", {}, observed_at=now, data_quality=DATA_QUALITY_LIVE
    )
    coordinator._handle_stream_payload(
        "TimingData", {}, observed_at=now, data_quality=DATA_QUALITY_BOOTSTRAP
    )

    coordinator._handle_live_state(True, "init")
    coordinator._handle_live_state(True, "replay")
    assert coordinator._replay_mode is True
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator.data["active_count"] == 0

    assert coordinator._resolve_location_context("4", now) is None
    context = SimpleNamespace(
        timestamp=now,
        as_dict=lambda: {
            "status": "OffTrack",
            "source": "live",
            "stale": False,
            "confidence": "high",
            "distance_to_track": "bad",
        },
    )
    coordinator._track_map_store = SimpleNamespace(
        location_context=lambda *_args, **_kwargs: context
    )
    resolved = coordinator._resolve_location_context("4", now)
    assert resolved.status == "OffTrack"
    assert resolved.distance_to_track is None
    await coordinator.async_close()
    assert coordinator._closed is True
