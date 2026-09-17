"""F1TV renewal must preserve user choices and recover from temporary failures."""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientError
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import auth
from custom_components.f1_sensor.const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN

NOW = datetime(2026, 9, 12, 12, tzinfo=UTC)


def _jwt(payload: object) -> str:
    def part(value: object) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(payload)}.synthetic-signature"


def _token(expires: datetime, session_id: object) -> str:
    return _jwt({"exp": int(expires.timestamp()), "SessionId": session_id})


class _RenewalApi:
    """A controlled response boundary that never opens a network connection."""

    def __init__(self, token: str) -> None:
        self.status = 200
        self.body: object = {"data": {"subscriptionToken": token}}
        self.error: Exception | None = None
        self.json_error: Exception | None = None
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.requests: list[tuple[str, dict]] = []
        self.closed = False

    @asynccontextmanager
    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        self.started.set()
        try:
            await self.release.wait()
            if self.error is not None:
                raise self.error
            response = SimpleNamespace(
                status=self.status,
                headers={},
                json=AsyncMock(return_value=self.body, side_effect=self.json_error),
            )
            yield response
        finally:
            self.closed = True


@pytest.fixture
async def renewal(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    monkeypatch.setattr(auth, "_utcnow", lambda: NOW)
    session_id = _jwt({"exp": int((NOW + timedelta(days=30)).timestamp())})
    old_header = f"Bearer {_token(NOW + timedelta(hours=2), session_id)}"
    new_token = _token(NOW + timedelta(days=4), session_id)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={"sensor_name": "F1", CONF_LIVE_TIMING_AUTH_HEADER: old_header},
    )
    entry.add_to_hass(hass)
    runtime = {
        auth.AUTH_RUNTIME_STATUS: auth.evaluate_f1tv_auth_header(old_header),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    hass.config_entries.async_schedule_reload = Mock()
    api = _RenewalApi(new_token)
    monkeypatch.setattr(auth, "async_get_clientsession", lambda _hass: api)
    yield SimpleNamespace(
        hass=hass,
        entry=entry,
        runtime=runtime,
        session_id=session_id,
        old_header=old_header,
        new_token=new_token,
        api=api,
    )
    auth.async_cancel_f1tv_auth_status_refresh(hass, entry.entry_id)
    if manager := runtime.get("f1tv_token_renewal"):
        await manager.async_close()
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer invalid",
        "Basic abc.def.ghi",
        "Bearer a.b.c",
        f"Bearer {_jwt([])}",
        f"Bearer {_jwt({})}",
        f"Bearer {_jwt({'SessionId': None})}",
        f"Bearer {_jwt({'SessionId': 123})}",
        f"Bearer {_jwt({'SessionId': '  '})}",
    ],
)
def test_extract_session_rejects_malformed_or_missing_values(header):
    assert auth.extract_f1tv_session_id(header) is None


def test_extract_session_preserves_embedded_token():
    session_id = _jwt({"exp": int((NOW + timedelta(days=30)).timestamp())})
    header = f"Bearer {_token(NOW + timedelta(hours=2), f'  {session_id}  ')}"
    assert auth.extract_f1tv_session_id(header) == session_id


async def test_renewal_saves_new_token_without_redirecting_or_exposing_secrets(
    renewal, caplog
):
    ctx = renewal
    expired = auth.evaluate_f1tv_auth_header(
        f"Bearer {_token(NOW - timedelta(seconds=1), ctx.session_id)}"
    )
    auth.async_update_f1tv_auth_repair_issue(ctx.hass, ctx.entry, expired)

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
    await ctx.hass.async_block_till_done()

    assert result is auth.F1TvRenewalResult.RENEWED
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == f"Bearer {ctx.new_token}"
    assert ctx.entry.data["sensor_name"] == "F1"
    assert len(ctx.api.requests) == 1
    url, request = ctx.api.requests[0]
    assert url == auth.F1_RETRIEVE_SUBSCRIBER_URL
    assert request["headers"]["cd-sessionid"] == ctx.session_id
    assert request["allow_redirects"] is False
    assert request["json"] == {}
    timeout = request["timeout"]
    assert getattr(timeout, "total", timeout) == 15
    assert ctx.api.closed
    ctx.hass.config_entries.async_schedule_reload.assert_called_once_with(
        ctx.entry.entry_id
    )
    status = ctx.runtime[auth.AUTH_RUNTIME_STATUS]
    assert status.status == auth.AUTH_STATUS_VALID
    assert (
        ir.async_get(ctx.hass).async_get_issue(
            DOMAIN, auth.f1tv_auth_repair_issue_id(ctx.entry.entry_id)
        )
        is None
    )
    assert ctx.old_header not in caplog.text
    assert ctx.new_token not in caplog.text
    assert ctx.session_id not in json.dumps(status.as_safe_dict())
    assert ctx.session_id not in caplog.text


