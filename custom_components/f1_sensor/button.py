from __future__ import annotations

import asyncio
from inspect import isawaitable
import logging
import time

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from . import const
from .auth import (
    async_set_runtime_f1tv_auth_status,
    async_update_f1tv_auth_repair_issue,
    evaluate_f1tv_auth_header,
    is_auth_feature_enabled,
)
from .calibration import LiveDelayCalibrationManager
from .const import (
    API_URL,
    CONF_LIVE_TIMING_AUTH_HEADER,
    DOMAIN,
)
from .entity import F1AuxEntity, default_object_id, set_suggested_object_id
from .replay_entities import (
    F1ReplayBackButton,
    F1ReplayForwardButton,
    F1ReplayLoadButton,
    F1ReplayPauseButton,
    F1ReplayPlayButton,
    F1ReplayRefreshButton,
    F1ReplayStopButton,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    registry = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not registry:
        return
    name = entry.data.get("sensor_name", "F1")
    entities = []

    manager: LiveDelayCalibrationManager | None = registry.get("calibration_manager")
    if manager is not None:
        entity = F1MatchDelayButton(
            manager,
            f"{entry.entry_id}_delay_calibration_match",
            entry.entry_id,
            name,
        )
        set_suggested_object_id(entity, default_object_id("delay_calibration_match"))
        entities.append(entity)

    # Public experimental auth can be enabled without exposing developer-only
    # Jolpica diagnostics.
    if is_auth_feature_enabled() and entry.data.get(CONF_LIVE_TIMING_AUTH_HEADER):
        entity = F1ClearF1TvAccessButton(
            hass=hass,
            entry=entry,
            device_name=name,
            unique_id=f"{entry.entry_id}_clear_f1tv_access",
        )
        set_suggested_object_id(entity, default_object_id("clear_f1tv_access"))
        entities.append(entity)

    if const.ENABLE_DEVELOPMENT_MODE_UI and registry.get("http_session") is not None:
        entity = F1JolpicaUserAgentTestButton(
            hass=hass,
            entry_id=entry.entry_id,
            device_name=name,
            unique_id=f"{entry.entry_id}_jolpica_user_agent_test",
        )
        set_suggested_object_id(entity, default_object_id("jolpica_ua_test"))
        entities.append(entity)

    # Replay mode buttons
    replay_controller = registry.get("replay_controller")
    if replay_controller is not None:
        replay_buttons = (
            ("replay_load", F1ReplayLoadButton),
            ("replay_play", F1ReplayPlayButton),
            ("replay_pause", F1ReplayPauseButton),
            ("replay_back_30", F1ReplayBackButton),
            ("replay_forward_30", F1ReplayForwardButton),
            ("replay_stop", F1ReplayStopButton),
            ("replay_refresh", F1ReplayRefreshButton),
        )
        for key, entity_cls in replay_buttons:
            entity = entity_cls(
                replay_controller,
                f"{entry.entry_id}_{key}",
                entry.entry_id,
                name,
            )
            set_suggested_object_id(entity, default_object_id(key))
            entities.append(entity)

    if entities:
        async_add_entities(entities)


class F1ClearF1TvAccessButton(F1AuxEntity, ButtonEntity):
    """Diagnostic button that removes the saved F1TV authorization value."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:key-remove"
    _attr_translation_key = "clear_f1tv_access"

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        unique_id: str,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry.entry_id, device_name)
        ButtonEntity.__init__(self)
        self.hass = hass
        self._entry = entry

    async def async_press(self) -> None:
        if not is_auth_feature_enabled():
            return

        data = dict(self._entry.data)
        if not data.get(CONF_LIVE_TIMING_AUTH_HEADER):
            return

        data[CONF_LIVE_TIMING_AUTH_HEADER] = ""
        status = evaluate_f1tv_auth_header("")
        self.hass.config_entries.async_update_entry(self._entry, data=data)
        async_set_runtime_f1tv_auth_status(self.hass, self._entry.entry_id, status)
        async_update_f1tv_auth_repair_issue(self.hass, self._entry, status)
        await self.hass.config_entries.async_reload(self._entry.entry_id)


class F1MatchDelayButton(F1AuxEntity, ButtonEntity):
    """Button that captures the elapsed calibration time and applies it."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "delay_calibration_match"

    def __init__(
        self,
        manager: LiveDelayCalibrationManager,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self._manager = manager
        self._attr_icon = "mdi:check"

    async def async_press(self) -> None:
        try:
            await self._manager.async_complete(source="button")
        except RuntimeError as err:  # noqa: BLE001
            _LOGGER.debug("Calibration button press ignored: %s", err)
            if self.hass:
                snapshot = {}
                try:
                    snapshot = self._manager.snapshot() or {}
                except Exception:  # noqa: BLE001
                    snapshot = {}
                mode = str(snapshot.get("mode") or "idle")
                if mode == "waiting":
                    message = (
                        "Calibration is enabled, but the timer hasn't started yet.\n\n"
                        "This usually means no session has gone live yet. Wait until the "
                        "session is running, then press `Match live delay` when your TV feed "
                        "has caught up."
                    )
                elif mode == "idle":
                    message = (
                        "Calibration is not enabled.\n\n"
                        "Turn on the calibration switch before pressing `Match live delay`, "
                        "otherwise no value will be saved."
                    )
                else:
                    detail = snapshot.get("message")
                    detail_line = f"\n\nDetail: {detail}" if detail else ""
                    message = (
                        "Can't match live delay right now.\n\n"
                        "The calibration timer must be running to save a value."
                        f"{detail_line}"
                    )
                result = persistent_notification.async_create(
                    self.hass,
                    message,
                    title="F1 live delay",
                    notification_id=f"{DOMAIN}_delay_calibration_warning",
                )
                if isawaitable(result):
                    await result


class F1JolpicaUserAgentTestButton(F1AuxEntity, ButtonEntity):
    """Diagnostic button that performs a single Jolpica call and logs the UA used."""

    _device_category = "system"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bug"
    _attr_translation_key = "jolpica_ua_test"

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, unique_id, entry_id, device_name)
        ButtonEntity.__init__(self)
        self.hass = hass
        self._entry_id = entry_id

    async def async_press(self) -> None:
        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        session = reg.get("http_session")
        ua_configured = reg.get("user_agent")
        ua_session = None
        try:
            ua_session = (
                session.headers.get("User-Agent")
                if session is not None and getattr(session, "headers", None) is not None
                else None
            )
        except Exception:
            ua_session = None

        if session is None:
            msg = "No dedicated Jolpica HTTP session found; reload the integration."
            _LOGGER.warning(msg)
            res = persistent_notification.async_create(
                self.hass,
                msg,
                title="F1 Sensor - Jolpica UA test",
                notification_id=f"{DOMAIN}_jolpica_ua_test",
            )
            if isawaitable(res):
                await res
            return

        # Make an actual network request so the remote server sees the UA.
        # Use a small valid query to keep payload tiny.
        status = None
        err = None
        started = time.time()
        headers = {"User-Agent": str(ua_configured)} if ua_configured else None
        try:
            async with asyncio.timeout(10):
                async with session.get(
                    API_URL, params={"limit": "1"}, headers=headers
                ) as resp:
                    status = resp.status
                    # Drain response to keep session healthy; ignore content.
                    await resp.text()
        except Exception as e:  # noqa: BLE001
            err = str(e)

        elapsed_ms = int(round((time.time() - started) * 1000))
        if err is not None:
            log = (
                f"Jolpica UA test FAILED (elapsed={elapsed_ms}ms) "
                f"ua_configured={ua_configured!r} ua_session={ua_session!r} ua_sent={headers.get('User-Agent') if isinstance(headers, dict) else None!r} error={err}"
            )
            _LOGGER.warning(log)
            message = log
        else:
            log = (
                f"Jolpica UA test OK (status={status}, elapsed={elapsed_ms}ms) "
                f"ua_configured={ua_configured!r} ua_session={ua_session!r} ua_sent={headers.get('User-Agent') if isinstance(headers, dict) else None!r} url={API_URL}"
            )
            _LOGGER.info(log)
            message = log

        res = persistent_notification.async_create(
            self.hass,
            message,
            title="F1 Sensor - Jolpica UA test",
            notification_id=f"{DOMAIN}_jolpica_ua_test",
        )
        if isawaitable(res):
            await res
