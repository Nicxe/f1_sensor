from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
import pytest

BLUEPRINT_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "blueprints"
    / "automation"
    / "homeassistant"
    / "f1_race_control_notifications.yaml"
)
BLUEPRINT_DEST = Path(
    "blueprints/automation/homeassistant/f1_race_control_notifications.yaml"
)


async def _install_blueprint(hass: HomeAssistant) -> None:
    destination = Path(hass.config.path(str(BLUEPRINT_DEST)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        BLUEPRINT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _register_notification_service(
    hass: HomeAssistant,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    register_service = getattr(hass.services, "async_" + "register")

    async def _record(call: ServiceCall) -> None:
        calls.append(dict(call.data))

    register_service("test", "record_notification", _record)
    return calls


async def _set_race_control_state(
    hass: HomeAssistant,
    state: str,
    *,
    category: str = "Flag",
    event_id: str = "",
    flag: str = "",
    message: str | None = None,
) -> None:
    hass.states.async_set(
        "sensor.test_race_control",
        state,
        {
            "category": category,
            "event_id": event_id,
            "flag": flag,
            "message": message or state,
            "scope": "Track",
        },
    )
    await hass.async_block_till_done()


async def _setup_blueprint_automation(
    hass: HomeAssistant,
    *,
    filter_blue_flags: bool,
) -> bool:
    config = {
        "automation": [
            {
                "id": "race_control_notifications_blueprint_test",
                "alias": "Race Control Notifications Blueprint Test",
                "use_blueprint": {
                    "path": "homeassistant/f1_race_control_notifications.yaml",
                    "input": {
                        "race_control_sensor": "sensor.test_race_control",
                        "require_active_phase": False,
                        "session_status_sensor": "",
                        "active_session_phases": ["live", "suspended"],
                        "enable_current_session_filter": False,
                        "current_session_sensor": "",
                        "allowed_current_sessions": [
                            "Practice 1",
                            "Practice 2",
                            "Practice 3",
                            "Qualifying",
                            "Sprint Qualifying",
                            "Sprint",
                            "Race",
                        ],
                        "allowed_flags": [],
                        "filter_blue_flags": filter_blue_flags,
                        "allowed_categories": "",
                        "include_keywords": "",
                        "exclude_keywords": "",
                        "title_prefix": "F1 Race Control Test",
                        "include_fields": ["flag"],
                        "cooldown_seconds": 0,
                        "notification_actions": [
                            {
                                "action": "test.record_notification",
                                "data": {
                                    "event_id": "{{ race_control_event_id }}",
                                    "flag": "{{ race_control_flag }}",
                                    "message": "{{ notification_message }}",
                                    "title": "{{ notification_title }}",
                                },
                            }
                        ],
                        "activation_condition": [],
                    },
                },
            }
        ]
    }
    result = await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()
    return result


@pytest.mark.asyncio
async def test_blue_flag_notification_is_sent_when_filter_is_disabled(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)
    await _set_race_control_state(hass, "Idle")

    assert await _setup_blueprint_automation(hass, filter_blue_flags=False)
    calls.clear()

    await _set_race_control_state(
        hass,
        "WAVED BLUE FLAG FOR CAR 43",
        event_id="blue-1",
        flag="BLUE",
    )

    assert calls == [
        {
            "event_id": "blue-1",
            "flag": "BLUE",
            "message": "WAVED BLUE FLAG FOR CAR 43\nFlag: BLUE",
            "title": "F1 Race Control Test: BLUE",
        }
    ]


@pytest.mark.asyncio
async def test_blue_flag_notification_can_be_filtered_out(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)
    await _set_race_control_state(hass, "Idle")

    assert await _setup_blueprint_automation(hass, filter_blue_flags=True)
    calls.clear()

    await _set_race_control_state(
        hass,
        "WAVED BLUE FLAG FOR CAR 43",
        event_id="blue-2",
        flag="BLUE",
    )

    assert calls == []


@pytest.mark.asyncio
async def test_non_blue_flag_notification_still_sends_when_blue_filter_is_enabled(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)
    await _set_race_control_state(hass, "Idle")

    assert await _setup_blueprint_automation(hass, filter_blue_flags=True)
    calls.clear()

    await _set_race_control_state(
        hass,
        "YELLOW FLAG IN SECTOR 2",
        event_id="yellow-1",
        flag="YELLOW",
    )

    assert calls == [
        {
            "event_id": "yellow-1",
            "flag": "YELLOW",
            "message": "YELLOW FLAG IN SECTOR 2\nFlag: YELLOW",
            "title": "F1 Race Control Test: YELLOW",
        }
    ]
