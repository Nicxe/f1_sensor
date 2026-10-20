"""Direct-data ownership, isolation and privacy regressions."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager


class Coordinator:
    def __init__(self):
        self.data = {
            "MRData": {
                "StandingsTable": {
                    "StandingsLists": [
                        {
                            "season": "2026",
                            "round": "18",
                            "DriverStandings": [{"position": "1", "points": "331"}],
                        }
                    ]
                }
            }
        }
        self.last_update_success = True
        self.listeners = set()
        self.async_request_refresh = AsyncMock()

    def async_add_listener(self, callback):
        self.listeners.add(callback)
        return lambda: self.listeners.discard(callback)

    def update(self):
        for callback in tuple(self.listeners):
            callback()


@pytest.fixture
def store(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, options={"card_data_features": ["driver_standings"]}
    )
    entry.add_to_hass(hass)
    coordinator = Coordinator()
    manager = NoSpoilerModeManager(hass)
    hass.data[DOMAIN] = {"no_spoiler_manager": manager}
    data = {"driver_coordinator": coordinator}
    result = CardDataStore(hass, entry, data)
    entry.runtime_data = SimpleNamespace(card_data=result)
    return result, coordinator, manager


async def test_multiple_clients_share_data_and_final_cleanup(store):
    owner, coordinator, _ = store
    first, second = [], []
    a = owner.subscribe(["driver_standings"], first.append)
    b = owner.subscribe(["driver_standings"], second.append)
    assert len(coordinator.listeners) == 1
    assert first[-1]["payload"]["attributes"]["driver_standings"][0]["points"] == "331"
    first[-1]["payload"]["attributes"]["driver_standings"][0]["points"] = "0"
    assert second[-1]["payload"]["attributes"]["driver_standings"][0]["points"] == "331"
    revision = second[-1]["revision"]
    coordinator.update()
    assert len(second) == 1
    coordinator.data = deepcopy(coordinator.data)
    coordinator.data["MRData"]["StandingsTable"]["StandingsLists"][0]["round"] = "19"
    coordinator.update()
    assert second[-1]["revision"] > revision
    a()
    assert len(coordinator.listeners) == 1
    b()
    assert not coordinator.listeners
    await owner.async_close()


async def test_spoiler_block_replaces_cached_data_and_reconnect_snapshot(store):
    owner, _, manager = store
    received = []
    stop = owner.subscribe(["driver_standings"], received.append)
    await manager.async_set_active(True)
    assert received[-1]["status"] == "blocked"
    assert received[-1]["payload"] is None
    other = []
    unsubscribe = owner.subscribe(["driver_standings"], other.append)
    assert other[-1]["payload"] is None
    await manager.async_set_active(False)
    assert received[-1]["status"] == "ready"
    stop()
    unsubscribe()
    await owner.async_close()


async def test_unload_sends_closed_and_cannot_be_restarted(store):
    owner, coordinator, _ = store
    received = []
    stop = owner.subscribe(["driver_standings"], received.append)
    await owner.async_close()
    assert received[-1]["status"] == "closed"
    assert received[-1]["payload"] is None
    assert not coordinator.listeners
    stop()
    with pytest.raises(RuntimeError, match="closed"):
        owner.subscribe(["driver_standings"], received.append)


async def test_missing_and_failed_sources_never_fall_back_to_entities(store):
    owner, coordinator, _ = store
    assert owner.snapshot("constructor_standings")["status"] == "unavailable"
    owner.snapshot("driver_standings")
    coordinator.last_update_success = False
    assert owner.snapshot("driver_standings")["status"] == "stale"
    await owner.async_close()
