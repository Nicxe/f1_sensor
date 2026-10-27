"""Acceptance tests for Phase 2 platform and demand-driven runtime work."""

from __future__ import annotations

from importlib import import_module
from unittest.mock import Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import async_migrate_entry
from custom_components.f1_sensor.const import (
    CONF_LIVE_TIMING_AUTH_HEADER,
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_LIVE,
    SUPPORTED_SENSOR_KEYS,
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
from custom_components.f1_sensor.weather import F1RaceWeatherCoordinator


def _typed_runtime(entry_id, registry):
    return F1RuntimeData(
        static=StaticRuntime(),
        live=None,
        replay=None,
        track_map=TrackMapRuntimeData(TrackMapStore(entry_id)),
        cache=CacheRuntime(object(), {}, {}, {}),
        providers=ProviderRuntime(ProviderRegistry()),
        history=HistoryRuntime(service=object()),
        capabilities=CapabilityState(frozenset(), frozenset(), frozenset()),
        legacy=registry,
    )


def test_feature_plan_static_only_has_zero_live_demand() -> None:
    plan = build_feature_plan({"next_race", "weather"}, live_enabled=True)

    assert plan.live_required is False
    assert plan.active_live_features == frozenset()
    assert plan.coordinators == frozenset()
    assert plan.requested_streams == frozenset()
    assert plan.stream_reasons == {}


@pytest.mark.parametrize("feature", ["driver_positions", "pitstops"])
def test_session_scoped_features_request_identity_without_session_sensor(
    feature,
) -> None:
    plan = build_feature_plan({feature}, live_enabled=True)

    assert "SessionInfo" in plan.public_streams
    assert plan.stream_reasons["SessionInfo"] == (feature,)


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


def test_team_radio_feature_plan_includes_driver_identity_stream() -> None:
    plan = build_feature_plan({"team_radio"}, live_enabled=True)

    assert plan.coordinators == frozenset({"team_radio", "session_info"})
    assert plan.requested_streams == frozenset(
        {"DriverList", "Heartbeat", "TeamRadio", "SessionInfo"}
    )
    assert plan.stream_reasons["DriverList"] == ("team_radio",)
    assert plan.stream_reasons["TeamRadio"] == ("team_radio",)


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
    entry.runtime_data = _typed_runtime(entry.entry_id, typed_registry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"source": "legacy"}

    assert entry_runtime_registry(hass, entry.entry_id) is typed_registry


@pytest.mark.parametrize(
    ("platform", "entity_suffix"),
    (
        ("sensor", "next_race"),
        ("binary_sensor", "race_week"),
        ("media_player", "replay_player"),
        ("button", "delay_calibration_match"),
        ("number", "live_delay_number"),
        ("select", "live_delay_reference"),
        ("calendar", "f1_season_calendar"),
        ("weather", "weather_entity"),
    ),
)
@pytest.mark.asyncio
async def test_platform_setup_uses_typed_runtime_even_with_stale_legacy_data(
    hass, platform, entity_suffix
) -> None:
    """Refactoring lookup syntax is safe; ignoring the typed owner is not."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"sensor_name": "F1"},
        options={
            "disabled_sensors": sorted(
                SUPPORTED_SENSOR_KEYS - {"next_race", "race_week", "calendar"}
            )
        },
    )
    entry.add_to_hass(hass)
    coordinator = Mock(spec=DataUpdateCoordinator, data={}, last_update_success=True)
    registry = dict.fromkeys(
        (
            "driver_coordinator",
            "constructor_coordinator",
            "last_race_coordinator",
            "season_results_coordinator",
            "sprint_results_coordinator",
        )
    )
    registry["race_coordinator"] = coordinator
    if platform == "media_player":
        registry["replay_controller"] = object()
    elif platform == "button":
        registry["calibration_manager"] = object()
    elif platform == "number":
        registry["live_delay_controller"] = Mock(current=15)
    elif platform == "select":
        registry["delay_reference_controller"] = Mock(current="session_live")
    elif platform == "weather":
        registry["race_weather_coordinator"] = Mock(
            spec=F1RaceWeatherCoordinator, data={}, last_update_success=True
        )
    entry.runtime_data = _typed_runtime(entry.entry_id, registry)
    # An old mapping may still exist during migration. Using it loses entities.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    entities = []
    await import_module(f"custom_components.f1_sensor.{platform}").async_setup_entry(
        hass, entry, lambda added, *_: entities.extend(added)
    )
    assert f"{entry.entry_id}_{entity_suffix}" in {
        entity.unique_id for entity in entities
    }


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

    assert entry.version == 4
    assert entry.minor_version == 4
    assert entry.entry_id == original_entry_id
    assert entry.unique_id == DOMAIN
    assert entry.data == {
        "sensor_name": "My F1",
        CONF_LIVE_TIMING_AUTH_HEADER: "Bearer secret-placeholder",
        "entity_name_mode": "localized",
        "legacy_race_control_events": True,
    }
    assert entry.options["enable_race_control"] is True
    assert entry.options["disabled_sensors"] == ["favorite_driver", "team_radio"]
    assert entry.options["live_delay_seconds"] == 15
    assert entry.options[CONF_OPERATION_MODE] == OPERATION_MODE_LIVE


@pytest.mark.parametrize("live_enabled", [True, False])
def test_team_radio_only_plan_supplies_session_path_resource_when_live_enabled(
    live_enabled,
) -> None:
    plan = build_feature_plan({"team_radio"}, live_enabled=live_enabled)
    if not live_enabled:
        assert plan.requested_streams == frozenset()
        assert plan.coordinators == frozenset()
        return
    assert "SessionInfo" in plan.public_streams
    assert plan.stream_reasons["SessionInfo"] == ("team_radio",)
    assert plan.needs("session_info")
    assert plan.needs("team_radio")
