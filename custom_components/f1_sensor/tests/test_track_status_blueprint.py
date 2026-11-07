from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

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


async def _register_services(
    hass: HomeAssistant,
) -> list[tuple[str, dict[str, Any]]]:
    assert await async_setup_component(hass, "scene", {})
    await hass.async_block_till_done()
    calls: list[tuple[str, dict[str, Any]]] = []
    register_service = getattr(hass.services, "async_" + "register")

    async def _ignore_device_call(call: ServiceCall) -> None:
        """Keep device actions isolated while recording dispatch on the event bus."""

    for domain, service in (
        ("input_boolean", "turn_on"),
        ("light", "turn_on"),
        ("light", "turn_off"),
        ("select", "select_option"),
    ):
        register_service(domain, service, _ignore_device_call)

    @callback
    def _record_service_call(event: Event) -> None:
        if event.data["domain"] in {"scene", "light", "select", "input_boolean"}:
            calls.append(
                (
                    f"{event.data['domain']}.{event.data['service']}",
                    dict(event.data["service_data"]),
                )
            )

    hass.bus.async_listen(EVENT_CALL_SERVICE, _record_service_call)
    return calls


async def _set_states(hass: HomeAssistant, states: dict[str, StateSpec]) -> None:
    for entity_id, value in states.items():
        if isinstance(value, tuple):
            state, attributes = value
        else:
            state, attributes = value, {}
        hass.states.async_set(entity_id, state, attributes)
    await hass.async_block_till_done()


async def _set_states_without_full_drain(
    hass: HomeAssistant, states: dict[str, StateSpec]
) -> None:
    for entity_id, value in states.items():
        if isinstance(value, tuple):
            state, attributes = value
        else:
            state, attributes = value, {}
        hass.states.async_set(entity_id, state, attributes)
    await asyncio.sleep(0)
    await asyncio.sleep(0)


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


async def _register_stateful_light(hass: HomeAssistant) -> None:
    """Model immediate RGB light feedback, keeping real HA scene snapshots."""

    async def update_light(call: ServiceCall) -> None:
        entity_ids = call.data["entity_id"]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            attributes = dict(state.attributes) if state else {}
            attributes.update(
                {key: value for key, value in call.data.items() if key != "entity_id"}
            )
            hass.states.async_set(
                entity_id, "on" if call.service == "turn_on" else "off", attributes
            )

    for service in ("turn_on", "turn_off"):
        hass.services.async_register("light", service, update_light)


async def _drain_blueprint_actions(hass: HomeAssistant) -> None:
    """Drain runnable actions without waiting for a delayed restore."""
    for _ in range(50):
        await asyncio.sleep(0)


@pytest.mark.parametrize("next_alert", ["YELLOW", "RED", "SC", "VSC"])
@pytest.mark.parametrize("clear_gap", [4.205, 12])
@pytest.mark.asyncio
async def test_blueprint_preserves_snapshot_across_delayed_clear(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    next_alert: str,
    clear_gap: float,
) -> None:
    """Issue 969: a new alert must not snapshot the temporary green color."""
    await _install_blueprint(hass)
    await _register_services(hass)
    await _register_stateful_light(hass)
    original = [90, 60, 30]
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "suspended",
            "light.test_track_status": (
                "on",
                {
                    "rgb_color": original,
                    "color_mode": "rgb",
                    "supported_color_modes": ["rgb"],
                    "brightness": 180,
                },
            ),
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        clear_color=[0, 255, 0],
        extra_inputs={
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_after_delay",
            "clear_restore_delay_s": 10,
        },
    )

    async def advance(seconds: float) -> None:
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)
        await _drain_blueprint_actions(hass)
        if seconds >= 10:
            await hass.async_block_till_done()

    await _set_states(hass, {"sensor.test_track_status": "RED"})
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    assert list(hass.states.get("light.test_track_status").attributes["rgb_color"]) == [
        0,
        255,
        0,
    ]
    await advance(clear_gap)
    await _set_states(hass, {"sensor.test_track_status": next_alert})
    await advance(50.467)
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    await advance(11)
    assert (
        list(hass.states.get("light.test_track_status").attributes["rgb_color"])
        == original
    )

    # Attribute-only updates must not start a fresh green/restore cycle.
    await _set_states_without_full_drain(
        hass, {"sensor.test_track_status": ("CLEAR", {"message": "AllClear"})}
    )
    await _drain_blueprint_actions(hass)
    assert (
        list(hass.states.get("light.test_track_status").attributes["rgb_color"])
        == original
    )

    # A later independent alert must capture the user's new light setting.
    new_color = [30, 60, 90]
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.test_track_status", "rgb_color": new_color},
        blocking=True,
    )
    await _set_states(hass, {"sensor.test_track_status": "YELLOW"})
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    await advance(11)
    assert (
        list(hass.states.get("light.test_track_status").attributes["rgb_color"])
        == new_color
    )


