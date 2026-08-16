"""Entry-owned storage lifecycle helpers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

ENTRY_STORAGE_VERSION = 1


def entry_storage_keys(entry_id: str) -> tuple[str, ...]:
    """Return every storage key owned exclusively by one config entry."""
    return (
        f"{DOMAIN}_{entry_id}_http_cache_v1",
        f"{DOMAIN}_{entry_id}_live_delay_v1",
        f"{DOMAIN}_{entry_id}_live_delay_reference_v1",
        f"{DOMAIN}_{entry_id}_replay_start_reference_v1",
        f"{DOMAIN}_{entry_id}_race_control_log_v1",
    )


async def async_remove_entry_storage(hass: HomeAssistant, entry_id: str) -> None:
    """Remove storage owned by a deleted config entry."""
    for key in entry_storage_keys(entry_id):
        await Store(hass, ENTRY_STORAGE_VERSION, key).async_remove()
