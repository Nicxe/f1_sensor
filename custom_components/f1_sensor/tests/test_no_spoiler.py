"""Tests for No Spoiler Mode manager and integration behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.f1_sensor.no_spoiler import NoSpoilerModeManager


# ---------------------------------------------------------------------------
# NoSpoilerModeManager unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manager_default_state(hass) -> None:
    """Manager starts inactive when storage has no saved state."""
    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()
    assert mgr.is_active is False


@pytest.mark.asyncio
async def test_manager_restores_active_state(hass) -> None:
    """Manager restores active=True from persisted storage on load."""
    mgr = NoSpoilerModeManager(hass)
    with patch.object(
        mgr._store, "async_load", AsyncMock(return_value={"active": True})
    ):
        await mgr.async_load()
    assert mgr.is_active is True


@pytest.mark.asyncio
async def test_manager_set_active_persists_and_notifies(hass) -> None:
    """set_active persists state and calls all registered listeners."""
    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    received: list[bool] = []
    unsub = mgr.add_listener(received.append)

    with patch.object(mgr._store, "async_save", AsyncMock()) as mock_save:
        await mgr.async_set_active(True)
        mock_save.assert_awaited_once_with({"active": True})

    assert mgr.is_active is True
    assert received == [True]

    # Deactivate
    with patch.object(mgr._store, "async_save", AsyncMock()) as mock_save:
        await mgr.async_set_active(False)
        mock_save.assert_awaited_once_with({"active": False})

    assert mgr.is_active is False
    assert received == [True, False]

    unsub()


@pytest.mark.asyncio
async def test_manager_set_active_noop_on_same_state(hass) -> None:
    """set_active does nothing when the state is unchanged."""
    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    received: list[bool] = []
    mgr.add_listener(received.append)

    with patch.object(mgr._store, "async_save", AsyncMock()) as mock_save:
        await mgr.async_set_active(False)  # already False
        mock_save.assert_not_awaited()

    assert received == []


@pytest.mark.asyncio
async def test_manager_listener_unsubscribe(hass) -> None:
    """Unsubscribing a listener stops it from receiving further notifications."""
    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    received: list[bool] = []
    unsub = mgr.add_listener(received.append)
    unsub()

    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    assert received == []


# ---------------------------------------------------------------------------
# _is_no_spoiler_blocked and _is_no_spoiler_jolpica_blocked unit tests
# ---------------------------------------------------------------------------


def _make_fake_coordinator(hass, *, replay_mode: bool = False):
    coord = SimpleNamespace()
    coord.hass = hass
    coord._replay_mode = replay_mode
    coord.data = {"sentinel": "old_data"}
    return coord


@pytest.mark.asyncio
async def test_is_no_spoiler_blocked_when_active(hass) -> None:
    from custom_components.f1_sensor import (
        _is_no_spoiler_blocked,
        _NO_SPOILER_MANAGER_KEY,
    )
    from custom_components.f1_sensor.const import DOMAIN

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()
    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = mgr
    coord = _make_fake_coordinator(hass)
    assert _is_no_spoiler_blocked(coord) is True


@pytest.mark.asyncio
async def test_is_no_spoiler_blocked_replay_bypasses(hass) -> None:
    """Replay mode bypasses the no-spoiler gate."""
    from custom_components.f1_sensor import (
        _is_no_spoiler_blocked,
        _NO_SPOILER_MANAGER_KEY,
    )
    from custom_components.f1_sensor.const import DOMAIN

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()
    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = mgr
    coord = _make_fake_coordinator(hass, replay_mode=True)
    assert _is_no_spoiler_blocked(coord) is False


@pytest.mark.asyncio
async def test_is_no_spoiler_blocked_when_inactive(hass) -> None:
    from custom_components.f1_sensor import (
        _is_no_spoiler_blocked,
        _NO_SPOILER_MANAGER_KEY,
    )
    from custom_components.f1_sensor.const import DOMAIN

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = mgr
    coord = _make_fake_coordinator(hass)
    assert _is_no_spoiler_blocked(coord) is False


@pytest.mark.asyncio
async def test_is_no_spoiler_jolpica_blocked_sensitive(hass) -> None:
    from custom_components.f1_sensor import (
        _is_no_spoiler_jolpica_blocked,
        _NO_SPOILER_MANAGER_KEY,
    )
    from custom_components.f1_sensor.const import DOMAIN

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()
    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = mgr
    coord = _make_fake_coordinator(hass)
    # Default: _no_spoiler_sensitive not set → treated as True (blocked)
    assert _is_no_spoiler_jolpica_blocked(coord) is True


@pytest.mark.asyncio
async def test_is_no_spoiler_jolpica_blocked_not_sensitive(hass) -> None:
    """Schedule coordinator (race_coordinator) is never blocked."""
    from custom_components.f1_sensor import (
        _is_no_spoiler_jolpica_blocked,
        _NO_SPOILER_MANAGER_KEY,
    )
    from custom_components.f1_sensor.const import DOMAIN

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()
    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = mgr
    coord = _make_fake_coordinator(hass)
    coord._no_spoiler_sensitive = False  # marked as schedule/calendar
    assert _is_no_spoiler_jolpica_blocked(coord) is False


# ---------------------------------------------------------------------------
# async_setup creates the manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_creates_manager(hass) -> None:
    """async_setup should create and load the NoSpoilerModeManager."""
    from custom_components.f1_sensor import async_setup, _NO_SPOILER_MANAGER_KEY
    from custom_components.f1_sensor.const import DOMAIN

    with patch(
        "custom_components.f1_sensor.NoSpoilerModeManager.async_load", AsyncMock()
    ) as mock_load:
        result = await async_setup(hass, {})

    assert result is True
    mgr = hass.data[DOMAIN][_NO_SPOILER_MANAGER_KEY]
    assert isinstance(mgr, NoSpoilerModeManager)
    mock_load.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_idempotent(hass) -> None:
    """Calling async_setup twice does not create a second manager instance."""
    from custom_components.f1_sensor import async_setup, _NO_SPOILER_MANAGER_KEY
    from custom_components.f1_sensor.const import DOMAIN

    with patch(
        "custom_components.f1_sensor.NoSpoilerModeManager.async_load", AsyncMock()
    ):
        await async_setup(hass, {})
        first = hass.data[DOMAIN][_NO_SPOILER_MANAGER_KEY]
        await async_setup(hass, {})
        second = hass.data[DOMAIN][_NO_SPOILER_MANAGER_KEY]

    assert first is second


# ---------------------------------------------------------------------------
# No Spoiler Mode switch entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_spoiler_switch_reflects_manager_state(hass) -> None:
    """Switch entity tracks manager state and updates HA state."""
    from custom_components.f1_sensor.switch import F1NoSpoilerSwitch

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    switch = F1NoSpoilerSwitch(mgr, "test_unique", "entry1", "F1")
    assert switch.is_on is False

    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    assert switch.is_on is True


@pytest.mark.asyncio
async def test_no_spoiler_switch_turn_on_activates_manager(hass) -> None:
    from custom_components.f1_sensor.switch import F1NoSpoilerSwitch

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    switch = F1NoSpoilerSwitch(mgr, "test_unique", "entry1", "F1")

    with patch.object(mgr._store, "async_save", AsyncMock()):
        await switch.async_turn_on()

    assert mgr.is_active is True


@pytest.mark.asyncio
async def test_no_spoiler_switch_turn_off_deactivates_manager(hass) -> None:
    from custom_components.f1_sensor.switch import F1NoSpoilerSwitch

    mgr = NoSpoilerModeManager(hass)
    with patch.object(
        mgr._store, "async_load", AsyncMock(return_value={"active": True})
    ):
        await mgr.async_load()

    switch = F1NoSpoilerSwitch(mgr, "test_unique", "entry1", "F1")
    assert switch.is_on is True

    with patch.object(mgr._store, "async_save", AsyncMock()):
        await switch.async_turn_off()

    assert mgr.is_active is False
    assert switch.is_on is False


# ---------------------------------------------------------------------------
# LiveSessionSupervisor gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supervisor_no_spoiler_active_property(hass) -> None:
    """_is_no_spoiler_active returns True when manager is active."""
    from custom_components.f1_sensor import _NO_SPOILER_MANAGER_KEY
    from custom_components.f1_sensor.const import DOMAIN
    from custom_components.f1_sensor.live_window import LiveSessionSupervisor

    mgr = NoSpoilerModeManager(hass)
    with patch.object(mgr._store, "async_load", AsyncMock(return_value=None)):
        await mgr.async_load()

    hass.data.setdefault(DOMAIN, {})[_NO_SPOILER_MANAGER_KEY] = mgr

    session_coord = MagicMock()
    bus = MagicMock()
    http_session = MagicMock()
    supervisor = LiveSessionSupervisor(
        hass, session_coord, bus, http_session=http_session
    )

    assert supervisor._is_no_spoiler_active is False

    with patch.object(mgr._store, "async_save", AsyncMock()):
        await mgr.async_set_active(True)

    assert supervisor._is_no_spoiler_active is True
