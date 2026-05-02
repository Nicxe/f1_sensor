"""Repairs support for F1 Sensor."""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .auth import (
    async_update_f1tv_auth_repair_issue,
    evaluate_f1tv_auth_header,
    f1tv_auth_repair_issue_id,
    validate_replacement_auth_header,
)
from .const import (
    CONF_CLEAR_LIVE_TIMING_AUTH_HEADER,
    CONF_LIVE_TIMING_AUTH_HEADER,
)

_AUTH_HEADER_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)


class F1TvTokenRepairFlow(RepairsFlow):
    """Repair flow for expired or invalid F1TV token access."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the repair flow."""
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Handle the first step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, object] | None = None
    ) -> FlowResult:
        """Handle token replacement or removal."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if bool(user_input.get(CONF_CLEAR_LIVE_TIMING_AUTH_HEADER, False)):
                await self._async_save_auth_header("")
                return self.async_create_entry(title="", data={})

            auth_header, error, _status = validate_replacement_auth_header(
                user_input.get(CONF_LIVE_TIMING_AUTH_HEADER)
            )
            if error is None and auth_header is not None:
                await self._async_save_auth_header(auth_header)
                return self.async_create_entry(title="", data={})
            errors[CONF_LIVE_TIMING_AUTH_HEADER] = error or "invalid_auth_header"

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_LIVE_TIMING_AUTH_HEADER): _AUTH_HEADER_SELECTOR,
                    vol.Optional(
                        CONF_CLEAR_LIVE_TIMING_AUTH_HEADER,
                        default=False,
                    ): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={"name": self._entry.title or "F1"},
        )

    async def _async_save_auth_header(self, auth_header: str) -> None:
        data = dict(self._entry.data)
        data[CONF_LIVE_TIMING_AUTH_HEADER] = auth_header
        self.hass.config_entries.async_update_entry(self._entry, data=data)
        async_update_f1tv_auth_repair_issue(
            self.hass,
            self._entry,
            evaluate_f1tv_auth_header(auth_header),
        )
        await self.hass.config_entries.async_reload(self._entry.entry_id)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a repair flow."""
    if data and (entry_id := data.get("entry_id")):
        entry = hass.config_entries.async_get_entry(str(entry_id))
        if entry is not None and issue_id == f1tv_auth_repair_issue_id(entry.entry_id):
            return F1TvTokenRepairFlow(entry)
    return ConfirmRepairFlow()
