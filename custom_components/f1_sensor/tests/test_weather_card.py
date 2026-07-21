"""Structural regression tests for the standalone F1 weather card."""

from __future__ import annotations

from pathlib import Path

CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)


def _source() -> str:
    return CARD_PATH.read_text(encoding="utf-8")


def test_weather_card_is_registered_with_editor_and_picker_metadata() -> None:
    source = _source()

    assert "class F1WeatherCard extends LitElement" in source
    assert "class F1WeatherCardEditor extends LitElement" in source
    assert "customElements.define('f1-weather-card', F1WeatherCard)" in source
    assert (
        "customElements.define('f1-weather-card-editor', F1WeatherCardEditor)" in source
    )
    assert "type: 'custom:f1-weather-card'" in source
    assert "type: 'f1-weather-card'" in source
    assert "name: 'F1 Race Weather'" in source


def test_weather_card_uses_family_theme_responsive_layout_and_auto_height() -> None:
    source = _source()

    assert "static styles = [F1_THEME_STYLES" in source
    assert "radial-gradient(circle at 15% 10%, var(--f1-card-chip)" in source
    assert "font-family: var(--f1-card-heading-font-family" in source
    assert "font-family: var(--f1-card-display-font-family" in source
    assert 'class="fw-card" data-layout=${layoutMode}' in source
    assert ".fw-card[data-layout='narrow'] .fw-grid" in source
    assert "@media (prefers-reduced-motion: reduce)" in source
    assert "installSectionsAutoHeight(F1WeatherCard" in source
    assert "F1WeatherCard," in source


def test_weather_card_uses_compact_container_relative_visual_scale() -> None:
    source = _source()

    assert "--fw-card-title-size: clamp(14px, 2.2cqw, 18px);" in source
    assert "--fw-panel-title-size: clamp(11px, 3.5cqw, 13px);" in source
    assert "--fw-icon-box-size: clamp(40px, 12cqw, 46px);" in source
    assert "--fw-icon-size: clamp(24px, 7cqw, 28px);" in source
    assert "--fw-temperature-size: clamp(25px, 9cqw, 34px);" in source
    assert "font-size: var(--fw-temperature-size);" in source
    assert "--mdc-icon-size: var(--fw-icon-size);" in source


def test_weather_card_exposes_current_and_race_start_weather_semantics() -> None:
    source = _source()

    assert "Now at circuit" in source
    assert "Race start" in source
    assert "Current circuit weather is not available" in source
    assert "Race-start forecast is not available" in source
    assert "prefer_live_weather: true" in source
    assert "resolveF1WeatherComparison(" in source
    assert 'role="meter"' in source
    assert "aria-label=${label}" in source
