from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
import pytest

BLUEPRINT_SOURCE = Path(__file__).resolve().parent / "fixtures" / "f1_track_status.yaml"
BLUEPRINT_DEST = Path("blueprints/automation/homeassistant/f1_track_status.yaml")
AUTOMATION_ENTITY_ID = "automation.track_status_blueprint_test"
StateSpec = str | tuple[str, dict[str, Any]]


async def _install_blueprint(hass: HomeAssistant) -> None:
    destination = Path(hass.config.path(str(BLUEPRINT_DEST)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        BLUEPRINT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _register_services(
    hass: HomeAssistant,
) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    register_service = getattr(hass.services, "async_" + "register")

    def _recorder(domain: str):
        async def _record(call: ServiceCall) -> None:
            calls.append((f"{domain}.{call.service}", dict(call.data)))

        return _record

    register_service("light", "turn_on", _recorder("light"))
    register_service("light", "turn_off", _recorder("light"))
    register_service("select", "select_option", _recorder("select"))
    return calls


async def _set_states(hass: HomeAssistant, states: dict[str, StateSpec]) -> None:
    for entity_id, value in states.items():
        if isinstance(value, tuple):
            state, attributes = value
        else:
            state, attributes = value, {}
        hass.states.async_set(entity_id, state, attributes)
    await hass.async_block_till_done()


async def _setup_blueprint_automation(
    hass: HomeAssistant,
    *,
    clear_color: list[int] | None = None,
    yellow_color: list[int] | None = None,
    extra_inputs: dict[str, Any] | None = None,
) -> bool:
    blueprint_inputs: dict[str, Any] = {
        "session_status_entity": "sensor.test_session_status",
        "track_status_entity": "sensor.test_track_status",
        "light_target": "light.test_track_status",
        "active_session_phases": ["live", "suspended"],
        "enable_current_session_filter": False,
        "transition_s": 0,
        "snapshot_pre_race": False,
        "snapshot_before_alert": False,
        "clear_behavior_mode": "steady",
        "yellow_red_mode": "steady",
        "yellow_red_after_flash": "steady",
        "sc_vsc_mode": "steady",
        "sc_vsc_after_flash": "steady",
        "end_delay_min": 0,
        "end_action": "turn_off",
        "cleanup_scenes_on_end": False,
        "enable_notifications": False,
        "color_clear": clear_color or [11, 22, 33],
        "color_yellow": yellow_color or [44, 55, 66],
    }
    if extra_inputs:
        blueprint_inputs.update(extra_inputs)

    config = {
        "automation": [
            {
                "id": "track_status_blueprint_test",
                "alias": "Track Status Blueprint Test",
                "use_blueprint": {
                    "path": "homeassistant/f1_track_status.yaml",
                    "input": blueprint_inputs,
                },
            }
        ]
    }
    result = await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()
    return result


def _last_triggered(hass: HomeAssistant) -> str | None:
    state = hass.states.get(AUTOMATION_ENTITY_ID)
    assert state is not None
    return state.attributes.get("last_triggered")


@pytest.mark.asyncio
async def test_blueprint_syncs_track_light_when_session_enters_active(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "pre",
        },
    )

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "live"})

    assert calls == [
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
                "brightness_pct": 100,
                "rgb_color": [11, 22, 33],
                "transition": 0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_blueprint_ignores_internal_session_updates_without_track_change(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "YELLOW",
            "sensor.test_session_status": "pre",
        },
    )

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "live"})
    assert calls == [
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
                "brightness_pct": 100,
                "rgb_color": [44, 55, 66],
                "transition": 0,
            },
        )
    ]
    last_triggered = _last_triggered(hass)
    assert last_triggered is not None

    calls.clear()
    await _set_states(hass, {"sensor.test_session_status": "suspended"})

    assert calls == []
    assert _last_triggered(hass) == last_triggered


@pytest.mark.asyncio
async def test_blueprint_keeps_end_action_on_session_exit(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
        },
    )

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "finished"})

    assert calls == [
        (
            "light.turn_off",
            {
                "entity_id": ["light.test_track_status"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_blueprint_prefers_wled_playlist_over_preset_for_track_status(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "SC",
            "sensor.test_session_status": "pre",
            "light.test_track_status": "off",
            "select.test_wled_playlist": (
                "Idle",
                {"options": ["Safety Car Playlist"]},
            ),
            "select.test_wled_preset": (
                "Idle",
                {"options": ["Safety Car Preset"]},
            ),
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_wled_advanced": True,
            "wled_playlist_entity": "select.test_wled_playlist",
            "wled_preset_entity": "select.test_wled_preset",
            "wled_playlist_sc": "Safety Car Playlist",
            "wled_preset_sc": "Safety Car Preset",
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "live"})

    assert calls == [
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
            },
        ),
        (
            "select.select_option",
            {
                "entity_id": "select.test_wled_playlist",
                "option": "Safety Car Playlist",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_blueprint_falls_back_to_preset_when_playlist_is_invalid(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "SC",
            "sensor.test_session_status": "pre",
            "light.test_track_status": "off",
            "select.test_wled_playlist": (
                "Idle",
                {"options": ["Different Playlist"]},
            ),
            "select.test_wled_preset": (
                "Idle",
                {"options": ["Safety Car Preset"]},
            ),
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_wled_advanced": True,
            "wled_playlist_entity": "select.test_wled_playlist",
            "wled_preset_entity": "select.test_wled_preset",
            "wled_playlist_sc": "Safety Car Playlist",
            "wled_preset_sc": "Safety Car Preset",
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "live"})

    assert calls == [
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
            },
        ),
        (
            "select.select_option",
            {
                "entity_id": "select.test_wled_preset",
                "option": "Safety Car Preset",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_blueprint_applies_finished_override_before_end_action(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
            "light.test_track_status": "off",
            "select.test_wled_playlist": (
                "Idle",
                {"options": ["Checkered Playlist"]},
            ),
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_wled_advanced": True,
            "wled_playlist_entity": "select.test_wled_playlist",
            "wled_playlist_finished": "Checkered Playlist",
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "finished"})

    assert calls == [
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
            },
        ),
        (
            "select.select_option",
            {
                "entity_id": "select.test_wled_playlist",
                "option": "Checkered Playlist",
            },
        ),
        (
            "light.turn_off",
            {
                "entity_id": ["light.test_track_status"],
            },
        ),
    ]