@pytest.mark.parametrize("cleanup_on_end", [False, True])
@pytest.mark.asyncio
async def test_blueprint_delayed_snapshot_session_boundaries(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    cleanup_on_end: bool,
) -> None:
    """Protect session-start CLEAR and discard old snapshots for the next session."""
    await _install_blueprint(hass)
    await _register_services(hass)
    await _register_stateful_light(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "pre",
            "light.test_track_status": "off",
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_pre_race": True,
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_after_delay",
            "clear_restore_delay_s": 10,
            "end_action": "restore_pre_race",
            "cleanup_scenes_on_end": cleanup_on_end,
        },
    )

    async def advance(seconds: float) -> None:
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)
        await _drain_blueprint_actions(hass)
        if seconds >= 10:
            await hass.async_block_till_done()

    await _set_states_without_full_drain(hass, {"sensor.test_session_status": "live"})
    await _drain_blueprint_actions(hass)
    await advance(4)
    await _set_states(hass, {"sensor.test_track_status": "YELLOW"})
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    await advance(11)
    assert hass.states.get("light.test_track_status").state == "off"

    # End the session before the next pending restore can run.
    await _set_states(hass, {"light.test_track_status": "on"})
    await _set_states(hass, {"sensor.test_track_status": "RED"})
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    await advance(4)
    await _set_states(hass, {"sensor.test_session_status": "finished"})
    await advance(11)
    assert hass.states.get("light.test_track_status").state == "off"

    # A retained pre-alert snapshot was ON, while the new session starts OFF.
    await _set_states_without_full_drain(hass, {"sensor.test_session_status": "live"})
    await _drain_blueprint_actions(hass)
    await advance(4)
    await _set_states(hass, {"sensor.test_track_status": "SC"})
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    await advance(11)
    assert hass.states.get("light.test_track_status").state == "off"