@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_session_requires_pairing_without_changing_token(
    renewal, status
):
    ctx = renewal
    ctx.api.status = status

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.PAIRING_REQUIRED
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()
    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.PAIRING_REQUIRED
    )
    auth.async_schedule_f1tv_auth_status_refresh(ctx.hass, ctx.entry)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)
    assert len(ctx.api.requests) == 1
    assert (
        ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_EXPIRING_SOON
    )
    assert (
        ir.async_get(ctx.hass).async_get_issue(
            DOMAIN, auth.f1tv_auth_repair_issue_id(ctx.entry.entry_id)
        )
        is not None
    )


@pytest.mark.parametrize("status", [301, 400, 404, 429, 500, 503])
async def test_temporary_http_failure_retains_saved_access(renewal, status):
    ctx = renewal
    ctx.api.status = status

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.RETRY_LATER
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.parametrize("error", [TimeoutError(), ClientError("sensitive-session")])
async def test_network_failure_is_retryable_and_redacted(renewal, caplog, error):
    ctx = renewal
    ctx.api.error = error

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.RETRY_LATER
    assert "sensitive-session" not in caplog.text
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    assert ctx.api.closed


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"data": None},
        {"data": []},
        {"data": "invalid"},
        {"data": {}},
        {"data": {"subscriptionToken": 123}},
        {"data": {"subscriptionToken": ""}},
        {"data": {"subscriptionToken": "not-a-jwt"}},
    ],
)
async def test_malformed_response_is_retryable_without_overwriting_access(
    renewal, body
):
    ctx = renewal
    ctx.api.body = body

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.RETRY_LATER
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


async def test_invalid_json_is_retryable(renewal):
    ctx = renewal
    ctx.api.json_error = ValueError("invalid JSON")
    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.RETRY_LATER
    )


@pytest.mark.parametrize("hours", [-1, 0, 0.1, 2, 23, 24])
async def test_short_or_unchanged_replacement_cannot_start_reload_loop(renewal, hours):
    ctx = renewal
    ctx.api.body = {
        "data": {
            "subscriptionToken": _token(NOW + timedelta(hours=hours), ctx.session_id)
        }
    }

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.RETRY_LATER
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


async def test_long_lived_but_older_replacement_is_not_saved(renewal):
    ctx = renewal
    newer = f"Bearer {_token(NOW + timedelta(days=5), ctx.session_id)}"
    ctx.hass.config_entries.async_update_entry(
        ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: newer}
    )

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.RETRY_LATER
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == newer
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.parametrize("session_id", [None, "", _jwt({"exp": int(NOW.timestamp())})])
async def test_missing_or_expired_session_requires_pairing_without_request(
    renewal, session_id
):
    ctx = renewal
    header = f"Bearer {_token(NOW + timedelta(hours=2), session_id)}"
    ctx.hass.config_entries.async_update_entry(
        ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: header}
    )

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)

    assert result is auth.F1TvRenewalResult.PAIRING_REQUIRED
    assert not ctx.api.requests
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == header


@pytest.mark.parametrize("change", ["clear", "replace", "unload", "remove"])
async def test_response_cannot_overwrite_new_user_choice_or_retired_runtime(
    renewal, change
):
    ctx = renewal
    ctx.api.release.clear()
    task = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await asyncio.wait_for(ctx.api.started.wait(), 1)
    expected = ctx.old_header
    if change in ("clear", "replace"):
        expected = "" if change == "clear" else "Bearer newly-paired-token"
        ctx.hass.config_entries.async_update_entry(
            ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: expected}
        )
    elif change == "unload":
        ctx.hass.data[DOMAIN][ctx.entry.entry_id] = {}
    else:
        await ctx.hass.config_entries.async_remove(ctx.entry.entry_id)
    ctx.api.release.set()

    assert await task is auth.F1TvRenewalResult.CANCELLED
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == expected
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


