from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import repairs
from custom_components.f1_sensor.auth import (
    async_update_f1tv_auth_repair_issue,
    evaluate_f1tv_auth_header,
    f1tv_auth_repair_issue_id,
)
from custom_components.f1_sensor.const import (
    CONF_CLEAR_LIVE_TIMING_AUTH_HEADER,
    CONF_LIVE_TIMING_AUTH_HEADER,
    DOMAIN,
)


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


async def test_repair_flow_replaces_expired_token(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    old_token = _jwt(datetime.now(UTC) - timedelta(hours=1))
    new_token = _jwt(datetime.now(UTC) + timedelta(days=2))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {old_token}"},
    )
    entry.add_to_hass(hass)
    status = evaluate_f1tv_auth_header(entry.data[CONF_LIVE_TIMING_AUTH_HEADER])
    async_update_f1tv_auth_repair_issue(hass, entry, status)
    hass.config_entries.async_reload = AsyncMock(return_value=True)

    flow = await repairs.async_create_fix_flow(
        hass,
        f1tv_auth_repair_issue_id(entry.entry_id),
        {"entry_id": entry.entry_id},
    )
    flow.hass = hass

    result = await flow.async_step_confirm(
        {CONF_LIVE_TIMING_AUTH_HEADER: f"Authorization: Bearer {new_token}"}
    )

    assert result["type"] == "create_entry"
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == f"Bearer {new_token}"
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f1tv_auth_repair_issue_id(entry.entry_id)
        )
        is None
    )


async def test_repair_flow_can_clear_token(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    old_token = _jwt(datetime.now(UTC) - timedelta(hours=1))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {old_token}"},
    )
    entry.add_to_hass(hass)
    async_update_f1tv_auth_repair_issue(
        hass,
        entry,
        evaluate_f1tv_auth_header(entry.data[CONF_LIVE_TIMING_AUTH_HEADER]),
    )
    hass.config_entries.async_reload = AsyncMock(return_value=True)

    flow = await repairs.async_create_fix_flow(
        hass,
        f1tv_auth_repair_issue_id(entry.entry_id),
        {"entry_id": entry.entry_id},
    )
    flow.hass = hass

    result = await flow.async_step_confirm(
        {
            CONF_LIVE_TIMING_AUTH_HEADER: "",
            CONF_CLEAR_LIVE_TIMING_AUTH_HEADER: True,
        }
    )

    assert result["type"] == "create_entry"
    assert entry.data[CONF_LIVE_TIMING_AUTH_HEADER] == ""
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f1tv_auth_repair_issue_id(entry.entry_id)
        )
        is None
    )


async def test_repair_flow_rejects_invalid_replacement(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", True
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={CONF_LIVE_TIMING_AUTH_HEADER: "Bearer old.invalid.token"},
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_reload = AsyncMock(return_value=True)

    flow = await repairs.async_create_fix_flow(
        hass,
        f1tv_auth_repair_issue_id(entry.entry_id),
        {"entry_id": entry.entry_id},
    )
    flow.hass = hass

    result = await flow.async_step_confirm(
        {CONF_LIVE_TIMING_AUTH_HEADER: "Bearer not-a-jwt"}
    )

    assert result["type"] == "form"
    assert result["errors"][CONF_LIVE_TIMING_AUTH_HEADER] == "invalid_auth_header"
    hass.config_entries.async_reload.assert_not_called()


async def test_repair_flow_is_hidden_when_development_ui_disabled(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.f1_sensor.const.ENABLE_DEVELOPMENT_MODE_UI", False
    )
    old_token = _jwt(datetime.now(UTC) - timedelta(hours=1))
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="F1",
        data={CONF_LIVE_TIMING_AUTH_HEADER: f"Bearer {old_token}"},
    )
    entry.add_to_hass(hass)
    async_update_f1tv_auth_repair_issue(
        hass,
        entry,
        evaluate_f1tv_auth_header(entry.data[CONF_LIVE_TIMING_AUTH_HEADER]),
    )

    flow = await repairs.async_create_fix_flow(
        hass,
        f1tv_auth_repair_issue_id(entry.entry_id),
        {"entry_id": entry.entry_id},
    )

    assert flow.__class__.__name__ == "ConfirmRepairFlow"
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f1tv_auth_repair_issue_id(entry.entry_id)
        )
        is None
    )
