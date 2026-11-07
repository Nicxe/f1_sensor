"""Schedule refreshes cannot discard data belonging to an active stream."""

from types import SimpleNamespace

import pytest

from custom_components import f1_sensor as integration
from custom_components.f1_sensor.live_window import LiveAvailabilityTracker


@pytest.mark.parametrize(
    "coordinator_type",
    [
        integration.LiveDriversCoordinator,
        integration.TeamRadioCoordinator,
        integration.PitStopCoordinator,
        integration.ChampionshipPredictionCoordinator,
    ],
)
async def test_index_refresh_preserves_delayed_live_delivery(hass, coordinator_type):
    session = SimpleNamespace(data={"Sessions": [{"Key": 11408, "EndDate": "old"}]})
    live = LiveAvailabilityTracker()
    coordinator = coordinator_type(hass, session, delay_seconds=50, live_state=live)
    try:
        live.set_state(True, "live-Qualifying")
        coordinator._on_session_index_update()
        delivered = []
        receive = integration._wrap_delayed_handler(coordinator, delivered.append)
        receive({"session": 11408, "lap": "last completed lap"})
        assert delivered == []

        session.data = {
            "Sessions": [{"Key": 11408, "EndDate": "corrected"}, {"Key": 11409}]
        }
        coordinator._on_session_index_update()
        coordinator.set_delay(0)

        assert delivered == [{"session": 11408, "lap": "last completed lap"}]
    finally:
        await coordinator.async_close()


async def test_index_refresh_keeps_minisectors_until_actual_session_changes(hass):
    session = SimpleNamespace(data={"Sessions": [{"Key": 11408}]})
    live = LiveAvailabilityTracker()
    coordinator = integration.LiveDriversCoordinator(hass, session, live_state=live)
    try:
        live.set_state(True, "live-Qualifying")
        coordinator._on_session_index_update()
        coordinator._on_sessioninfo({"Key": 11408, "Type": "Qualifying"})
        coordinator._merge_timingdata(
            {"Lines": {"1": {"Sectors": {"0": {"Segments": {"0": {"Status": 2048}}}}}}}
        )
        before = coordinator.minisector_snapshot()
        assert before["drivers"]

        session.data = {"Sessions": [{"Key": 11408, "Path": "published-later/"}]}
        coordinator._on_session_index_update()

        after = coordinator.minisector_snapshot()
        assert after["drivers"] == before["drivers"]
        assert after["generation"] == before["generation"]
        coordinator._on_sessioninfo({"Key": 11409, "Type": "Race"})
        assert coordinator.minisector_snapshot()["drivers"] == {}
        assert coordinator.minisector_snapshot()["generation"] != before["generation"]
    finally:
        await coordinator.async_close()
