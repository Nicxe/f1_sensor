from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BLUEPRINT_FILENAME = "f1_incident_notifications.yaml"
_REPO_PATH = _REPO_ROOT / "blueprints" / _BLUEPRINT_FILENAME
_HA_PATH = (
    _REPO_ROOT / "blueprints" / "automation" / "homeassistant" / _BLUEPRINT_FILENAME
)
BLUEPRINT_SOURCE = _REPO_PATH if _REPO_PATH.exists() else _HA_PATH
BLUEPRINT_DEST = Path(
    "blueprints/automation/homeassistant/f1_incident_notifications.yaml"
)


async def _install_blueprint(hass: HomeAssistant) -> None:
    destination = Path(hass.config.path(str(BLUEPRINT_DEST)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        BLUEPRINT_SOURCE.read_text(encoding="utf-8"), encoding="utf-8"
    )


def _register_notification_service(hass: HomeAssistant) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    register_service = getattr(hass.services, "async_" + "register")

    async def _record(call: ServiceCall) -> None:
        calls.append(dict(call.data))

    register_service("test", "record_notification", _record)
    return calls


async def _setup_blueprint_automation(
    hass: HomeAssistant,
    *,
    min_confidence: str = "medium",
    allowed_session_types: list[str] | None = None,
    include_candidate_events: bool = False,
    include_cleared_notifications: bool = False,
) -> bool:
    config = {
        "automation": [
            {
                "id": "incident_notifications_blueprint_test",
                "alias": "Incident Notifications Blueprint Test",
                "use_blueprint": {
                    "path": "homeassistant/f1_incident_notifications.yaml",
                    "input": {
                        "notify_services": "test.record_notification",
                        "notify_targets": [],
                        "min_confidence": min_confidence,
                        "allowed_session_types": allowed_session_types
                        or ["race", "sprint", "qualifying"],
                        "include_candidate_events": include_candidate_events,
                        "include_cleared_notifications": include_cleared_notifications,
                        "title_prefix": "F1 Incident Test",
                    },
                },
            }
        ]
    }
    result = await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()
    return result


def _incident_event(
    *,
    incident_id: str = "2026-miami-race-10-2026-05-03T17:00:01Z",
    phase: str = "confirmed",
    confidence: str = "medium",
    session_type: str = "race",
    session_name: str = "Race",
    location_description: str | None = None,
) -> dict[str, Any]:
    return {
        "entry_id": "incident-entry",
        "incident_id": incident_id,
        "phase": phase,
        "confidence": confidence,
        "reason": "timing_stopped",
        "driver": {
            "racing_number": "10",
            "tla": "GAS",
            "name": "Pierre Gasly",
            "team": "Alpine",
        },
        "session": {
            "meeting_name": "Miami Grand Prix",
            "session_name": session_name,
            "session_type": session_type,
            "session_key": f"2026-miami-{session_type}",
        },
        "track_status": {
            "status": None,
            "message": None,
        },
        "race_control": {
            "message": None,
            "category": None,
            "flag": None,
        },
        "location": {
            "status": "OnTrack" if location_description else None,
            "source": "live" if location_description else None,
            "stale": False if location_description else None,
            "confidence": "high" if location_description else None,
            "description": location_description,
            "sector": 2 if location_description else None,
            "corner": None,
            "pit_lane": False if location_description else None,
            "track_segment": 42 if location_description else None,
            "distance_to_track": 4.2 if location_description else None,
            "geometry_source": (
                "static_circuit_geometry" if location_description else None
            ),
            "fallback_state": "static_catalog" if location_description else None,
            "updated_at": ("2026-05-03T17:00:01Z" if location_description else None),
        },
        "signals": ["timing_stopped"],
        "started_at": "2026-05-03T17:00:01Z",
        "updated_at": "2026-05-03T17:00:01Z",
        "data_quality": "live",
    }


async def _fire_incident(hass: HomeAssistant, **kwargs: Any) -> None:
    hass.bus.async_fire("f1_sensor_incident", _incident_event(**kwargs))
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_default_incident_notification_is_neutral_and_tagged(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _fire_incident(hass)

    assert calls == [
        {
            "title": "F1 Incident Test (MEDIUM)",
            "message": "Possible on-track incident: GAS stopped\nSession: Race",
            "data": {
                "tag": "f1_incident_2026_miami_race_10_2026_05_03t17_00_01z",
                "group": "f1_incidents",
                "incident_id": "2026-miami-race-10-2026-05-03T17:00:01Z",
                "phase": "confirmed",
                "confidence": "medium",
            },
        }
    ]


@pytest.mark.asyncio
async def test_default_filters_skip_candidate_cleared_practice_and_testing(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _fire_incident(hass, phase="candidate", confidence="high")
    await _fire_incident(hass, phase="cleared", confidence="high")
    await _fire_incident(hass, confidence="low")
    await _fire_incident(
        hass,
        confidence="medium",
        session_type="practice",
        session_name="Practice 1",
    )
    await _fire_incident(
        hass,
        confidence="high",
        session_type="practice",
        session_name="Practice 1",
    )
    await _fire_incident(
        hass,
        confidence="high",
        session_type="testing",
        session_name="Testing",
    )

    assert calls == []


@pytest.mark.asyncio
async def test_practice_high_can_pass_when_practice_is_selected(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)

    assert await _setup_blueprint_automation(
        hass,
        min_confidence="high",
        allowed_session_types=["race", "sprint", "qualifying", "practice"],
    )
    calls.clear()

    await _fire_incident(
        hass,
        confidence="high",
        session_type="practice",
        session_name="Practice 1",
    )

    assert len(calls) == 1
    assert calls[0]["message"] == (
        "Possible on-track incident: GAS stopped\nSession: Practice 1"
    )


@pytest.mark.asyncio
async def test_incident_notification_includes_optional_location_description(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _fire_incident(hass, location_description="on track, sector 2")

    assert calls[0]["message"] == (
        "Possible on-track incident: GAS stopped\n"
        "Session: Race\n"
        "Location: on track, sector 2"
    )


@pytest.mark.asyncio
async def test_candidate_and_cleared_notifications_are_opt_in(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)

    assert await _setup_blueprint_automation(
        hass,
        include_candidate_events=True,
        include_cleared_notifications=True,
    )
    calls.clear()

    await _fire_incident(hass, phase="candidate", confidence="medium")
    await _fire_incident(hass, phase="cleared", confidence="medium")

    assert [call["data"]["phase"] for call in calls] == ["candidate", "cleared"]
    assert calls[1]["message"] == (
        "Possible on-track incident: GAS cleared\nSession: Race"
    )


@pytest.mark.asyncio
async def test_incident_updates_use_same_notification_tag_for_dedupe(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = _register_notification_service(hass)

    assert await _setup_blueprint_automation(hass)
    calls.clear()

    await _fire_incident(hass, phase="confirmed", confidence="medium")
    await _fire_incident(hass, phase="updated", confidence="high")

    assert len(calls) == 2
    assert calls[0]["data"]["tag"] == calls[1]["data"]["tag"]
    assert calls[1]["data"]["phase"] == "updated"
    assert calls[1]["data"]["confidence"] == "high"
