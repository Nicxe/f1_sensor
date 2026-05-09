"""Regression tests for F1 race control card layout CSS."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_PATH = (
    ROOT
    / "custom_components"
    / "f1_sensor"
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)


def _race_control_source() -> str:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    source = CARD_PATH.read_text()
    start = source.index("class F1RaceControlCard extends LitElement")
    end = source.index("class F1RaceControlCardEditor", start)
    return source[start:end]


def test_race_control_list_rows_keep_message_off_bottom_edge() -> None:
    source = _race_control_source()

    assert "align-items: start;" in source
    assert "row-gap: 6px;" in source
    assert "padding: 10px 14px 11px 16px;" in source
    assert "padding: 11px 14px 12px 16px;" in source
    assert "min-height: 68px;" in source
    assert "line-height: 1.38;" in source
