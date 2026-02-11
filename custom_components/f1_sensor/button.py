from __future__ import annotations

import logging
import time

from homeassistant.components import persistent_notification
from inspect import isawaitable
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import async_timeout

from .const import DOMAIN, API_URL, ENABLE_DEVELOPMENT_MODE_UI
from .entity import F1AuxEntity
from .calibration import LiveDelayCalibrationManager
from .replay_entities import (
    F1ReplayLoadButton,
    F1ReplayPlayButton,
    F1ReplayPauseButton,
    F1ReplayStopButton,
    F1ReplayRefreshButton,
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
        entities.append(
            F1MatchDelayButton(
                manager,
                f"{name} match live delay",
                f"{entry.entry_id}_delay_calibration_match",
                entry.entry_id,
                name,
            )
        )

    # Manual diagnostic button to verify which UA we send to Jolpica/Ergast.
    # Only expose this in development-mode UI to avoid confusing normal users.
    if ENABLE_DEVELOPMENT_MODE_UI and registry.get("http_session") is not None:
        entities.append(
            F1JolpicaUserAgentTestButton(
                hass=hass,
                entry_id=entry.entry_id,
                device_name=name,
                sensor_name=f"{name} Jolpica user-agent test",
                unique_id=f"{entry.entry_id}_jolpica_user_agent_test",
            )
        )

    # Replay mode buttons
    replay_controller = registry.get("replay_controller")
    if replay_controller is not None:
        entities.extend(
            [
                F1ReplayLoadButton(
                    replay_controller,
                    f"{name} Replay Load",
                    f"{entry.entry_id}_replay_load",
                    entry.entry_id,
                    name,
                ),
                F1ReplayPlayButton(
                    replay_controller,
                    f"{name} Replay Play",
                    f"{entry.entry_id}_replay_play",
                    entry.entry_id,
                    name,
                ),
                F1ReplayPauseButton(
                    replay_controller,
                    f"{name} Replay Pause",
                    f"{entry.entry_id}_replay_pause",
                    entry.entry_id,
                    name,
                ),
                F1ReplayStopButton(
                    replay_controller,
                    f"{name} Replay Stop",
                    f"{entry.entry_id}_replay_stop",
                    entry.entry_id,
                    name,
                ),
                F1ReplayRefreshButton(
                    replay_controller,
                    f"{name} Replay Refresh Sessions",
                    f"{entry.entry_id}_replay_refresh",
                    entry.entry_id,
                    name,
                ),
            ]
        )

    if entities:
        async_add_entities(entities)


class F1MatchDelayButton(F1AuxEntity, ButtonEntity):
    """Button that captures the elapsed calibration time and applies it."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        manager: LiveDelayCalibrationManager,
        sensor_name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, sensor_name, unique_id, entry_id, device_name)
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

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bug"

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        sensor_name: str,
        unique_id: str,
        entry_id: str,
        device_name: str,
    ) -> None:
        F1AuxEntity.__init__(self, sensor_name, unique_id, entry_id, device_name)
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
            async with async_timeout.timeout(10):
                async with session.get(
                    API_URL, params={"limit": "1"}, headers=headers
                ) as resp:
                    status = resp.status
                    # Drain response to keep session healthy; ignore content.
                    await resp.text()
        except Exception as e:  # noqa: BLE001
            err = str(e)

        elapsed_ms = int(round((time.time() - started) * 1000))
        if err:
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
