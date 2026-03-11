from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.f1_sensor.button import F1JolpicaUserAgentTestButton
from custom_components.f1_sensor.const import DOMAIN


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
