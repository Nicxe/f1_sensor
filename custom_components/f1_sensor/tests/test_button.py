from __future__ import annotations

import re
from unittest.mock import AsyncMock

from homeassistant.helpers.entity import EntityCategory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.f1_sensor.auth import (
    AUTH_RUNTIME_STATUS,
    AUTH_STATUS_NOT_CONFIGURED,
)
from custom_components.f1_sensor.auth_http import AUTH_PAIRING_SESSIONS
from custom_components.f1_sensor.button import (
    F1ClearF1TvAccessButton,
    F1JolpicaUserAgentTestButton,
    F1RefreshF1TvAccessButton,
    async_setup_entry,
)
from custom_components.f1_sensor.const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN


class _TimeoutSession:
    def __init__(self) -> None:
        self.headers = {"User-Agent": "session-ua"}
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        raise TimeoutError


@pytest.mark.asyncio
async def test_jolpica_ua_button_timeout_reports_failure(hass, monkeypatch) -> None:
    entry_id = "entry-test"
    session = _TimeoutSession()
    hass.data.setdefault(DOMAIN, {})[entry_id] = {
        "http_session": session,
        "user_agent": "configured-ua",
    }

    notifications = AsyncMock()
    monkeypatch.setattr(
        "custom_components.f1_sensor.button.persistent_notification.async_create",
        notifications,
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.button.time.time",
        lambda: 10.0,
    )

    button = F1JolpicaUserAgentTestButton(
        hass=hass,
        unique_id=f"{entry_id}_jolpica_ua_test",
        entry_id=entry_id,
        device_name="F1",
    )

    await button.async_press()

    assert session.calls == 1
    notifications.assert_awaited_once()
    message = notifications.await_args.args[1]
    assert "Jolpica UA test FAILED" in message
    assert "ua_configured='configured-ua'" in message
    assert "ua_session='session-ua'" in message


@pytest.mark.asyncio
async def test_clear_f1tv_access_button_clears_saved_token_and_reloads(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_EXPERIMENTAL_F1TV_AUTH", True
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    hass.config_entries.async_reload = AsyncMock(return_value=True)

    button = F1ClearF1TvAccessButton(
        hass=hass,
        unique_id=f"{entry.entry_id}_clear_f1tv_access",
        entry=entry,
        device_name="F1",
    )

    await button.async_press()

    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ""
    status = hass.data[DOMAIN][entry.entry_id][AUTH_RUNTIME_STATUS]
    assert status.status == AUTH_STATUS_NOT_CONFIGURED
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_clear_f1tv_access_button_is_inert_when_gate_closed(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_EXPERIMENTAL_F1TV_AUTH", False
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_reload = AsyncMock(return_value=True)

    button = F1ClearF1TvAccessButton(
        hass=hass,
        unique_id=f"{entry.entry_id}_clear_f1tv_access",
        entry=entry,
        device_name="F1",
    )

    await button.async_press()

    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == "Bearer existing-token"
    hass.config_entries.async_reload.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_f1tv_access_button_creates_pairing_notification(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_EXPERIMENTAL_F1TV_AUTH", True
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)
    notifications = AsyncMock()
    monkeypatch.setattr(
        "custom_components.f1_sensor.button.persistent_notification.async_create",
        notifications,
    )

    button = F1RefreshF1TvAccessButton(
        hass=hass,
        unique_id=f"{entry.entry_id}_refresh_f1tv_access",
        entry=entry,
        device_name="F1",
    )

    assert button.entity_category is EntityCategory.DIAGNOSTIC
    assert button.icon == "mdi:key-change"

    await button.async_press()

    notifications.assert_awaited_once()
    message = notifications.await_args.args[1]
    assert "Open F1TV Token Helper" in message
    assert "Bearer existing-token" not in message
    assert "subscription_token" not in message
    match = re.search(r"\((https?://[^)]+)\)", message)
    assert match is not None
    helper_url = URL(match.group(1))
    sessions = hass.data[DOMAIN][AUTH_PAIRING_SESSIONS]
    session = sessions[helper_url.query["session_id"]]
    assert session.entry_id == entry.entry_id
    assert helper_url.query["nonce"] == session.nonce


@pytest.mark.asyncio
async def test_refresh_f1tv_access_button_is_inert_when_gate_closed(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_EXPERIMENTAL_F1TV_AUTH", False
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    notifications = AsyncMock()
    monkeypatch.setattr(
        "custom_components.f1_sensor.button.persistent_notification.async_create",
        notifications,
    )

    button = F1RefreshF1TvAccessButton(
        hass=hass,
        unique_id=f"{entry.entry_id}_refresh_f1tv_access",
        entry=entry,
        device_name="F1",
    )

    await button.async_press()

    notifications.assert_not_called()
    assert AUTH_PAIRING_SESSIONS not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_jolpica_ua_button_is_not_added_when_only_f1tv_auth_is_public(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_EXPERIMENTAL_F1TV_AUTH", True
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "sensor_name": "F1",
            CONF_LIVE_TIMING_AUTH_HEADER: "Bearer existing-token",
        },
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "http_session": _TimeoutSession()
    }
    added = []

    await async_setup_entry(hass, entry, added.extend)

    assert any(isinstance(entity, F1ClearF1TvAccessButton) for entity in added)
    assert any(isinstance(entity, F1RefreshF1TvAccessButton) for entity in added)
    assert not any(isinstance(entity, F1JolpicaUserAgentTestButton) for entity in added)


@pytest.mark.asyncio
async def test_refresh_f1tv_access_button_is_added_without_saved_token(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_EXPERIMENTAL_F1TV_AUTH", True
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"loaded": True}
    added = []

    await async_setup_entry(hass, entry, added.extend)

    assert any(isinstance(entity, F1RefreshF1TvAccessButton) for entity in added)
    assert not any(isinstance(entity, F1ClearF1TvAccessButton) for entity in added)
