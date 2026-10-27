"""Regressions for active unchanged tyres and Singapore's mirrored phantom row."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from homeassistant.config_entries import ConfigEntryState
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import LiveDriversCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.signalr import LiveBus


@pytest.fixture
def tyre_sequences() -> dict:
    """Return scoped, otherwise unmodified deltas from the recorded sessions."""
    path = Path(__file__).parent / "fixtures" / "issue920_current_tyres.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
async def coordinator(hass):
    coord = LiveDriversCoordinator(hass, SimpleNamespace(data={}))
    yield coord
    await coord.async_close()


def _apply_sequence(coordinator, tyre_sequences, name) -> None:
    for frame in tyre_sequences[name]["frames"]:
        coordinator._on_timingapp(frame["payload"])


def _delta(coordinator, driver, index, **fields) -> None:
    coordinator._on_timingapp({"Lines": {driver: {"Stints": {str(index): fields}}}})


@pytest.mark.parametrize(
    ("sequence", "driver", "laps"),
    [("austin_leclerc", "16", 22), ("austin_hamilton", "44", 14)],
)
async def test_austin_continuation_reaches_current_tyres_through_live_bus(
    hass, tyre_sequences, sequence, driver, laps
) -> None:
    """Real subscription delivery must follow the row advancing on reused tyres."""
    bus = LiveBus(hass, SimpleNamespace())
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    session = SimpleNamespace(data={}, async_add_listener=lambda _cb: lambda: None)
    coord = LiveDriversCoordinator(hass, session, bus=bus, config_entry=entry)
    await coord.async_config_entry_first_refresh()
    try:
        bus._process_payload(
            {"M": [{"M": "feed", "A": ["SessionStatus", {"Status": "Started"}]}]}
        )
        frames = tyre_sequences[sequence]["frames"]
        for frame in frames:
            bus._process_payload(
                {"M": [{"M": "feed", "A": ["TimingAppData", frame["payload"]]}]}
            )
        current = coord.data["drivers"][driver]
        assert current["tyres"] == {
            "compound": "SOFT",
            "stint_laps": laps,
            "new": False,
        }
        assert bus._cnt["TimingAppData"] == len(frames)
    finally:
        await coord.async_close()


async def test_advancing_unknown_continuation_keeps_known_compound(
    coordinator, tyre_sequences
) -> None:
    """An advancing row can omit its compound correction without erasing SOFT."""
    # Stop at LEC's actual UNKNOWN/New=false placeholder; the next sparse delta
    # advances its counter before a meaningful compound is available.
    for frame in tyre_sequences["austin_leclerc"]["frames"][:3]:
        coordinator._on_timingapp(frame["payload"])
    _delta(coordinator, "16", 2, TotalLaps=4)

    current = coordinator.data["drivers"]["16"]
    assert current["tyres"] == {"compound": "SOFT", "stint_laps": 4, "new": False}


async def test_confirmed_used_hards_use_new_flag_from_earlier_delta(
    coordinator, tyre_sequences
) -> None:
    """HAM's confirmation omits New=false already stored in the placeholder."""
    _apply_sequence(coordinator, tyre_sequences, "austin_hamilton")
    _apply_sequence(coordinator, tyre_sequences, "austin_hamilton_hard")

    current = coordinator.data["drivers"]["44"]
    assert current["tyres"] == {"compound": "HARD", "stint_laps": 8, "new": False}
    assert current["tyre_history"]["current_stint_index"] == 4


@pytest.mark.parametrize(
    ("sequence", "driver", "laps"),
    [("singapore_alonso", "14", 35), ("singapore_stroll", "18", 22)],
)
async def test_singapore_mirrored_stint_and_lap_time_deltas_stay_inactive(
    coordinator, tyre_sequences, sequence, driver, laps
) -> None:
    """Mirrored counters and newest-row lap times cannot displace the real row."""
    for frame in tyre_sequences[sequence]["frames"]:
        coordinator._on_timingapp(frame["payload"])
        current = coordinator.data["drivers"][driver]
        assert current["tyre_history"]["current_stint_index"] == 0
    assert current["tyres"] == {"compound": "SOFT", "stint_laps": laps, "new": True}
    assert current["tyre_history"]["stints"][0]["best_lap_time"] is not None
    assert current["tyre_history"]["stints"][1]["best_lap_time"] is None