@pytest.mark.asyncio
async def test_blueprint_failed_delayed_restore_keeps_snapshot(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed restore must not discard the only saved pre-alert state."""
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
            "light.test_track_status": "off",
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_after_delay",
            "clear_restore_delay_s": 10,
        },
    )

    async def fail_restore(call: ServiceCall) -> None:
        raise HomeAssistantError("Test restore failed")

    hass.services.async_register("scene", "turn_on", fail_restore)
    await _set_states(hass, {"sensor.test_track_status": "RED"})
    calls.clear()
    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    await _drain_blueprint_actions(hass)
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert any(service == "scene.turn_on" for service, _ in calls)
    assert not any(service == "scene.delete" for service, _ in calls)
    assert hass.states.get("scene.automation_track_status_blueprint_test_pre_alert")
    calls.clear()
    await _set_states(hass, {"sensor.test_track_status": "YELLOW"})
    assert not any(service == "scene.create" for service, _ in calls)


@pytest.mark.asyncio
async def test_blueprint_syncs_track_light_when_session_enters_active(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
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
async def test_blueprint_restores_pre_race_scene_after_start_clear_delay(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "light.test_track_status": "off",
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "pre",
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_pre_race": True,
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_after_delay",
            "clear_restore_delay_s": 0,
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": "live"})

    assert calls == [
        (
            "scene.create",
            {
                "scene_id": "automation_track_status_blueprint_test_pre_race",
                "snapshot_entities": ["light.test_track_status"],
            },
        ),
        (
            "scene.create",
            {
                "scene_id": "automation_track_status_blueprint_test_pre_alert",
                "snapshot_entities": ["light.test_track_status"],
            },
        ),
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
                "brightness_pct": 100,
                "rgb_color": [11, 22, 33],
                "transition": 0,
            },
        ),
        (
            "scene.turn_on",
            {
                "entity_id": "scene.automation_track_status_blueprint_test_pre_race",
            },
        ),
        (
            "scene.delete",
            {"entity_id": "scene.automation_track_status_blueprint_test_pre_alert"},
        ),
    ]
    scene = hass.states.get("scene.automation_track_status_blueprint_test_pre_race")
    assert scene is not None and scene.state != "unknown"


@pytest.mark.asyncio
async def test_blueprint_ignores_internal_session_updates_without_track_change(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
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


@pytest.mark.parametrize(
    (
        "current_state",
        "current_metadata",
        "status_metadata",
        "allowed_sessions",
        "session_phase",
        "active_phases",
        "expected_red",
    ),
    [
        ("unknown", {}, {}, ["Qualifying"], "suspended", ["live", "suspended"], True),
        (
            "unknown",
            {"name": "Sprint Qualifying", "last_label": "Sprint Qualifying"},
            {},
            ["Sprint Qualifying"],
            "suspended",
            ["live", "suspended"],
            True,
        ),
        (
            "unknown",
            {
                "type": "Practice",
                "name": "Practice 3",
                "number": 3,
                "last_label": "Practice 3",
            },
            {},
            ["Practice 3"],
            "suspended",
            ["live", "suspended"],
            True,
        ),
        (
            "unknown",
            {"type": "Race", "name": "Race", "last_label": "Race"},
            {},
            ["Race"],
            "suspended",
            ["live", "suspended"],
            True,
        ),
        (
            "unknown",
            {"type": "Race", "name": "Sprint", "last_label": "Sprint"},
            {},
            ["Sprint"],
            "suspended",
            ["live", "suspended"],
            True,
        ),
        (
            "unknown",
            {
                "type": "Race",
                "name": "Sprint Shootout",
                "last_label": "Sprint Qualifying",
            },
            {},
            ["Sprint Qualifying"],
            "suspended",
            ["live", "suspended"],
            True,
        ),
        (
            "unknown",
            {"live_status": "Finished"},
            {},
            ["Qualifying"],
            "break",
            ["live", "suspended", "break"],
            True,
        ),
        ("unknown", {}, {}, ["Race"], "suspended", ["live", "suspended"], False),
        (
            "unknown",
            {},
            {"start": "2026-11-08T14:00:00"},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            False,
        ),
        (
            "unknown",
            {"start": None},
            {},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            False,
        ),
        (
            "unknown",
            {},
            {"gmt_offset": "00:00:00"},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            False,
        ),
        (
            "unknown",
            {"type": "Practice", "name": "Practice 1", "number": 1},
            {},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            False,
        ),
        (
            "unavailable",
            {},
            {},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            False,
        ),
        ("unknown", {}, {}, ["Qualifying"], "live", ["live", "suspended"], False),
        ("unknown", {}, {}, ["Qualifying"], "suspended", ["live"], False),
        (
            "Qualifying",
            {},
            {},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            True,
        ),
        (
            "Practice 1",
            {},
            {},
            ["Qualifying"],
            "suspended",
            ["live", "suspended"],
            False,
        ),
    ],
    ids=[
        "current-qualifying",
        "current-sprint-qualifying",
        "current-practice",
        "current-race",
        "current-sprint",
        "legacy-sprint-shootout",
        "enabled-qualifying-break",
        "disallowed-session",
        "different-session-start",
        "missing-session-identity",
        "different-timezone",
        "stale-label-for-different-session-type",
        "unavailable-current-session",
        "unknown-outside-interruption",
        "suspension-not-enabled",
        "known-allowed-label",
        "known-disallowed-label",
    ],
)
@pytest.mark.asyncio
async def test_blueprint_red_after_suspension_requires_current_session_scope(
    hass: HomeAssistant,
    current_state: str,
    current_metadata: dict[str, Any],
    status_metadata: dict[str, Any],
    allowed_sessions: list[str],
    session_phase: str,
    active_phases: list[str],
    expected_red: bool,
) -> None:
    """Follow the red flag after Aborted without accepting another session's label."""
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    identity = {"start": "2026-11-07T15:00:00", "gmt_offset": "-03:00:00"}
    metadata = {
        **identity,
        "type": "Qualifying",
        "name": "Qualifying",
        "number": None,
        "session_key": 11408,
        "last_label": "Qualifying",
        "live_status": "Aborted",
        "active": False,
        **current_metadata,
    }
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "YELLOW",
            "sensor.test_session_status": ("live", {**identity, **status_metadata}),
            "sensor.test_current_session": ("Qualifying", metadata),
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_current_session_filter": True,
            "current_session_entity": "sensor.test_current_session",
            "allowed_current_sessions": allowed_sessions,
            "active_session_phases": active_phases,
        },
    )
    await _set_states(
        hass,
        {
            "sensor.test_current_session": (current_state, metadata),
            "sensor.test_session_status": (
                session_phase,
                {**identity, **status_metadata},
            ),
        },
    )
    calls.clear()

    # The recorded Q2 flag arrived 348 ms after the suspension, not before it.
    await _set_states(hass, {"sensor.test_track_status": "RED"})

    assert calls == (
        [
            (
                "light.turn_on",
                {
                    "entity_id": ["light.test_track_status"],
                    "brightness_pct": 100,
                    "rgb_color": [255, 0, 0],
                    "transition": 0,
                },
            )
        ]
        if expected_red
        else []
    )


