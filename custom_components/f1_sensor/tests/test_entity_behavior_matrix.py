"""Behavior coverage for shared entity stream and naming helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from custom_components.f1_sensor.const import (
    CONF_OPERATION_MODE,
    DOMAIN,
    OPERATION_MODE_DEVELOPMENT,
    OPERATION_MODE_LIVE,
)
from custom_components.f1_sensor.entity import (
    F1AuxEntity,
    F1BaseEntity,
    _entity_name_from_key,
    _entry_name_settings,
    _safe_write_ha_state,
    default_object_id,
    is_auth_gated_stream_active,
    is_replay_only_stream_active,
    register_entry_name_settings,
)
from custom_components.f1_sensor.replay_mode import ReplayState


class _Base(F1BaseEntity):
    _attr_translation_key = "track_status"

    def __init__(self, coordinator):
        super().__init__(coordinator, "uid", "entry", "F1")
        self.clears = 0

    def _clear_state(self):
        self.clears += 1


class _Aux(F1AuxEntity):
    _attr_translation_key = "track_status"


def test_entity_naming_invalid_mode_and_fallbacks() -> None:
    register_entry_name_settings(
        "invalid", {"entity_name_mode": "bad", "entity_name_language": "sv_SE"}
    )
    assert default_object_id(None) is None
    assert default_object_id("  ") is None
    assert _entity_name_from_key(None, entry_id="invalid") is None
    assert _entity_name_from_key("custom_untranslated", entry_id="invalid") == (
        "Custom untranslated"
    )
    assert _entry_name_settings(None)
    assert _entity_name_from_key("_") is None


def test_stream_activation_helpers_cover_live_replay_and_auth(hass) -> None:
    assert is_replay_only_stream_active(None, "entry") is False
    hass.data.setdefault(DOMAIN, {})["entry"] = {}
    assert is_replay_only_stream_active(hass, "entry") is False

    live_state = SimpleNamespace(is_live=True, reason="live")
    registry = hass.data[DOMAIN]["entry"] = {
        "live_state": live_state,
        CONF_OPERATION_MODE: OPERATION_MODE_DEVELOPMENT,
    }
    assert is_replay_only_stream_active(hass, "entry") is True
    registry[CONF_OPERATION_MODE] = OPERATION_MODE_LIVE
    assert is_replay_only_stream_active(hass, "entry") is False
    live_state.reason = "replay"
    assert is_replay_only_stream_active(hass, "entry") is True

    assert is_auth_gated_stream_active(None, "entry", "TimingData") is False
    registry[CONF_OPERATION_MODE] = OPERATION_MODE_DEVELOPMENT
    assert is_auth_gated_stream_active(hass, "entry", "TimingData") is False
    registry[CONF_OPERATION_MODE] = OPERATION_MODE_LIVE
    live_state.is_live = False
    assert is_auth_gated_stream_active(hass, "entry", "TimingData") is False
    live_state.is_live = True
    assert is_auth_gated_stream_active(hass, "entry", "TimingData") is False
    live_state.reason = "live"
    registry["signalr_stream_capabilities"] = {"auth_enabled": False}
    assert is_auth_gated_stream_active(hass, "entry", "TimingData") is False
    registry["signalr_stream_capabilities"] = {
        "auth_enabled": True,
        "auth_gated_live_streams": "bad",
    }
    assert is_auth_gated_stream_active(hass, "entry", "TimingData") is False
    registry["signalr_stream_capabilities"]["auth_gated_live_streams"] = {"TimingData"}
    assert is_auth_gated_stream_active(hass, "entry", "TimingData") is True


async def test_base_entity_availability_stream_transitions_and_metadata(hass) -> None:
    coordinator = SimpleNamespace(available=True)
    entity = _Base(coordinator)
    entity.hass = hass
    registry = hass.data.setdefault(DOMAIN, {}).setdefault("entry", {})
    registry.update(
        {
            CONF_OPERATION_MODE: OPERATION_MODE_LIVE,
            "live_state": SimpleNamespace(is_live=False, reason="idle"),
        }
    )
    assert entity.available is False

    registry["live_state"] = SimpleNamespace(is_live=False, reason="no-spoiler")
    assert entity.available is True
    registry["live_state"] = SimpleNamespace(is_live=True, reason="live")
    registry["live_bus"] = SimpleNamespace(last_stream_activity_age=lambda: None)
    assert entity.available is False
    registry["live_bus"] = SimpleNamespace(last_stream_activity_age=lambda: 91)
    assert entity.available is False
    registry["live_bus"] = SimpleNamespace(last_stream_activity_age=lambda: 1)
    assert entity.available is True

    registry["replay_controller"] = SimpleNamespace(state=ReplayState.PLAYING)
    registry["live_bus"] = SimpleNamespace(last_stream_activity_age=lambda: None)
    assert entity.available is True
    assert entity._is_stream_active() is True
    assert entity.name
    assert entity.suggested_object_id == "f1_track_status"
    assert entity.device_info["name"] == "F1 - System"

    registry["live_state"].is_live = False
    registry["replay_controller"].state = ReplayState.IDLE
    assert entity._is_stream_active() is False
    assert entity._handle_stream_state(False) is True
    assert entity.clears == 1
    registry["live_state"].is_live = True
    assert entity._handle_stream_state(False) is False
    assert entity._handle_stream_state(True) is True
    registry["live_state"].is_live = False
    assert entity._handle_stream_state(True) is True
    assert entity.clears >= 2


def test_aux_entity_stream_metadata_and_threadsafe_write(hass, monkeypatch) -> None:
    aux = _Aux("aux", "entry", "F1")
    aux.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=False),
        "replay_controller": SimpleNamespace(state=ReplayState.PAUSED),
    }
    assert aux._is_stream_active() is True
    assert aux.suggested_object_id == "f1_track_status"
    assert aux.device_info["model"] == "F1 Sensor - System"

    scheduled = Mock()
    fake_loop = Mock()
    fake = SimpleNamespace(
        hass=SimpleNamespace(loop=fake_loop),
        async_schedule_update_ha_state=scheduled,
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(
            asyncio, "get_running_loop", Mock(side_effect=RuntimeError("no loop"))
        )
        _safe_write_ha_state(fake)
    fake_loop.call_soon_threadsafe.assert_called_once_with(scheduled, False)
    _safe_write_ha_state(SimpleNamespace(hass=None))


def test_entity_exact_super_fallback_and_broken_runtime_paths(hass) -> None:
    class NoKeyBase(F1BaseEntity):
        pass

    class NoKeyAux(F1AuxEntity):
        pass

    class BrokenReplay:
        @property
        def state(self):
            raise RuntimeError("state")

    coordinator = SimpleNamespace(available=True)
    base = NoKeyBase(coordinator, "base", "entry", "F1")
    aux = NoKeyAux("aux", "entry", "F1")
    base.hass = hass
    aux.hass = hass
    hass.data.setdefault(DOMAIN, {})["entry"] = {
        "live_state": SimpleNamespace(is_live=False),
        "replay_controller": BrokenReplay(),
    }
    assert base.suggested_object_id is None
    assert aux.suggested_object_id is None
    assert base._is_stream_active() is False
    assert aux._is_stream_active() is False

    transition = _Base(coordinator)
    transition.hass = hass
    transition._stream_last_active = None
    assert transition._handle_stream_state(True) is True
    assert transition.clears == 1

    class BrokenHass:
        @property
        def loop(self):
            raise RuntimeError("loop")

    _safe_write_ha_state(
        SimpleNamespace(
            hass=BrokenHass(),
            async_schedule_update_ha_state=Mock(),
        )
    )
