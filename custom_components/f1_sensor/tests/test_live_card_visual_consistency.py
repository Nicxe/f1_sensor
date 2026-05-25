"""Regression tests for F1 live data card visual consistency CSS."""

from __future__ import annotations

from pathlib import Path
import re

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


def _card_source() -> str:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    return CARD_PATH.read_text()


def _blocks_for_selector(source: str, selector: str) -> list[str]:
    pattern = re.compile(
        rf"(?m)^    {re.escape(selector)} \{{(?P<body>.*?)^    \}}",
        re.DOTALL,
    )
    return [match.group("body") for match in pattern.finditer(source)]


def _ts_table_block(source: str) -> str:
    pattern = re.compile(
        r"(?m)^    \.ts-times,\n    \.ts-stats \{(?P<body>.*?)^    \}",
        re.DOTALL,
    )
    match = pattern.search(source)
    if match is None:
        pytest.fail("Tyre statistics table spacing block not found")
    return match.group("body")


def test_live_card_table_rows_share_spacing_token() -> None:
    source = _card_source()

    assert "--f1-table-row-gap: 6px;" in source
    assert "--f1-table-row-min-height: 34px;" in source
    assert "--f1-table-row-padding: 6px 8px;" in source
    assert "--f1-table-row-padding-compact: 5px 6px;" in source

    blocks = [_ts_table_block(source)]
    expected_selector_counts = {
        ".ps-table": 1,
        ".dl-table": 1,
        ".cpd-table": 2,
        ".cpt-table": 1,
        ".inv-table": 1,
        ".tl-table": 1,
        ".qt-table": 1,
        ".pt-table": 1,
        ".rl-table": 1,
        ".sg-table": 1,
    }
    for selector, expected_count in expected_selector_counts.items():
        selector_blocks = _blocks_for_selector(source, selector)
        assert len(selector_blocks) == expected_count
        blocks.extend(selector_blocks)

    for block in blocks:
        assert "gap: var(--f1-table-row-gap);" in block
        assert "gap: 4px;" not in block


def test_position_movement_arrows_keep_dark_mode_and_gain_light_mode_contrast() -> None:
    source = _card_source()

    assert ".cpd-pos-arrow.up {\n      color: #34d399;" in source
    assert ".cpd-pos-arrow.down {\n      color: #f87171;" in source
    assert ".cpt-pos-arrow.up {\n      color: #34d399;" in source
    assert ".cpt-pos-arrow.down {\n      color: #f87171;" in source

    light_mode_block = (
        ":host([data-effective-theme='light']) .cpd-delta-pill,\n"
        "  :host([data-effective-theme='light']) .cpt-delta-pill,\n"
        "  :host([data-effective-theme='light']) .cpd-pos-arrow,\n"
        "  :host([data-effective-theme='light']) .cpt-pos-arrow {\n"
        "    color: var(--f1-card-text);\n"
        "  }"
    )
    assert light_mode_block in source