@pytest.mark.asyncio
async def test_blueprint_filtered_session_exit_keeps_last_label_cleanup(
    hass: HomeAssistant,
) -> None:
    """Restricting flag updates must not suppress the suspended session's end action."""
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    identity = {"start": "2026-11-07T15:00:00", "gmt_offset": "-03:00:00"}
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "RED",
            "sensor.test_session_status": ("suspended", identity),
            "sensor.test_current_session": (
                "unknown",
                {
                    **identity,
                    "type": "Qualifying",
                    "name": "Qualifying",
                    "last_label": "Qualifying",
                    "live_status": "Aborted",
                    "active": False,
                },
            ),
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_current_session_filter": True,
            "current_session_entity": "sensor.test_current_session",
            "allowed_current_sessions": ["Qualifying"],
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_session_status": ("finished", identity)})

    assert calls == [("light.turn_off", {"entity_id": ["light.test_track_status"]})]


@pytest.mark.asyncio
async def test_blueprint_keeps_end_action_on_session_exit(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
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
async def test_blueprint_notifies_before_continuous_sc_flash(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "input_boolean.test_notify_flag": "off",
            "light.test_track_status": "off",
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_notifications": True,
            "notification_actions": [
                {
                    "action": "input_boolean.turn_on",
                    "target": {"entity_id": "input_boolean.test_notify_flag"},
                }
            ],
            "sc_vsc_mode": "flash_continuous",
        },
    )
    calls.clear()

    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "SC"})

    assert calls[0] == (
        "input_boolean.turn_on",
        {"entity_id": ["input_boolean.test_notify_flag"]},
    )
    assert calls[1] == (
        "light.turn_on",
        {
            "entity_id": ["light.test_track_status"],
            "brightness_pct": 100,
            "rgb_color": [255, 0, 0],
        },
    )

    await _set_states(hass, {"sensor.test_track_status": "CLEAR"})


