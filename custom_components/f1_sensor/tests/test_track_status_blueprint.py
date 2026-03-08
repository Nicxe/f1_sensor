from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
import pytest

ROOT = Path(__file__).resolve().parents[3]
BLUEPRINT_SOURCE = (
    ROOT / "blueprints" / "automation" / "homeassistant" / "f1_track_status.yaml"
)
BLUEPRINT_DEST = Path("blueprints/automation/homeassistant/f1_track_status.yaml")
AUTOMATION_ENTITY_ID = "automation.track_status_blueprint_test"


async def _install_blueprint(hass: HomeAssistant) -> None:
    destination = Path(hass.config.path(str(BLUEPRINT_DEST)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        BLUEPRINT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _register_light_services(
    hass: HomeAssistant,
) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def _record(call: ServiceCall) -> None:
        calls.append((call.service, dict(call.data)))

    hass.services.async_register("light", "turn_on", _record)
    hass.services.async_register("light", "turn_off", _record)
    return calls


async def _set_states(hass: HomeAssistant, states: dict[str, str]) -> None:
    for entity_id, state in states.items():
        hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


async def _setup_blueprint_automation(
    hass: HomeAssistant,
    *,
    clear_color: list[int] | None = None,
    yellow_color: list[int] | None = None,
) -> bool:
    config = {
        "automation": [
            {
                "id": "track_status_blueprint_test",
                "alias": "Track Status Blueprint Test",
                "use_blueprint": {
                    "path": "homeassistant/f1_track_status.yaml",
                    "input": {
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
                    },
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
    calls = _register_light_services(hass)
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
            "turn_on",
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
    calls = _register_light_services(hass)
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
            "turn_on",
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
    calls = _register_light_services(hass)
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
            "turn_off",
            {
                "entity_id": ["light.test_track_status"],
            },
        )
    ]