@pytest.mark.parametrize(
    ("sequence", "driver", "old_laps"),
    [("singapore_alonso", "14", 36), ("singapore_stroll", "18", 23)],
)
async def test_confirmed_change_resets_immediately_and_ignores_old_row_updates(
    coordinator, tyre_sequences, sequence, driver, old_laps
) -> None:
    """Explicit real changes are valid at zero laps before their first increment."""
    _apply_sequence(coordinator, tyre_sequences, sequence)
    _apply_sequence(coordinator, tyre_sequences, f"{sequence}_change")
    current = coordinator.data["drivers"][driver]
    expected = {"compound": "MEDIUM", "stint_laps": 0, "new": True}
    assert current["tyres"] == expected
    assert current["tyre_history"]["current_stint_index"] == 1

    _delta(coordinator, driver, 0, TotalLaps=old_laps)
    assert current["tyres"] == expected
    assert current["tyre_history"]["current_stint_index"] == 1


@pytest.mark.parametrize("corrected_laps", [21, 2])
async def test_active_continuation_accepts_counter_correction(
    coordinator, tyre_sequences, corrected_laps
) -> None:
    """A downward correction must update the active row without selecting old data."""
    _apply_sequence(coordinator, tyre_sequences, "austin_leclerc")
    _delta(coordinator, "16", 2, TotalLaps=corrected_laps)

    current = coordinator.data["drivers"]["16"]
    expected = {"compound": "SOFT", "stint_laps": corrected_laps, "new": False}
    assert current["tyres"] == expected

    _delta(coordinator, "16", 2, LapTime="1:34.000", LapNumber=27)
    assert current["tyres"] == expected
    _delta(coordinator, "16", 1, TotalLaps=3)
    assert current["tyres"] == expected


async def test_continuation_lap_time_stays_with_confirmed_tyre_set(
    coordinator, tyre_sequences
) -> None:
    """Following an unchanged row must preserve lap attribution to the same set."""
    _apply_sequence(coordinator, tyre_sequences, "austin_leclerc")
    _delta(coordinator, "16", 2, LapTime="1:34.000", LapNumber=27)

    history = coordinator.data["drivers"]["16"]["tyre_history"]
    assert history["stints"][1]["best_lap_time"] == "1:34.000"
    assert history["stints"][2]["best_lap_time"] is None
    soft = coordinator.data["tyre_statistics"]["compounds"]["SOFT"]
    assert soft["sets_used_total"] == 1
    assert soft["best_times"][0]["time"] == "1:34.000"


@pytest.mark.parametrize(
    ("sequence", "driver", "display_index", "laps", "new"),
    [
        ("austin_leclerc", "16", 2, 22, False),
        ("singapore_alonso", "14", 0, 35, True),
        ("singapore_stroll", "18", 0, 22, True),
    ],
)
async def test_initial_snapshot_infers_counting_row_without_prior_deltas(
    coordinator, tyre_sequences, sequence, driver, display_index, laps, new
) -> None:
    """Reconnect and seek snapshots must distinguish continuing and phantom rows."""
    stints = {}
    for frame in tyre_sequences[sequence]["frames"]:
        updates = frame["payload"]["Lines"][driver]["Stints"]
        items = enumerate(updates) if isinstance(updates, list) else updates.items()
        for index, fields in items:
            stints.setdefault(str(index), {}).update(fields)

    coordinator._on_timingapp({"Lines": {driver: {"Stints": stints}}})

    current = coordinator.data["drivers"][driver]
    assert current["tyres"] == {"compound": "SOFT", "stint_laps": laps, "new": new}
    assert current["tyre_history"]["current_tyres_stint_index"] == display_index