async def test_overlapping_renewals_share_one_request_and_reload(renewal):
    ctx = renewal
    ctx.api.release.clear()
    first = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await asyncio.wait_for(ctx.api.started.wait(), 1)
    second = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await asyncio.sleep(0)
    ctx.api.release.set()

    results = await asyncio.gather(first, second)
    await ctx.hass.async_block_till_done()

    assert results == [auth.F1TvRenewalResult.RENEWED] * 2
    assert len(ctx.api.requests) == 1
    ctx.hass.config_entries.async_schedule_reload.assert_called_once_with(
        ctx.entry.entry_id
    )


async def test_unload_cancels_pending_request_without_restoring_access(renewal):
    ctx = renewal
    ctx.api.release.clear()
    task = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await asyncio.wait_for(ctx.api.started.wait(), 1)

    await ctx.runtime["f1tv_token_renewal"].async_close()

    assert await asyncio.wait_for(task, 1) is auth.F1TvRenewalResult.CANCELLED
    assert ctx.api.closed
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.parametrize(
    "state", ["gate_closed", "missing_root", "missing_runtime", "invalid_runtime"]
)
async def test_renewal_is_inert_without_active_runtime(renewal, monkeypatch, state):
    ctx = renewal
    if state == "gate_closed":
        monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
    elif state == "missing_root":
        ctx.hass.data.pop(DOMAIN)
    elif state == "missing_runtime":
        ctx.hass.data[DOMAIN].pop(ctx.entry.entry_id)
    else:
        ctx.hass.data[DOMAIN][ctx.entry.entry_id] = "invalid"

    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.CANCELLED
    )
    assert not ctx.api.requests


@pytest.fixture
def renewal_timers(renewal, monkeypatch):
    clock = SimpleNamespace(now=NOW, timers=[])
    monkeypatch.setattr(auth, "_utcnow", lambda: clock.now)

    def call_later(_hass, delay, callback):
        timer = SimpleNamespace(delay=delay, callback=callback, cancelled=False)
        clock.timers.append(timer)

        def cancel():
            timer.cancelled = True

        return cancel

    monkeypatch.setattr(auth, "async_call_later", call_later)
    return clock


async def test_failed_automatic_renewal_keeps_expiry_monitor_and_creates_repair(
    renewal, renewal_timers
):
    ctx = renewal
    clock = renewal_timers
    ctx.api.status = 503

    auth.async_schedule_f1tv_auth_status_refresh(ctx.hass, ctx.entry)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)

    assert len(ctx.api.requests) == 1
    expiry = next(
        timer for timer in clock.timers if timer.delay == 7200 and not timer.cancelled
    )
    assert (
        ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_EXPIRING_SOON
    )
    clock.now += timedelta(hours=2)
    expiry.cancelled = True
    expiry.callback(clock.now)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)

    assert ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_EXPIRED
    assert (
        ir.async_get(ctx.hass).async_get_issue(
            DOMAIN, auth.f1tv_auth_repair_issue_id(ctx.entry.entry_id)
        )
        is not None
    )
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.old_header
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


async def test_entering_expiring_window_automatically_renews(renewal, renewal_timers):
    ctx = renewal
    clock = renewal_timers
    header = f"Bearer {_token(NOW + timedelta(hours=25), ctx.session_id)}"
    ctx.hass.config_entries.async_update_entry(
        ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: header}
    )
    ctx.runtime[auth.AUTH_RUNTIME_STATUS] = auth.evaluate_f1tv_auth_header(header)
    auth.async_schedule_f1tv_auth_status_refresh(ctx.hass, ctx.entry)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)
    assert not ctx.api.requests

    transition = next(timer for timer in clock.timers if not timer.cancelled)
    assert transition.delay == 3600
    clock.now += timedelta(hours=1)
    transition.cancelled = True
    transition.callback(clock.now)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)

    assert len(ctx.api.requests) == 1
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == f"Bearer {ctx.new_token}"
    assert ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_VALID
    ctx.hass.config_entries.async_schedule_reload.assert_called_once_with(
        ctx.entry.entry_id
    )


