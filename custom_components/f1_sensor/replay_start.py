from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_REPLAY_START_REFERENCE,
    DOMAIN,
    REPLAY_START_REFERENCE_FORMATION,
    REPLAY_START_REFERENCE_SESSION,
)
from .reference_controller import StoredReferenceController


class ReplayStartReferenceController(StoredReferenceController):
    """Persist and broadcast the replay start reference selection."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        storage_version: int = 1,
    ) -> None:
        super().__init__(
            hass,
            entry_id,
            storage_key=f"{DOMAIN}_{entry_id}_replay_start_reference_v{storage_version}",
            default=DEFAULT_REPLAY_START_REFERENCE,
            allowed={
                REPLAY_START_REFERENCE_SESSION,
                REPLAY_START_REFERENCE_FORMATION,
            },
            log_label="Replay start reference",
            storage_version=storage_version,
        )
