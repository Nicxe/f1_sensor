"""A normal live-session close must follow delivery of its last valid laps."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import f1_sensor as f1
from custom_components.f1_sensor import live_window
from custom_components.f1_sensor.const import DOMAIN, SUPPORTED_SENSOR_KEYS
from custom_components.f1_sensor.live_window import LiveSessionSupervisor, SessionWindow

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "issue_958_session_finish.json").read_text(
        encoding="utf-8"
    )
)["sources"]


class _QuietTransport:
    """Replace the upstream socket while keeping the entry's real shared bus."""

    async def ensure_connection(self):
        return None

    async def messages(self):
        await asyncio.Event().wait()
        yield {}

    async def update_streams(self, _streams):
        return None

    async def close(self):
        return None


async def _exercise_session_finish(
    hass, aioclient_mock, monkeypatch, case, delay, *, finish_action=None
):
    """Exercise setup wiring, real ingestion queues and supervisor shutdown together."""
    aioclient_mock.get(
        re.compile(r"https://.*"),
        json={"Meetings": [], "MRData": {"RaceTable": {"Races": []}}},
    )
    # Choose the test window explicitly; retain normal construction and wiring.
    monkeypatch.setattr(LiveSessionSupervisor, "async_start", AsyncMock())
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        data={"sensor_name": "F1", "data_choice_version": 1},
        options={
            "operation_mode": "live",
            "enable_race_control": True,
            "live_delay_seconds": delay,
            "disabled_sensors": sorted(SUPPORTED_SENSOR_KEYS - {"driver_positions"}),
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    remove_driver_listener = remove_state_listener = remove_card_listener = lambda: None
    try:
        registry = hass.data[DOMAIN][entry.entry_id]
        bus = entry.runtime_data.live.bus
        supervisor = entry.runtime_data.live.supervisor
        drivers = registry["drivers_coordinator"]
        analysis_bus = registry["analysis_bus"]
        laps = entry.runtime_data.history.lap_analysis
        card_data = entry.runtime_data.card_data
        remove_card_listener = card_data.subscribe(
            ["driver_positions"], lambda _data: None
        )
        controller = registry["live_delay_controller"]
        assert controller.current == delay
        assert drivers is not None

        clock = SimpleNamespace(value=0.0)
        origin = datetime(2026, 10, 30, 19, 0, tzinfo=UTC)
        monkeypatch.setattr(f1, "time", SimpleNamespace(monotonic=lambda: clock.value))
        monkeypatch.setattr(
            live_window,
            "dt_util",
            SimpleNamespace(utcnow=lambda: origin + timedelta(seconds=clock.value)),
        )
        monkeypatch.setattr(bus, "_monotonic", lambda: clock.value)
        monkeypatch.setattr(bus, "_transport_factory", _QuietTransport)
        info = case["session_info"]
        window = SessionWindow(
            meeting_name=info["Meeting"]["Name"],
            session_name=info["Name"],
            path=info["Path"],
            start_utc=origin - timedelta(hours=1),
            end_utc=origin + timedelta(minutes=20),
            connect_at=origin - timedelta(hours=2),
            disconnect_at=origin + timedelta(minutes=35),
            meeting_key=info["Meeting"]["Key"],
            session_key=info["Key"],
        )
        expected = {
            (number, count, case["expected_last_lap_times"][number])
            for number, count in case["expected_laps"].items()
        }
        published = set()
        before_close = []
        readable_drain_snapshots = []

        def observe_drivers():
            for number, driver in (drivers.data or {}).get("drivers", {}).items():
                published.add(
                    (
                        number,
                        driver.get("lap_history", {}).get("completed_laps"),
                        driver.get("timing", {}).get("last_lap"),
                    )
                )

        def observe_close(is_live, reason):
            if not is_live and reason != "init":
                before_close.append(expected <= published)

        remove_driver_listener = drivers.async_add_listener(observe_drivers)
        remove_state_listener = supervisor.availability.add_listener(observe_close)
        events = iter(case["events"])
        event = next(events, None)
        first_offset = case["events"][0]["offset"]
        ends_at = changed_delay_at = interrupted_at = duplicate_sent_at = None

        async def advance(_seconds):
            nonlocal event, ends_at, changed_delay_at, interrupted_at, duplicate_sent_at
            clock.value += 20
            assert clock.value <= 1200, "The ended live session did not close"
            # These heartbeats isolate normal session completion from inactivity.
            bus.inject_message("Heartbeat", {"Utc": origin.isoformat()})
            while event is not None and event["offset"] - first_offset <= clock.value:
                bus.inject_message(event["stream"], event["payload"])
                if (
                    ends_at is None
                    and event["stream"] == "SessionStatus"
                    and event["payload"].get("Status") == "Ends"
                ):
                    ends_at = clock.value
                event = next(events, None)
            if finish_action == "duplicate-finalised":
                if (
                    ends_at is not None
                    and duplicate_sent_at is None
                    and clock.value > ends_at
                ):
                    bus.inject_message(
                        "SessionStatus", {"Status": "Finalised", "Started": "Finished"}
                    )
                    duplicate_sent_at = clock.value
            elif finish_action is not None and ends_at is not None:
                if changed_delay_at is None and clock.value > ends_at:
                    await controller.async_set_delay(300)
                    changed_delay_at = clock.value
                elif (
                    finish_action in {"no-spoiler", "replay"}
                    and interrupted_at is None
                    and changed_delay_at is not None
                    and clock.value > changed_delay_at
                ):
                    interrupted_at = clock.value
                    if finish_action == "no-spoiler":
                        await hass.data[DOMAIN]["no_spoiler_manager"].async_set_active(
                            True
                        )
                    else:
                        # The replay controller claims ownership through this tracker.
                        # Existing replay tests cover replacement of the transport.
                        supervisor.availability.set_state(True, "replay")
            f1._drain_delayed_ingest_queue(drivers)
            f1._drain_delayed_ingest_queue(analysis_bus)
            if finish_action is None and ends_at is not None and expected <= published:
                snapshot = card_data.snapshot("driver_positions")
                assert snapshot["status"] == "ready"
                rows = snapshot["payload"]["attributes"]["drivers"]
                visible = {
                    (
                        row["racing_number"],
                        row["completed_laps"],
                        row["laps"].get(str(row["completed_laps"])),
                    )
                    for row in rows
                }
                assert expected <= visible, (
                    "The Timing card lost its final readable laps"
                )
                readable_drain_snapshots.append(clock.value)
            await asyncio.sleep(0)

        monkeypatch.setattr(supervisor, "_interruptible_sleep", advance)
        bus.inject_message("SessionInfo", info)
        await supervisor._activate_window(window, source="index")

        assert expected <= published, "Normal close discarded a final recorded lap"
        if finish_action in {"no-spoiler", "replay"}:
            assert interrupted_at is not None
            assert clock.value == interrupted_at, "The interrupt waited for the drain"
            assert supervisor.availability.reason == finish_action
            assert bus._running is (finish_action == "replay")
            assert before_close == ([] if finish_action == "replay" else [True])
            return
        assert before_close == [True], "Availability ended before the last laps arrived"
        assert supervisor.availability.reason == f"finished-{info['Name']}"
        assert not bus._running
        assert ends_at is not None, "Normal close happened before the Ends status"
        elapsed_after_ends = clock.value - ends_at
        expected_drain = 60 + controller.current
        assert expected_drain <= elapsed_after_ends < expected_drain + 20
        if finish_action is None:
            assert len(readable_drain_snapshots) >= 3
            snapshot = card_data.snapshot("driver_positions")
            assert snapshot["status"] == "unavailable"
            assert snapshot["payload"] is None
        if finish_action == "increase":
            assert changed_delay_at is not None
        elif finish_action == "duplicate-finalised":
            assert duplicate_sent_at is not None
        for number, count, lap_time in expected:
            lap = laps.get_lap(int(number), count)
            assert lap is not None
            minutes, seconds = lap_time.split(":")
            assert lap["lap_duration"] == pytest.approx(
                int(minutes) * 60 + float(seconds)
            )
    finally:
        remove_driver_listener()
        remove_state_listener()
        remove_card_listener()
        if entry.state == ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["session"])
@pytest.mark.parametrize("delay", [0, 300], ids=["live", "delayed-five-minutes"])
async def test_last_recorded_laps_are_published_before_normal_close(
    hass, enable_custom_integrations, aioclient_mock, monkeypatch, case, delay
):
    """Every recorded session delivers its final laps before normal shutdown."""
    await _exercise_session_finish(hass, aioclient_mock, monkeypatch, case, delay)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish_action", ["increase", "no-spoiler", "replay", "duplicate-finalised"]
)
async def test_delay_change_and_interrupts_during_final_drain(
    hass, enable_custom_integrations, aioclient_mock, monkeypatch, finish_action
):
    """Changing the delay extends normal drain but never postpones safety boundaries."""
    qualifying = next(
        case for case in _CASES if case["session"] == "us_2026_qualifying_q3"
    )
    await _exercise_session_finish(
        hass,
        aioclient_mock,
        monkeypatch,
        qualifying,
        0,
        finish_action=finish_action,
    )
