"""Regression gates introduced by the Phase 5 quality programme."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter

import pytest

from custom_components.f1_sensor.track_map import TrackMapPosition, TrackMapStore


@pytest.mark.performance
@pytest.mark.parametrize("source", ["live", "replay"])
def test_realtime_and_replay_snapshot_load_stays_within_budget(source: str) -> None:
    base = datetime(2026, 8, 31, tzinfo=UTC)
    store = TrackMapStore("phase-5-load")
    store.update_session_info(
        {
            "Key": "phase-5",
            "Name": "Race",
            "Type": "Race",
            "Meeting": {"Circuit": {"Key": "151", "ShortName": "Miami"}},
        }
    )
    store.update_driver_list(
        {
            str(number): {"RacingNumber": str(number), "Tla": f"D{number:02d}"}
            for number in range(1, 21)
        }
    )

    started = perf_counter()
    for update in range(100):
        store.update_positions(
            [
                TrackMapPosition(
                    racing_number=str(number),
                    timestamp=base + timedelta(milliseconds=update * 100),
                    x=1000 + number * 5 + update,
                    y=2000 + number * 3 + update,
                    z=0,
                    status="OnTrack",
                )
                for number in range(1, 21)
            ],
            source=source,
        )
        for _client in range(10):
            assert len(store.snapshot()["drivers"]) == 20
    elapsed_ms = (perf_counter() - started) * 1000

    assert elapsed_ms < 2500