@pytest.mark.asyncio
async def test_blueprint_uses_native_snapshot_entity_list_for_pre_alert_scene(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "light.test_track_status": "off",
            "number.test_wled_intensity": "128",
            "number.test_wled_speed": "64",
            "select.test_wled_palette": "Default",
            "select.test_wled_playlist": "Idle",
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_wled_advanced": True,
            "snapshot_before_alert": True,
            "wled_intensity_entity": "number.test_wled_intensity",
            "wled_palette_entity": "select.test_wled_palette",
            "wled_playlist_entity": "select.test_wled_playlist",
            "wled_speed_entity": "number.test_wled_speed",
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_track_status": "SC"})

    assert calls[0] == (
        "scene.create",
        {
            "scene_id": "automation_track_status_blueprint_test_pre_alert",
            "snapshot_entities": [
                "light.test_track_status",
                "select.test_wled_playlist",
                "select.test_wled_palette",
                "number.test_wled_intensity",
                "number.test_wled_speed",
            ],
        },
    )


@pytest.mark.asyncio
async def test_blueprint_prefers_wled_playlist_over_preset_for_track_status(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
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
    calls = await _register_services(hass)
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
async def test_blueprint_resets_wled_effect_when_clear_falls_back_to_standard_mode(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "SC",
            "sensor.test_session_status": "pre",
            "light.test_track_status": "off",
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
            "wled_preset_entity": "select.test_wled_preset",
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

    calls.clear()
    await _set_states(hass, {"sensor.test_track_status": "CLEAR"})

    assert calls == [
        (
            "light.turn_on",
            {
                "entity_id": ["light.test_track_status"],
                "brightness_pct": 100,
                "rgb_color": [11, 22, 33],
                "transition": 0,
                "effect": "Solid",
            },
        )
    ]


@pytest.mark.asyncio
async def test_blueprint_restores_pre_alert_scene_after_wled_clear_delay(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
            "light.test_track_status": "off",
            "select.test_wled_preset": (
                "Idle",
                {"options": ["Safety Car Preset", "Green Flag Preset"]},
            ),
        },
    )

    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "enable_wled_advanced": True,
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_after_delay",
            "clear_restore_delay_s": 0,
            "wled_preset_entity": "select.test_wled_preset",
            "wled_preset_sc": "Safety Car Preset",
            "wled_preset_clear": "Green Flag Preset",
        },
    )
    calls.clear()

    await _set_states(hass, {"sensor.test_track_status": "SC"})

    assert calls == [
        (
            "scene.create",
            {
                "scene_id": "automation_track_status_blueprint_test_pre_alert",
                "snapshot_entities": [
                    "light.test_track_status",
                    "select.test_wled_preset",
                ],
            },
        ),
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

    calls.clear()
    await _set_states(hass, {"sensor.test_track_status": "CLEAR"})

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
                "option": "Green Flag Preset",
            },
        ),
        (
            "scene.turn_on",
            {
                "entity_id": "scene.automation_track_status_blueprint_test_pre_alert",
            },
        ),
        (
            "scene.delete",
            {"entity_id": "scene.automation_track_status_blueprint_test_pre_alert"},
        ),
    ]


@pytest.mark.asyncio
async def test_blueprint_applies_finished_override_before_end_action(
    hass: HomeAssistant,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
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


@pytest.mark.parametrize("clear_mode", ["restore_immediately", "restore_after_delay"])
@pytest.mark.parametrize("wled_enabled", [False, True], ids=["rgb", "wled"])
@pytest.mark.asyncio
async def test_blueprint_first_clear_without_snapshot_uses_clear_fallback(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    clear_mode: str,
    wled_enabled: bool,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "unknown",
            "sensor.test_session_status": "live",
            "light.test_track_status": "off",
            "select.test_wled_preset": ("Idle", {"options": ["Idle", "Green Flag"]}),
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_before_alert": True,
            "clear_behavior_mode": clear_mode,
            "clear_restore_delay_s": 0,
            "enable_wled_advanced": wled_enabled,
            "wled_preset_entity": "select.test_wled_preset",
            "wled_preset_clear": "Green Flag",
        },
    )
    calls.clear()
    caplog.clear()

    await _set_states(hass, {"sensor.test_track_status": "CLEAR"})

    expected_calls = (
        [
            ("light.turn_on", {"entity_id": ["light.test_track_status"]}),
            (
                "select.select_option",
                {"entity_id": "select.test_wled_preset", "option": "Green Flag"},
            ),
        ]
        if wled_enabled
        else [
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
    )
    assert calls == expected_calls
    assert "missing or not currently available" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_blueprint_cleans_up_session_without_an_alert_snapshot(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "pre",
            "light.test_track_status": "off",
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_pre_race": True,
            "snapshot_before_alert": True,
            "cleanup_scenes_on_end": True,
        },
    )
    await _set_states(hass, {"sensor.test_session_status": "live"})
    assert hass.states.get("scene.automation_track_status_blueprint_test_pre_race")
    assert (
        hass.states.get("scene.automation_track_status_blueprint_test_pre_alert")
        is None
    )
    calls.clear()
    caplog.clear()

    await _set_states(hass, {"sensor.test_session_status": "finished"})

    assert calls == [
        ("light.turn_off", {"entity_id": ["light.test_track_status"]}),
        (
            "scene.delete",
            {"entity_id": "scene.automation_track_status_blueprint_test_pre_race"},
        ),
    ]
    assert (
        hass.states.get("scene.automation_track_status_blueprint_test_pre_race") is None
    )
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_blueprint_skips_snapshot_removed_during_clear_delay(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "SC",
            "sensor.test_session_status": "live",
            "light.test_track_status": "off",
        },
    )
    scene_entity = "scene.automation_track_status_blueprint_test_pre_alert"
    await hass.services.async_call(
        "scene",
        "create",
        {
            "scene_id": "automation_track_status_blueprint_test_pre_alert",
            "snapshot_entities": ["light.test_track_status"],
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(scene_entity)
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_after_delay",
            "clear_restore_delay_s": 15,
        },
    )
    calls.clear()

    await _set_states_without_full_drain(hass, {"sensor.test_track_status": "CLEAR"})
    for _ in range(20):
        if calls and calls[-1][0] == "light.turn_on":
            break
        await asyncio.sleep(0)
    assert calls and calls[-1][0] == "light.turn_on"
    await hass.services.async_call(
        "scene", "delete", {"entity_id": scene_entity}, blocking=True
    )
    calls.clear()
    caplog.clear()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()

    assert calls == []
    assert "missing or not currently available" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.asyncio
