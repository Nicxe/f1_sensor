from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components.http import KEY_HASS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.auth_http import (
    AUTH_CALLBACK_ATTEMPTS,
    AUTH_CALLBACK_MAX_BODY_BYTES,
    AUTH_CALLBACK_METRICS,
    AUTH_CALLBACK_RATE_LIMIT,
    F1TvAuthCallbackView,
    _async_complete_pairing_flow,
    _callback_rate_limited,
    _is_safe_callback_url,
    _record_callback_failure,
    async_create_f1tv_pairing_session,
    async_get_f1tv_callback_url,
    async_pop_f1tv_pairing_session_result,
    async_process_f1tv_pairing_callback,
    async_setup_f1tv_auth_http,
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


async def test_callback_url_uses_browser_visible_frontend_base(hass):
    """Use the frontend origin instead of a container-only backend address."""
    hass.config.api = Mock(
        use_ssl=False,
        local_ip="172.18.0.2",
        port=8123,
    )
    request = Mock(headers={"HA-Frontend-Base": "https://ha.example.com/"})

    with patch("homeassistant.helpers.http.current_request") as current_request:
        current_request.get.return_value = request

        assert async_get_f1tv_callback_url(hass) == (
            "https://ha.example.com/api/f1_sensor/auth/f1tv/callback"
        )


async def test_callback_url_rejects_public_http_frontend_base(hass):
    """Never send a token to a public callback over cleartext HTTP."""
    request = Mock(headers={"HA-Frontend-Base": "http://ha.example.com/"})

    with (
        patch("homeassistant.helpers.http.current_request") as current_request,
        patch(
            "custom_components.f1_sensor.auth_http.get_url",
            return_value="https://safe.example.com",
        ),
    ):
        current_request.get.return_value = request

        assert async_get_f1tv_callback_url(hass) == (
            "https://safe.example.com/api/f1_sensor/auth/f1tv/callback"
        )


def test_callback_url_policy_allows_https_and_local_http_only() -> None:
    assert _is_safe_callback_url(
        "https://ha.example.com/api/f1_sensor/auth/f1tv/callback"
    )
    assert _is_safe_callback_url(
        "http://192.168.1.10:8123/api/f1_sensor/auth/f1tv/callback"
    )
    assert _is_safe_callback_url(
        "http://homeassistant.local:8123/api/f1_sensor/auth/f1tv/callback"
    )
    assert not _is_safe_callback_url(
        "http://ha.example.com/api/f1_sensor/auth/f1tv/callback"
    )
    assert not _is_safe_callback_url("https://ha.example.com/other")


async def test_pairing_session_is_not_created_when_gate_closed(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
    entry = MockConfigEntry(domain=DOMAIN, data={"sensor_name": "F1"})
    entry.add_to_hass(hass)

    assert async_create_f1tv_pairing_session(hass, entry) is None


async def test_pairing_session_contains_no_token_when_gate_open(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
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


async def test_flow_pairing_callback_stores_runtime_result_without_entry(
    hass, monkeypatch
):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    token = _jwt(datetime.now(UTC) + timedelta(days=2))
    session = async_create_f1tv_pairing_session(hass, None, flow_id="flow-id")
    assert session is not None
    hass.config_entries.flow.async_configure = AsyncMock()

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": session.session_id,
            "nonce": session.nonce,
            "subscription_token": token,
        },
    )

    assert status is HTTPStatus.OK
    assert response["ok"] is True
    hass.config_entries.flow.async_configure.assert_awaited_once_with(
        "flow-id", {"session_id": session.session_id}
    )
    result = async_pop_f1tv_pairing_session_result(hass, session.session_id, "flow-id")
    assert result is not None
    auth_header, auth_status = result
    assert auth_header == f"Bearer {token}"
    assert auth_status.configured is True
    assert token not in repr(session)
    assert session.nonce not in repr(session)


async def test_valid_callback_saves_token_and_reloads_entry(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
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
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
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
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
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
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
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
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {},
        body_size=AUTH_CALLBACK_MAX_BODY_BYTES + 1,
    )

    assert status is HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response == {"ok": False, "code": "body_too_large"}


async def test_callback_is_inert_when_gate_closed(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
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


async def test_http_view_adds_security_headers_and_rate_limits(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    view = F1TvAuthCallbackView()

    def _request() -> Mock:
        request = Mock(
            content_length=1,
            query={},
            remote="192.0.2.44",
        )
        request.app = {KEY_HASS: hass}
        request.read = AsyncMock(return_value=b"{")
        return request

    for _ in range(AUTH_CALLBACK_RATE_LIMIT):
        response = await view.post(_request())
        assert response.status == HTTPStatus.BAD_REQUEST
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    response = await view.post(_request())

    assert response.status == HTTPStatus.TOO_MANY_REQUESTS
    assert response.headers["Retry-After"] == "60"
    metrics = hass.data[DOMAIN][AUTH_CALLBACK_METRICS]
    assert metrics["failures_total"] == AUTH_CALLBACK_RATE_LIMIT + 1
    assert metrics["failure_codes"] == {
        "invalid_json": AUTH_CALLBACK_RATE_LIMIT,
        "rate_limited": 1,
    }


async def test_callback_missing_expired_invalid_and_missing_entry_matrix(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    status, response = await async_process_f1tv_pairing_callback(hass, {})
    assert (status, response["code"]) == (HTTPStatus.BAD_REQUEST, "missing_field")

    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {"session_id": "missing", "nonce": "n", "subscription_token": "t"},
    )
    assert (status, response["code"]) == (HTTPStatus.GONE, "expired_pairing")

    flow_session = async_create_f1tv_pairing_session(hass, None, flow_id="flow")
    assert flow_session is not None
    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": flow_session.session_id,
            "nonce": flow_session.nonce,
            "subscription_token": "invalid",
        },
    )
    assert status is HTTPStatus.BAD_REQUEST
    assert response["code"] in {"auth_token_malformed", "invalid_auth_header"}

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    missing_entry = async_create_f1tv_pairing_session(hass, entry)
    assert missing_entry is not None
    missing_entry.entry_id = "not-installed"
    token = _jwt(datetime.now(UTC) + timedelta(days=1))
    status, response = await async_process_f1tv_pairing_callback(
        hass,
        {
            "session_id": missing_entry.session_id,
            "nonce": missing_entry.nonce,
            "subscription_token": token,
        },
    )
    assert (status, response["code"]) == (HTTPStatus.NOT_FOUND, "entry_not_found")


async def test_http_view_body_failures_json_shape_and_registration(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    view = F1TvAuthCallbackView()

    def request(*, length=1, body=b"{}", error=None):
        item = Mock(content_length=length, query={}, remote="198.51.100.2")
        item.app = {KEY_HASS: hass}
        item.read = (
            AsyncMock(side_effect=error) if error else AsyncMock(return_value=body)
        )
        return item

    response = await view.post(request(length=AUTH_CALLBACK_MAX_BODY_BYTES + 1))
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    response = await view.post(request(error=RuntimeError("read")))
    assert response.status == HTTPStatus.BAD_REQUEST
    response = await view.post(
        request(length=None, body=b"x" * (AUTH_CALLBACK_MAX_BODY_BYTES + 1))
    )
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    response = await view.post(request(body=b"[]"))
    assert response.status == HTTPStatus.BAD_REQUEST

    server = SimpleNamespace(register_view=Mock())
    hass.http = server
    async_setup_f1tv_auth_http(hass)
    server.register_view.assert_called_once_with(F1TvAuthCallbackView)
    async_setup_f1tv_auth_http(hass)
    server.register_view.assert_called_once()


async def test_auth_http_exact_corrupt_state_unsafe_url_and_repairs_flow(
    hass, monkeypatch
) -> None:
    hass.data.setdefault(DOMAIN, {})[AUTH_CALLBACK_ATTEMPTS] = "bad"
    assert _callback_rate_limited(hass, "client") is False
    hass.data[DOMAIN][AUTH_CALLBACK_METRICS] = "bad"
    _record_callback_failure(hass, "ignored")

    with (
        patch("homeassistant.helpers.http.current_request") as current_request,
        patch(
            "custom_components.f1_sensor.auth_http.get_url",
            return_value="http://public.example.com",
        ),
    ):
        current_request.get.return_value = None
        assert async_get_f1tv_callback_url(hass).startswith("/api/")

    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    assert (
        async_create_f1tv_pairing_session(
            hass,
            None,
            flow_id="flow",
            callback_url="http://public.example.com/api/f1_sensor/auth/f1tv/callback",
        )
        is None
    )
    assert async_pop_f1tv_pairing_session_result(hass, "missing", "flow") is None

    session = async_create_f1tv_pairing_session(
        hass,
        None,
        flow_id="repair-flow",
        flow_manager="repairs",
    )
    assert session is not None
    manager = SimpleNamespace(async_configure=AsyncMock())
    monkeypatch.setattr(
        "custom_components.f1_sensor.auth_http.repairs_flow_manager",
        lambda _hass: manager,
    )
    await _async_complete_pairing_flow(hass, session, session.session_id)
    manager.async_configure.assert_awaited_once()


async def test_auth_http_view_valid_payload_delegates_and_closed_gate_registration(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    process = AsyncMock(return_value=(HTTPStatus.OK, {"ok": True, "code": "connected"}))
    monkeypatch.setattr(
        "custom_components.f1_sensor.auth_http.async_process_f1tv_pairing_callback",
        process,
    )
    request = Mock(content_length=None, query={}, remote="203.0.113.1")
    request.app = {KEY_HASS: hass}
    request.read = AsyncMock(return_value=b'{"session_id":"s"}')
    response = await F1TvAuthCallbackView().post(request)
    assert response.status == HTTPStatus.OK
    process.assert_awaited_once()

    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
    hass.data.setdefault(DOMAIN, {}).pop("auth_http_view_registered", None)
    async_setup_f1tv_auth_http(hass)
