"""Exercise renewal resources through the integration's shared runtime cleanup."""

from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.f1_sensor import _async_close_runtime_mapping, auth
from custom_components.f1_sensor.const import CONF_LIVE_TIMING_AUTH_HEADER, DOMAIN


def _header(expires: datetime) -> str:
    def part(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    payload = {"exp": int(expires.timestamp()), "SessionId": "synthetic-session"}
    return f"Bearer {part({'alg': 'RS256'})}.{part(payload)}.synthetic-signature"


@pytest.fixture
async def lifecycle(hass, monkeypatch):
    monkeypatch.setattr("custom_components.f1_sensor.const.ENABLE_F1TV_AUTH", True)
    clock = SimpleNamespace(now=datetime.now(UTC))
    monkeypatch.setattr(auth, "_utcnow", lambda: clock.now)
    original = _header(clock.now + timedelta(hours=2))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={"sensor_name": "F1", CONF_LIVE_TIMING_AUTH_HEADER: original},
    )
    entry.add_to_hass(hass)
    runtime = {auth.AUTH_RUNTIME_STATUS: auth.evaluate_f1tv_auth_header(original)}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    hass.config_entries.async_schedule_reload = Mock()
    api = SimpleNamespace(
        status=503,
        started=asyncio.Event(),
        release=asyncio.Event(),
        closed=False,
        requests=0,
    )
    api.release.set()

    @asynccontextmanager
    async def post(*_args, **_kwargs):
        api.requests += 1
        api.started.set()
        try:
            await api.release.wait()
            yield SimpleNamespace(
                status=api.status,
                json=AsyncMock(
                    return_value={
                        "data": {
                            "subscriptionToken": _header(
                                clock.now + timedelta(days=4)
                            ).removeprefix("Bearer ")
                        }
                    }
                ),
            )
        finally:
            api.closed = True

    monkeypatch.setattr(
        auth, "async_get_clientsession", lambda _hass: SimpleNamespace(post=post)
    )
    yield SimpleNamespace(
        hass=hass,
        entry=entry,
        runtime=runtime,
        clock=clock,
        api=api,
        original=original,
    )
    await _async_close_runtime_mapping(runtime)
    await hass.async_block_till_done()


@pytest.mark.parametrize("runtime_removed", [False, True])
async def test_runtime_cleanup_cancels_inflight_renewal(lifecycle, runtime_removed):
    ctx = lifecycle
    ctx.api.status = 200
    ctx.api.release.clear()
    waiter = asyncio.create_task(auth.async_renew_f1tv_token(ctx.hass, ctx.entry))
    await ctx.api.started.wait()

    if runtime_removed:
        ctx.hass.data[DOMAIN].pop(ctx.entry.entry_id)
    await _async_close_runtime_mapping(ctx.runtime)

    assert await waiter is auth.F1TvRenewalResult.CANCELLED
    manager = ctx.runtime[auth.AUTH_RUNTIME_RENEWAL]
    assert manager.closed
    assert manager.task.cancelled()
    assert ctx.api.closed
    assert ctx.entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ctx.original
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.parametrize("runtime_removed", [False, True])
async def test_runtime_cleanup_cancels_retry_and_expiry_timers(
    lifecycle, runtime_removed
):
    ctx = lifecycle
    auth.async_schedule_f1tv_auth_status_refresh(ctx.hass, ctx.entry)
    manager = ctx.runtime[auth.AUTH_RUNTIME_RENEWAL]
    assert await manager.task is auth.F1TvRenewalResult.RETRY_LATER
    assert manager.retry_unsub is not None
    assert ctx.runtime.get(auth.AUTH_RUNTIME_STATUS_REFRESH_UNSUB) is not None

    if runtime_removed:
        ctx.hass.data[DOMAIN].pop(ctx.entry.entry_id)
    await _async_close_runtime_mapping(ctx.runtime)
    ctx.clock.now += timedelta(hours=3)
    async_fire_time_changed(ctx.hass, ctx.clock.now)
    await ctx.hass.async_block_till_done()

    assert manager.closed
    assert manager.retry_unsub is None
    assert ctx.api.requests == 1
    assert (
        ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_EXPIRING_SOON
    )
    ctx.hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.parametrize("replacement", ["cleared", "new_token"])
async def test_session_repair_survives_status_transition_until_access_replaced(
    lifecycle, replacement
):
    ctx = lifecycle
    header = _header(ctx.clock.now + timedelta(hours=25))
    ctx.hass.config_entries.async_update_entry(
        ctx.entry,
        data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: header},
    )
    ctx.runtime[auth.AUTH_RUNTIME_STATUS] = auth.evaluate_f1tv_auth_header(header)
    auth.async_schedule_f1tv_auth_status_refresh(ctx.hass, ctx.entry)
    ctx.api.status = 401

    result = await auth.async_renew_f1tv_token(ctx.hass, ctx.entry)
    issue_id = auth.f1tv_auth_repair_issue_id(ctx.entry.entry_id)
    registry = ir.async_get(ctx.hass)
    assert result is auth.F1TvRenewalResult.PAIRING_REQUIRED
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
    assert ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_VALID

    ctx.clock.now += timedelta(hours=1)
    async_fire_time_changed(ctx.hass, ctx.clock.now)
    await ctx.hass.async_block_till_done()

    assert (
        ctx.runtime[auth.AUTH_RUNTIME_STATUS].status == auth.AUTH_STATUS_EXPIRING_SOON
    )
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
    assert ctx.api.requests == 1

    updated_header = (
        "" if replacement == "cleared" else _header(ctx.clock.now + timedelta(days=4))
    )
    ctx.hass.config_entries.async_update_entry(
        ctx.entry,
        data={**ctx.entry.data, CONF_LIVE_TIMING_AUTH_HEADER: updated_header},
    )
    updated_status = auth.evaluate_f1tv_auth_header(updated_header)
    auth.async_set_runtime_f1tv_auth_status(
        ctx.hass, ctx.entry.entry_id, updated_status
    )
    auth.async_update_f1tv_auth_repair_issue(ctx.hass, ctx.entry, updated_status)

    assert registry.async_get_issue(DOMAIN, issue_id) is None
