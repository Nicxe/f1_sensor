import asyncio
from contextlib import suppress
from functools import cache
import json
from pathlib import Path

from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ENTITY_NAME_LANGUAGE,
    CONF_ENTITY_NAME_MODE,
    CONF_OPERATION_MODE,
    DEFAULT_ENTITY_NAME_LANGUAGE,
    DEFAULT_OPERATION_MODE,
    DOMAIN,
    ENTITY_NAME_MODE_LEGACY,
    ENTITY_NAME_MODE_LOCALIZED,
    OPERATION_MODE_DEVELOPMENT,
)

_TRANSLATIONS_DIR = Path(__file__).parent / "translations"
_ENTRY_NAME_SETTINGS: dict[str, tuple[str, str]] = {}


def _normalize_language(language: str | None) -> str:
    """Normalize a stored language code for translation lookup."""
    if not language:
        return DEFAULT_ENTITY_NAME_LANGUAGE
    normalized = str(language).strip().replace("_", "-").lower()
    return normalized or DEFAULT_ENTITY_NAME_LANGUAGE


def _translation_language_candidates(language: str | None) -> tuple[str, ...]:
    """Return translation file candidates in priority order."""
    normalized = _normalize_language(language)
    candidates: list[str] = []
    for candidate in (
        normalized,
        normalized.split("-", 1)[0],
        DEFAULT_ENTITY_NAME_LANGUAGE,
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


@cache
def _load_translation_names(language: str) -> dict[str, str]:
    """Load entity display names from a bundled translation file."""
    try:
        path = _TRANSLATIONS_DIR / f"{_normalize_language(language)}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        result: dict[str, str] = {}
        for entities in data.get("entity", {}).values():
            for key, attrs in entities.items():
                if isinstance(attrs, dict) and (n := attrs.get("name")):
                    result[key] = n
        return result
    except Exception:
        return {}


def register_entry_name_settings(entry_id: str, data: dict) -> None:
    """Register naming settings for a config entry."""
    mode = data.get(CONF_ENTITY_NAME_MODE, ENTITY_NAME_MODE_LEGACY)
    if mode not in (ENTITY_NAME_MODE_LEGACY, ENTITY_NAME_MODE_LOCALIZED):
        mode = ENTITY_NAME_MODE_LEGACY
    language = _normalize_language(data.get(CONF_ENTITY_NAME_LANGUAGE))
    _ENTRY_NAME_SETTINGS[entry_id] = (mode, language)


def unregister_entry_name_settings(entry_id: str) -> None:
    """Remove naming settings for a config entry."""
    _ENTRY_NAME_SETTINGS.pop(entry_id, None)


def clear_entry_name_settings() -> None:
    """Clear cached entry naming settings for tests."""
    _ENTRY_NAME_SETTINGS.clear()


def _entry_name_settings(entry_id: str | None) -> tuple[str, str]:
    """Return the naming mode and language for an entry."""
    if not entry_id:
        return ENTITY_NAME_MODE_LEGACY, DEFAULT_ENTITY_NAME_LANGUAGE
    return _ENTRY_NAME_SETTINGS.get(
        entry_id,
        (ENTITY_NAME_MODE_LEGACY, DEFAULT_ENTITY_NAME_LANGUAGE),
    )


def _translated_entity_name(translation_key: str, language: str) -> str | None:
    """Return the first matching translated entity name for a language."""
    for candidate in _translation_language_candidates(language):
        if name := _load_translation_names(candidate).get(translation_key):
            return name
    return None


def _default_object_id_from_translation_key(translation_key: str | None) -> str | None:
    """Return the stable default object_id for a translation key."""
    if not translation_key:
        return None
    normalized = str(translation_key).strip().replace("-", "_").lower()
    return f"f1_{normalized}" if normalized else None


def default_object_id(key: str | None) -> str | None:
    """Build a stable default object_id for a standard entity key."""
    return _default_object_id_from_translation_key(key)


def set_suggested_object_id(entity: Entity, object_id: str | None) -> None:
    """Set a stable suggested object ID when one is provided."""
    if object_id:
        entity._attr_suggested_object_id = object_id


def _entity_name_from_key(
    translation_key: str | None, *, entry_id: str | None = None
) -> str | None:
    """Return a display name for a translation key without any device prefix."""
    if not translation_key:
        return None
    mode, language = _entry_name_settings(entry_id)
    if mode == ENTITY_NAME_MODE_LOCALIZED:
        if name := _translated_entity_name(translation_key, language):
            return name
    elif name := _translated_entity_name(translation_key, DEFAULT_ENTITY_NAME_LANGUAGE):
        return name
    parts = translation_key.replace("_", " ").split()
    if not parts:
        return None
    return " ".join([parts[0].capitalize()] + parts[1:])


DEVICE_CATEGORIES: dict[str, str] = {
    "race": "Race",
    "championship": "Championship",
    "session": "Session",
    "drivers": "Drivers",
    "officials": "Officials",
    "system": "System",
}


def _safe_write_ha_state(entity: Entity) -> None:
    """Thread-safe request to write entity state."""
    hass = getattr(entity, "hass", None)
    if hass is None:
        return

    try:
        loop = hass.loop
    except Exception:
        return

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    # `async_schedule_update_ha_state` is a @callback (not a coroutine) and will
    # perform the write on the loop safely.
    if running is loop:
        with suppress(Exception):
            entity.async_schedule_update_ha_state(False)
        return

    with suppress(Exception):
        loop.call_soon_threadsafe(entity.async_schedule_update_ha_state, False)


class F1BaseEntity(CoordinatorEntity):
    """Common base entity for F1 sensors."""

    _device_category: str = "system"

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name
        self._stream_last_active: bool | None = None

    @property
    def name(self) -> str | None:
        """Return entity name from translations, without device prefix."""
        return _entity_name_from_key(
            getattr(self, "_attr_translation_key", None),
            entry_id=self._entry_id,
        )

    @property
    def suggested_object_id(self) -> str | None:
        """Preserve stable object IDs when name is overridden for display."""
        if hasattr(self, "_attr_suggested_object_id"):
            return self._attr_suggested_object_id
        if object_id := _default_object_id_from_translation_key(
            getattr(self, "_attr_translation_key", None)
        ):
            return object_id
        return super().suggested_object_id

    @property
    def device_info(self):
        label = DEVICE_CATEGORIES.get(self._device_category, "System")
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_{self._device_category}")},
            "name": f"{self._device_name} - {label}",
            "manufacturer": "Nicxe",
            "model": f"F1 Sensor - {label}",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def available(self) -> bool:
        """Expose coordinator availability as entity availability.

        Many live-feed coordinators toggle `coordinator.available` via
        LiveAvailabilityTracker. When not available, entities should be
        `unavailable` instead of keeping stale values for days/weeks.
        """
        with suppress(Exception):
            coord = getattr(self, "coordinator", None)
            if coord is not None and hasattr(coord, "available"):
                coord_available = bool(coord.available)

                # Additional guard: for live timing coordinators, only consider them
                # available when the integration's live_state says we are in a live
                # window (or when running in replay mode).
                #
                # This prevents sensors from staying available with restored/stale
                # values when the supervisor is idle or the upstream is quiet.
                with suppress(Exception):
                    reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
                        self._entry_id, {}
                    ) or {}
                    operation_mode = reg.get(
                        CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                    )
                    live_state = reg.get("live_state")
                    is_live_window = (
                        bool(getattr(live_state, "is_live", False))
                        if live_state is not None
                        else None
                    )
                    if (
                        operation_mode != OPERATION_MODE_DEVELOPMENT
                        and is_live_window is False
                    ):
                        return False

                    # Check if replay mode is active - skip activity check during replay
                    # since activity timestamps are cleared during transport swap
                    replay_controller = reg.get("replay_controller")
                    replay_active = False
                    if replay_controller is not None:
                        with suppress(Exception):
                            from .replay_mode import ReplayState

                            replay_active = replay_controller.state in (
                                ReplayState.PLAYING,
                                ReplayState.PAUSED,
                            )

                    # If we're in a live window, require actual stream activity.
                    # If we have seen no activity at all, treat as offline.
                    # Skip this check during replay mode since activity timestamps
                    # are reset when swapping transports.
                    if (
                        operation_mode != OPERATION_MODE_DEVELOPMENT
                        and is_live_window is True
                        and not replay_active
                    ):
                        bus = reg.get("live_bus")
                        activity_age = None
                        with suppress(Exception):
                            if bus is not None:
                                activity_age = bus.last_stream_activity_age()
                        if activity_age is None:
                            return False
                        # Treat prolonged inactivity as offline/unavailable.
                        # Heartbeat frames should keep this low during real sessions.
                        if activity_age > 90.0:
                            return False

                return coord_available
        return super().available

    def _safe_write_ha_state(self, *_args) -> None:
        """Thread-safe request to write entity state.

        Some upstream libraries (e.g. SignalR clients) invoke callbacks from worker
        threads. Calling `async_write_ha_state` directly from those threads is not
        safe. This helper always schedules the write on Home Assistant's event loop.
        """
        _safe_write_ha_state(self)

    def _is_stream_active(self) -> bool:
        reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
            self._entry_id, {}
        ) or {}
        live_state = reg.get("live_state")
        if live_state is not None and bool(getattr(live_state, "is_live", False)):
            return True
        replay_controller = reg.get("replay_controller")
        if replay_controller is not None:
            try:
                from .replay_mode import ReplayState

                return replay_controller.state in (
                    ReplayState.PLAYING,
                    ReplayState.PAUSED,
                )
            except Exception:
                return False
        return False

    def _clear_state_if_possible(self) -> None:
        clear = getattr(self, "_clear_state", None)
        if callable(clear):
            with suppress(Exception):
                clear()

    def _handle_stream_state(self, updated: bool) -> bool:
        """Handle live/replay stream inactivity and transitions.

        Returns True when state should be written (updated or cleared).
        """
        stream_active = self._is_stream_active()
        if not updated:
            if not stream_active:
                self._clear_state_if_possible()
                self._stream_last_active = stream_active
                return True
            return False

        if self._stream_last_active is None:
            self._stream_last_active = stream_active
        elif self._stream_last_active is True and stream_active is False:
            self._clear_state_if_possible()
            self._stream_last_active = stream_active
            return True

        self._stream_last_active = stream_active
        if not stream_active:
            self._clear_state_if_possible()
            return True
        return True


