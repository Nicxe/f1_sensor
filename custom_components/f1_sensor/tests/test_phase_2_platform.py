"""Acceptance tests for Phase 2 platform and demand-driven runtime work."""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import async_migrate_entry
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_LIVE,
)
from custom_components.f1_sensor.entity import entry_runtime_registry
from custom_components.f1_sensor.feature_plan import build_feature_plan
from custom_components.f1_sensor.providers import ProviderRegistry
from custom_components.f1_sensor.runtime import (
    CacheRuntime,
    CapabilityState,
    F1RuntimeData,
    HistoryRuntime,
    ProviderRuntime,
    StaticRuntime,
)
from custom_components.f1_sensor.track_map import TrackMapRuntimeData, TrackMapStore

EXPECTED_CARD_TYPES = {
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

DEPRECATED_CARD_TYPES = {"f1-session-archive-card"}


def test_feature_plan_static_only_has_zero_live_demand() -> None:
    plan = build_feature_plan({"next_race", "weather"}, live_enabled=True)

    assert plan.live_required is False
    assert plan.active_live_features == frozenset()
    assert plan.coordinators == frozenset()
    assert plan.requested_streams == frozenset()
    assert plan.stream_reasons == {}


def test_feature_plan_declares_exact_streams_and_reasons() -> None:
    plan = build_feature_plan(
        {"track_status", "formation_start"},
        live_enabled=True,
    )

    assert plan.coordinators == frozenset({"track_status", "formation_start"})
    assert plan.requested_streams == frozenset(
        {"Heartbeat", "TrackStatus", "SessionInfo", "SessionStatus", "CarData.z"}
    )
    assert plan.public_streams == frozenset(
        {"Heartbeat", "TrackStatus", "SessionInfo", "SessionStatus"}
    )
    assert plan.auth_streams == frozenset({"CarData.z"})
    assert plan.stream_reasons == {
        "CarData.z": ("formation_start",),
        "Heartbeat": ("live_transport_health",),
        "SessionInfo": ("formation_start",),
        "SessionStatus": ("formation_start",),
        "TrackStatus": ("track_status",),
    }


def test_provider_sources_share_one_golden_record_contract() -> None:
    registry = ProviderRegistry()
    jolpica = registry.normalize(
        "jolpica",
        "race_schedule",
        {"MRData": {"RaceTable": {"season": "2026", "round": "7"}}},
        final=True,
    )
    live = registry.normalize(
        "f1_live",
        "SessionInfo",
        {
            "Key": "race",
            "Utc": "2026-05-24T13:00:00Z",
            "Meeting": {"Key": "monaco"},
        },
        revision=4,
    )
    replay = registry.normalize(
        "replay",
        "SessionInfo",
        {
            "Key": "race",
            "Utc": "2026-05-24T13:00:00Z",
            "Meeting": {"Key": "monaco"},
        },
        revision=4,
    )

    golden_keys = {
        "provider",
        "kind",
        "source_session_id",
        "canonical_session_id",
        "event_timestamp",
        "received_timestamp",
        "revision",
        "sequence",
        "final",
        "quality",
        "coverage_reason",
        "payload",
    }
    assert all(
        set(record.as_dict()) == golden_keys for record in (jolpica, live, replay)
    )
    assert jolpica.canonical_session_id == "2026:7"
    assert live.canonical_session_id == replay.canonical_session_id == "monaco:race"
    assert live.event_timestamp == replay.event_timestamp == "2026-05-24T13:00:00Z"
    assert [jolpica.sequence, live.sequence, replay.sequence] == [1, 2, 3]
    assert all(
        "payload" not in record for record in registry.diagnostics()["latest"].values()
    )


def test_platform_runtime_prefers_typed_config_entry_data(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    typed_registry = {"source": "typed"}
    entry.runtime_data = F1RuntimeData(
        static=StaticRuntime(),
        live=None,
        replay=None,
        track_map=TrackMapRuntimeData(TrackMapStore(entry.entry_id)),
        cache=CacheRuntime(object(), {}, {}, {}),
        providers=ProviderRuntime(ProviderRegistry()),
        history=HistoryRuntime(service=object()),
        capabilities=CapabilityState(frozenset(), frozenset(), frozenset()),
        legacy=typed_registry,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"source": "legacy"}

    assert entry_runtime_registry(hass, entry.entry_id) is typed_registry


def test_platform_modules_do_not_read_entry_runtime_directly() -> None:
    component_dir = Path(__file__).resolve().parents[1]
    for filename in (
        "sensor.py",
        "binary_sensor.py",
        "media_player.py",
        "button.py",
        "number.py",
        "select.py",
        "calendar.py",
        "weather.py",
    ):
        source = (component_dir / filename).read_text(encoding="utf-8")
        assert "entry_runtime_registry" in source
        assert "hass.data[DOMAIN][entry.entry_id]" not in source
        assert ".get(entry.entry_id" not in source


@pytest.mark.asyncio
async def test_options_migration_preserves_identity_and_connection_data(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=DOMAIN,
        data={
            "sensor_name": "My F1",
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer secret-placeholder",
            "entity_name_mode": "localized",
            "disabled_sensors": ["team_radio"],
            "enable_race_control": False,
            "live_delay_seconds": 15,
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
        },
        options={"enable_race_control": True},
    )
    original_entry_id = entry.entry_id
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 3
    assert entry.entry_id == original_entry_id
    assert entry.unique_id == DOMAIN
    assert entry.data == {
        "sensor_name": "My F1",
        CONF_LIVE_TIMING_AUTH_HEADER: "Bearer secret-placeholder",
        "entity_name_mode": "localized",
    }
    assert entry.options["enable_race_control"] is True
    assert entry.options["disabled_sensors"] == ["team_radio"]
    assert entry.options["live_delay_seconds"] == 15
    assert entry.options[CONF_OPERATION_MODE] == OPERATION_MODE_LIVE


def test_frontend_loader_preserves_all_card_tags_and_eagerly_loads_bundle(
    bundled_card_path: Path,
) -> None:
    root = bundled_card_path.parent
    main_source = bundled_card_path.read_text(encoding="utf-8")
    loader_source = (root / "register.js").read_text(encoding="utf-8")
    registry_source = (root / "platform" / "card-registry.js").read_text(
        encoding="utf-8"
    )

    registered_cards = set(
        re.findall(r"customElements\.define\('([^']+)'", main_source)
    )
    metadata_cards = set(re.findall(r"\['(f1-[^']+-card)'\s*,", registry_source))
    assert metadata_cards == EXPECTED_CARD_TYPES
    assert EXPECTED_CARD_TYPES <= registered_cards
    assert {f"{card}-editor" for card in EXPECTED_CARD_TYPES} <= registered_cards
    assert DEPRECATED_CARD_TYPES <= registered_cards
    assert {f"{card}-editor" for card in DEPRECATED_CARD_TYPES}.isdisjoint(
        registered_cards
    )
    assert (
        "await import(`./f1-sensor-live-data-card.js${cacheSuffix}`)" in loader_source
    )
    assert "await import(`./platform/card-registry.js${cacheSuffix}`)" in loader_source
    assert loader_source.rstrip().endswith(
        "await import(`./f1-sensor-live-data-card.js${cacheSuffix}`);"
    )
    assert "MutationObserver" not in loader_source
    assert "import './f1-sensor-live-data-card.js'" not in loader_source
    assert "const LitElement = F1BaseElement;" in main_source
    for module in ("base-card", "actions", "accessibility", "i18n"):
        assert (root / "platform" / f"{module}.js").is_file()
