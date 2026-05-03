from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import json
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.auth_http import (
    AUTH_CALLBACK_MAX_BODY_BYTES,
    async_create_f1tv_pairing_session,
    async_process_f1tv_pairing_callback,
)
from custom_components.f1_sensor.const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN


def _part(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _jwt(exp: datetime) -> str:
    return ".".join(
        (
            _part({"alg": "RS256", "typ": "JWT"}),
            _part({"exp": int(exp.timestamp())}),
            "signature",
        )
    )


async def test_pairing_session_is_not_created_when_gate_closed(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)

    assert async_create_f1tv_pairing_session(hass, entry) is None


async def test_pairing_session_contains_no_token_when_gate_open(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)

    session = async_create_f1tv_pairing_session(
        hass,
        entry,
        flow_id="flow-id",
        callback_url="http://ha.local:8123/api/f1_sensor/auth/f1tv/callback",
    )

    assert session is not None
    assert session.entry_id == entry.entry_id
    assert "subscription_token" not in session.helper_url
    assert "Bearer" not in session.helper_url
    assert "flow-id" in session.helper_url


async def test_valid_callback_saves_token_and_reloads_entry(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    token = _jwt(datetime.now(UTC) + timedelta(days=2))
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    hass.config_entries.async_reload = AsyncMock(return_value=True)
    session = async_create_f1tv_pairing_session(
        hass,
        entry,
        callback_url="http://ha.local:8123/api/f1_sensor/auth/f1tv/callback",
    )
    assert session is not None

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": session.session_id,
            "nonce": session.nonce,
            "subscription_token": token,
            "source": "browser_extension",
        },
    )

    assert status is HTTPStatus.OK
    assert response["ok"] is True
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == f"Bearer {token}"
    assert session.used is True
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    assert token not in str(response)


async def test_callback_rejects_invalid_nonce(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    token = _jwt(datetime.now(UTC) + timedelta(days=2))
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    session = async_create_f1tv_pairing_session(hass, entry)
    assert session is not None

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": session.session_id,
            "nonce": "wrong",
            "subscription_token": token,
        },
    )

    assert status is HTTPStatus.FORBIDDEN
    assert response == {"ok": False, "code": "invalid_nonce"}
    assert CONF_LIVE_TIMING_AUTH_HEADER not in entry.data


async def test_callback_rejects_reused_session(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    token = _jwt(datetime.now(UTC) + timedelta(days=2))
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)
    hass.config_entries.async_reload = AsyncMock(return_value=True)
    session = async_create_f1tv_pairing_session(hass, entry)
    assert session is not None
    payload = {
        "session_id": session.session_id,
        "nonce": session.nonce,
        "subscription_token": token,
    }

    await async_process_f1tv_pairing_callback(hass, payload)
    status, response = await async_process_f1tv_pairing_callback(hass, payload)

    assert status is HTTPStatus.GONE
    assert response == {"ok": False, "code": "pairing_already_used"}


async def test_callback_rejects_token_in_query(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {},
        query={"subscription_token": "secret"},
    )

    assert status is HTTPStatus.BAD_REQUEST
    assert response == {"ok": False, "code": "token_in_query"}
    assert "secret" not in str(response)


async def test_callback_rejects_oversized_body(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {},
        body_size=AUTH_CALLBACK_MAX_BODY_BYTES + 1,
    )

    assert status is HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response == {"ok": False, "code": "body_too_large"}


async def test_callback_is_inert_when_gate_closed(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": "session",
            "nonce": "nonce",
            "subscription_token": "secret",
        },
    )

    assert status is HTTPStatus.NOT_FOUND
    assert response == {"ok": False, "code": "gate_closed"}
    assert CONF_LIVE_TIMING_AUTH_HEADER not in entry.data
    assert "secret" not in str(response)
