"""Reproducible projection/publication comparison using a recorded P2 checkpoint."""

import json
from statistics import median
from time import process_time
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.card_data import CardDataStore
from custom_components.f1_sensor.sensor import F1TrackLimitsSensor
from custom_components.f1_sensor.tests.test_card_data_lifecycle import setup


@pytest.mark.performance
async def test_recorded_projection_resource_comparison(hass):
    async def measure(mode):
        entry, data, unused = setup(hass)
        await unused.async_close()
        hass.config_entries.async_update_entry(
            entry,
            options={
                "card_data_features": [] if mode == "sensor" else ["track_limits"],
            },
        )
        owner = CardDataStore(hass, entry, data)
        coordinator = data["race_control_coordinator"]
        recordings = coordinator.data_list
        sensor = None
        if mode != "direct":
            sensor = F1TrackLimitsSensor(coordinator, "benchmark", entry.entry_id, "F1")
            sensor.hass = hass
            sensor.async_write_ha_state = Mock()
        wire_bytes, messages = 0, 0
        previous_revision = None
        start = process_time()
        for message in recordings:
            coordinator.data = message
            coordinator.data_list = [message]
            if mode != "direct":
                before = sensor.async_write_ha_state.call_count
                sensor._handle_coordinator_update()
                if sensor.async_write_ha_state.call_count != before:
                    messages += 1
                    wire_bytes += len(
                        json.dumps(
                            {
                                "state": sensor.state,
                                "attributes": sensor.extra_state_attributes,
                            }
                        ).encode()
                    )
            if mode != "sensor":
                envelope = owner.snapshot("track_limits")
                if envelope["revision"] != previous_revision:
                    previous_revision = envelope["revision"]
                    messages += 1
                    wire_bytes += len(json.dumps(envelope).encode())
        cpu_ms = (process_time() - start) * 1000
        projection = (
            owner.snapshot("track_limits")["payload"]
            if mode == "direct"
            else {"state": sensor.state}
        )
        result = {
            "mode": mode,
            "input_messages": len(recordings),
            "cpu_ms": round(cpu_ms, 3),
            "serialized_bytes": wire_bytes,
            "messages": messages,
            "sensor_write_requests": sensor.async_write_ha_state.call_count
            if sensor is not None
            else 0,
            "track_limit_count": projection["state"],
        }
        await owner.async_close()
        return result

    results = []
    for mode in ("sensor", "direct", "direct_and_sensor"):
        await measure(mode)  # Warm imports and interpreter specialization equally.
        runs = [await measure(mode) for _ in range(9)]
        result = {**runs[0], "cpu_ms": median(run["cpu_ms"] for run in runs), "runs": 9}
        results.append(result)
    assert len({result["track_limit_count"] for result in results}) == 1
    assert results[1]["sensor_write_requests"] == 0
    print("CARD_DATA_BENCHMARK " + json.dumps(results))
