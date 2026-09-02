"""Regression gates introduced by the Phase 5 quality programme."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from time import perf_counter

import pytest

from custom_components.f1_sensor.track_map import TrackMapPosition, TrackMapStore

COMPONENT_ROOT = Path(__file__).parents[1]
CARD_ROOT = COMPONENT_ROOT / "www" / "f1-sensor-live-data-card"
PLACEHOLDER = re.compile(r"\{[^{}]+\}")
CARD_TYPES = {
    "f1-weekend-hub-card",
    "f1-sensor-live-data-card",
    "f1-pitstop-overview-card",
    "f1-driver-lap-times-card",
    "f1-championship-prediction-drivers-card",
    "f1-championship-prediction-teams-card",
    "f1-season-progression-card",
    "f1-last-race-results-card",
    "f1-lap-position-progression-card",
    "f1-replay-control-card",
    "f1-track-map-card",
    "f1-investigations-card",
    "f1-track-limits-card",
    "f1-next-race-card",
    "f1-weather-card",
    "f1-season-calendar-card",
    "f1-live-session-card",
    "f1-race-control-card",
    "f1-fia-documents-card",
    "f1-qualifying-timing-card",
    "f1-practice-timing-card",
    "f1-race-lap-card",
    "f1-starting-grid-card",
}


def _flatten(value: object, prefix: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        flattened: dict[str, str] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            flattened.update(_flatten(child, path))
        return flattened
    return {prefix: str(value)}


def test_translation_catalogs_have_exact_key_and_placeholder_parity() -> None:
    catalogs = {
        path.stem: _flatten(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((COMPONENT_ROOT / "translations").glob("*.json"))
    }
    english = catalogs["en"]

    assert len(catalogs) == 10
    for language, catalog in catalogs.items():
        assert catalog.keys() == english.keys(), language
        for key, value in catalog.items():
            assert set(PLACEHOLDER.findall(value)) == set(
                PLACEHOLDER.findall(english[key])
            ), f"{language}:{key}"


def test_all_cards_use_shared_actions_localization_and_registry_metadata() -> None:
    source = (CARD_ROOT / "f1-sensor-live-data-card.js").read_text(encoding="utf-8")
    registry = (CARD_ROOT / "platform" / "card-registry.js").read_text(encoding="utf-8")
    actions = (CARD_ROOT / "platform" / "actions.js").read_text(encoding="utf-8")

    assert (
        "F1_FONT_STYLE_CARD_CLASSES.forEach(sharedInstallF1CardActionAccessibility)"
        in source
    )
    assert "F1_FONT_STYLE_CARD_CLASSES.forEach(installF1FrontendLocalization)" in source
    assert "dispatchEvent(new CustomEvent('hass-action'" in actions
    assert "call-service" in actions and "perform-action" in actions
    assert set(re.findall(r"\['(f1-[a-z0-9-]+-card)'", registry)) == CARD_TYPES


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