class F1AuxEntity(Entity):
    """Helper base for entities that do not use a coordinator but share device info."""

    _device_category: str = "system"

    def __init__(self, unique_id: str, entry_id: str, device_name: str):
        super().__init__()
        self._attr_unique_id = unique_id
        self._entry_id = entry_id
        self._device_name = device_name
        self._stream_last_active: bool | None = None

    def _safe_write_ha_state(self, *_args) -> None:
        """Thread-safe request to write entity state (see F1BaseEntity)."""
        _safe_write_ha_state(self)

    def _is_stream_active(self) -> bool:
        reg = (self.hass.data.get(DOMAIN, {}) if self.hass else {}).get(
            self._entry_id, {}
        ) or {}
        live_state = reg.get("live_state")
        if live_state is not None and bool(getattr(live_state, "is_live", False)):
            return True
        replay_controller = reg.get("replay_controller")
        if replay_controller is not None:
            try:
                from .replay_mode import ReplayState

                return replay_controller.state in (
                    ReplayState.PLAYING,
                    ReplayState.PAUSED,
                )
            except Exception:
                return False
        return False

    @property
    def name(self) -> str | None:
        """Return entity name from translations, without device prefix."""
        return _entity_name_from_key(
            getattr(self, "_attr_translation_key", None),
            entry_id=self._entry_id,
        )

    @property
    def suggested_object_id(self) -> str | None:
        """Preserve stable object IDs when name is overridden for display."""
        if hasattr(self, "_attr_suggested_object_id"):
            return self._attr_suggested_object_id
        if object_id := _default_object_id_from_translation_key(
            getattr(self, "_attr_translation_key", None)
        ):
            return object_id
        return super().suggested_object_id

    @property
    def device_info(self):
        label = DEVICE_CATEGORIES.get(self._device_category, "System")
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_{self._device_category}")},
            "name": f"{self._device_name} - {label}",
            "manufacturer": "Nicxe",
            "model": f"F1 Sensor - {label}",
            "entry_type": DeviceEntryType.SERVICE,
        }