async def test_retries_back_off_until_recovery(renewal, renewal_timers):
    ctx = renewal
    clock = renewal_timers
    ctx.api.status = 503
    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.RETRY_LATER
    )
    delays = []
    for _attempt in range(9):
        pending = [timer for timer in clock.timers if not timer.cancelled]
        assert len(pending) == 1
        retry = pending[0]
        delays.append(retry.delay)
        # Repeated manual presses during the backoff must not call F1 again.
        count = len(ctx.api.requests)
        assert (
            await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
            is auth.F1TvRenewalResult.RETRY_LATER
        )
        assert len(ctx.api.requests) == count
        clock.now += timedelta(seconds=retry.delay)
        retry.cancelled = True
        retry.callback(clock.now)
        await ctx.hass.async_block_till_done(wait_background_tasks=True)

    assert delays[0] == auth.AUTH_RENEWAL_RETRY_SECONDS
    assert delays == sorted(delays)
    assert delays[-2:] == [auth.AUTH_RENEWAL_MAX_RETRY_SECONDS] * 2
    ctx.api.status = 200
    retry = next(timer for timer in clock.timers if not timer.cancelled)
    retry.cancelled = True
    retry.callback(clock.now)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == f"Bearer {ctx.new_token}"
    assert not [timer for timer in clock.timers if not timer.cancelled]
    ctx.hass.config_entries.async_schedule_reload.assert_called_once_with(
        ctx.entry.entry_id
    )


async def test_unload_removes_pending_retry_and_prevents_more_requests(
    renewal, renewal_timers
):
    ctx = renewal
    ctx.api.status = 503
    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.RETRY_LATER
    )
    assert any(not timer.cancelled for timer in renewal_timers.timers)

    await ctx.runtime[auth.AUTH_RUNTIME_RENEWAL].async_close()

    assert all(timer.cancelled for timer in renewal_timers.timers)
    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.CANCELLED
    )
    assert len(ctx.api.requests) == 1


async def test_failed_request_does_not_retry_after_access_was_cleared(
    renewal, renewal_timers
):
    ctx = renewal
    ctx.api.release.clear()
    ctx.api.error = ClientError("temporary error")
    task = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await asyncio.wait_for(ctx.api.started.wait(), 1)
    ctx.hass.config_entries.async_update_entry(
        ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: ""}
    )
    ctx.api.release.set()

    assert await task is auth.F1TvRenewalResult.CANCELLED
    assert not renewal_timers.timers
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ""


async def test_cancelled_waiter_does_not_cancel_shared_renewal(renewal):
    ctx = renewal
    ctx.api.release.clear()
    first = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await asyncio.wait_for(ctx.api.started.wait(), 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not ctx.api.closed
    second = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    ctx.api.release.set()

    assert await second is auth.F1TvRenewalResult.RENEWED
    assert len(ctx.api.requests) == 1
    ctx.hass.config_entries.async_schedule_reload.assert_called_once_with(
        ctx.entry.entry_id
    )


@pytest.mark.parametrize(
    "session_id", ["opaque-session", "a.invalid.c", _jwt({}), _jwt({"exp": "unknown"})]
)
async def test_session_without_known_expiry_is_validated_by_f1(renewal, session_id):
    ctx = renewal
    header = f"Bearer {_token(NOW + timedelta(hours=2), session_id)}"
    ctx.hass.config_entries.async_update_entry(
        ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: header}
    )

    assert (
        await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
        is auth.F1TvRenewalResult.RENEWED
    )
    assert ctx.api.requests[0][1]["headers"]["cd-sessionid"] == session_id


@pytest.mark.parametrize("change", ["clear", "disable", "gate_closed"])
async def test_scheduled_renewal_checks_entry_again_before_sending_session(
    renewal, renewal_timers, monkeypatch, change
):
    ctx = renewal
    auth.async_schedule_f1tv_auth_status_refresh(ctx.hass, ctx.entry)
    if change == "clear":
        ctx.hass.config_entries.async_update_entry(
            ctx.entry, data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: ""}
        )
    elif change == "disable":
        monkeypatch.setattr(
            ctx.hass.config_entries, "async_reload", AsyncMock(return_value=True)
        )
        await ctx.hass.config_entries.async_set_disabled_by(
            ctx.entry.entry_id, ConfigEntryDisabler.USER
        )
    else:
        monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", False)
    await ctx.hass.async_block_till_done(wait_background_tasks=True)

    assert not ctx.api.requests
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()