async def test_blueprint_restores_real_pre_alert_snapshot_when_clear_returns(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": "CLEAR",
            "sensor.test_session_status": "live",
            "light.test_track_status": "off",
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_before_alert": True,
            "clear_behavior_mode": "restore_immediately",
        },
    )
    await _set_states(hass, {"sensor.test_track_status": "SC"})
    scene_entity = "scene.automation_track_status_blueprint_test_pre_alert"
    assert hass.states.get(scene_entity)
    await _set_states(hass, {"light.test_track_status": "on"})
    calls.clear()
    caplog.clear()

    await _set_states(hass, {"sensor.test_track_status": "CLEAR"})

    assert calls == [
        ("scene.turn_on", {"entity_id": scene_entity}),
        ("light.turn_off", {"entity_id": "light.test_track_status"}),
    ]
    assert hass.states.get(scene_entity).state != "unknown"
    assert "missing or not currently available" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.parametrize("track_state", ["YELLOW", "RED", "SC", "VSC"])
@pytest.mark.asyncio
async def test_blueprint_timed_alert_without_snapshot_keeps_steady_color(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    track_state: str,
) -> None:
    await _install_blueprint(hass)
    calls = await _register_services(hass)
    await _set_states(
        hass,
        {
            "sensor.test_track_status": track_state,
            "sensor.test_session_status": "pre",
            "light.test_track_status": "off",
        },
    )
    assert await _setup_blueprint_automation(
        hass,
        extra_inputs={
            "snapshot_before_alert": True,
            "yellow_red_mode": "flash_timed",
            "yellow_red_flash_duration_s": 1,
            "yellow_red_after_flash": "restore_previous",
            "sc_vsc_mode": "flash_timed",
            "sc_vsc_flash_duration_s": 1,
            "sc_vsc_after_flash": "restore_previous",
            "flash_interval_s": 1,
        },
    )
    calls.clear()
    caplog.clear()

    await _set_states_without_full_drain(hass, {"sensor.test_session_status": "live"})
    for _ in range(20):
        if calls:
            break
        await asyncio.sleep(0)
    assert calls and calls[-1][0] == "light.turn_on"
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    for _ in range(20):
        if calls[-1][0] == "light.turn_off":
            break
        await asyncio.sleep(0)
    assert calls[-1][0] == "light.turn_off"
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert [service for service, _ in calls] == [
        "light.turn_on",
        "light.turn_off",
        "light.turn_on",
    ]
    assert calls[-1][1]["transition"] == 0
    assert (
        hass.states.get("scene.automation_track_status_blueprint_test_pre_alert")
        is None
    )
    assert "missing or not currently available" not in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
