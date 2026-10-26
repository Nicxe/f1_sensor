"""Pit Stops owns its timing inputs even without other driver features."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
import re

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN
from custom_components.f1_sensor.feature_plan import build_feature_plan


def test_pitstops_only_requests_shared_counts_and_lap_history() -> None:
    """A Pit Stops sensor must not depend on a dashboard requesting timing."""
    plan = build_feature_plan({"pitstops"}, live_enabled=True)

    assert plan.needs("drivers")
    assert {
        "SessionInfo",
        "DriverList",
        "TimingData",
        "TimingAppData",
        "DriverRaceInfo",
        "LapHistory",
        "PitStopSeries",
    } <= plan.requested_streams
    assert not {"CarData.z", "Position.z"} & plan.requested_streams
    assert plan.stream_reasons["TimingData"] == ("pitstops",)


def _test_auth_header() -> str:
    def encode(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    expiry = datetime.now(UTC) + timedelta(days=2)
    return "Bearer " + ".".join(
        (encode({"alg": "none"}), encode({"exp": int(expiry.timestamp())}), "test")
    )


@pytest.mark.asyncio
async def test_pitstops_only_entry_delivers_counts_without_other_driver_entities(
    hass, enable_custom_integrations, aioclient_mock
) -> None:
    """Automatic card capability planning already protects ordinary entries."""
    aioclient_mock.get(re.compile(r"https://.*"), json={"Meetings": []})
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        minor_version=2,
        data={
            "sensor_name": "F1",
            "operation_mode": "live",
            CONF_LIVE_TIMING_AUTH_HEADER: _test_auth_header(),
        },
        options={
            "exposed_sensor_keys": ["pitstops"],
            "enable_race_control": True,
            "install_dashboard_cards": False,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    try:
        registry = entry.runtime_data.legacy
        pitstops = registry["pitstop_coordinator"]
        drivers = registry["drivers_coordinator"]
        assert drivers is not None
        assert pitstops._drivers_coord is drivers
        bus = registry["live_bus"]
        assert not bus._running
        registry["live_state"].set_state(True, "live")
        bus.inject_message("SessionInfo", {"Key": 11396, "Type": "Race"})
        bus.inject_message("DriverList", {"41": {"Tla": "LIN"}})
        bus.inject_message("TimingData", {"Lines": {"41": {"NumberOfPitStops": 1}}})
        await hass.async_block_till_done()

        assert pitstops.data["total_stops"] == 1
        assert pitstops.data["cars"]["41"]["count"] == 1
        assert pitstops.data["cars"]["41"]["stops"] == []
        entities = er.async_get(hass)
        pitstop_entity_id = entities.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_pitstops"
        )
        assert pitstop_entity_id is not None
        assert hass.states.get(pitstop_entity_id).state == "1"
        bus.inject_message("DriverRaceInfo", {"41": {"PitStops": 2}})
        await hass.async_block_till_done()
        assert pitstops.data["total_stops"] == 2
        assert hass.states.get(pitstop_entity_id).state == "2"
        assert not bus._running
        assert (
            entities.async_get_entity_id(
                "sensor", DOMAIN, f"{entry.entry_id}_driver_positions"
            )
            is None
        )
        assert (
            entities.async_get_entity_id(
                "sensor", DOMAIN, f"{entry.entry_id}_current_tyres"
            )
            is None
        )
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
