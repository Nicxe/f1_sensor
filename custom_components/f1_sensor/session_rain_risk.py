"""Session-bound rain assessments from the existing delayed Race Control feed."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .data_helpers import _map_session_status_payload, _session_status_mapping_context
from .live_window import DEFAULT_PRE_WINDOW

_LOGGER = logging.getLogger(__name__)
_RAIN_MESSAGE = re.compile(
    r"RISK\s+OF\s+RAIN\s+FOR\s+(?:THE\s+)?F1\s+(.+?)\s+IS\s+(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)


def _session_kind(value: Any) -> str | None:
    text = " ".join(str(value or "").upper().split())
    practice = re.fullmatch(r"(?:FREE )?PRACTICE ([123])", text)
    if practice:
        return f"practice_{practice[1]}"
    return {
        "RACE": "race",
        "QUALIFYING": "qualifying",
        "SPRINT": "sprint",
        "SPRINT RACE": "sprint",
        "SPRINT QUALIFYING": "sprint_qualifying",
        "SPRINT SHOOTOUT": "sprint_qualifying",
    }.get(text)


def parse_session_rain_risk(message: Any) -> tuple[str, int | float] | None:
    """Recognize only an explicit F1 session assessment with a valid percentage."""
    if not isinstance(message, str) or not (
        match := _RAIN_MESSAGE.fullmatch(message.strip())
    ):
        return None
    kind = _session_kind(match[1])
    percentage = float(match[2])
    if kind is None or not 0 <= percentage <= 100:
        return None
    return kind, int(percentage) if percentage.is_integer() else percentage


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def empty_session_rain_risk(info: dict | None = None) -> dict[str, Any]:
    """Keep public attribute keys stable, including when no assessment exists."""
    info = info or {}
    meeting = info.get("Meeting")
    meeting = meeting if isinstance(meeting, dict) else {}
    return {
        "percentage": None,
        "session_key": str(info["Key"]) if info.get("Key") is not None else None,
        "meeting_key": str(meeting["Key"]) if meeting.get("Key") is not None else None,
        "session_name": info.get("Name"),
        "utc": None,
        "message": None,
        "source": "race_control",
    }


class SessionRainRiskCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Retain one assessment; share the existing ordered, delayed input bus."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        config_entry: ConfigEntry,
        bus: Any,
        session_info: DataUpdateCoordinator,
        session_status: DataUpdateCoordinator,
        live_state: Any,
        delay_controller: Any,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name="F1 Session Rain Risk", config_entry=config_entry
        )
        self.available = False
        self.data = empty_session_rain_risk()
        self._bus = bus
        self._session_info = session_info
        self._session_status = session_status
        self._live_state = live_state
        self._delay_controller = delay_controller
        self._delay_seconds = delay_controller.current
        self._restore_handle: Callable[[], None] | None = None
        self._info: dict[str, Any] = {}
        self._identity: tuple[str, str, str] | None = None
        self._terminal = False
        self._pending: deque[dict] = deque(maxlen=20)
        self._saved: dict[str, Any] | None = None
        self._legacy_log: dict[str, Any] | None = None
        self._store: Store = Store(
            hass, 1, f"{DOMAIN}_{config_entry.entry_id}_session_rain_risk"
        )
        self._unsubs: list[Callable[[], None]] = []

    async def async_initialize(self) -> None:
        saved = await self._store.async_load()
        self._saved = saved if isinstance(saved, dict) else None
        if self._saved is None:
            legacy = await Store(
                self.hass,
                1,
                f"{DOMAIN}_{self.config_entry.entry_id}_race_control_log_v1",
            ).async_load()
            self._legacy_log = legacy if isinstance(legacy, dict) else None
        self._unsubs = [
            self._session_info.async_add_listener(self._on_session_info),
            self._session_status.async_add_listener(self._on_session_status),
            self._live_state.add_listener(self._on_availability),
            self._bus.add_observation_reset_listener(self._on_observation_reset),
            self._bus.subscribe("RaceControlMessages", self._on_messages),
        ]
        self._on_session_info()

    async def _async_update_data(self) -> dict[str, Any]:
        return self.data

    def _replay(self) -> bool:
        return str(getattr(self._live_state, "reason", "")) in {"replay", "replay-mode"}

    def _publish(self, value: dict[str, Any]) -> None:
        self.available = bool(getattr(self._live_state, "is_live", False))
        if value != self.data:
            self.async_set_updated_data(value)

    def _persist(self, value: dict[str, Any] | None) -> None:
        if self._replay():
            return
        self._saved = value
        self._store.async_delay_save(lambda: deepcopy(self._saved), 1)

    def _on_session_info(self) -> None:
        info = self._session_info.data
        if not isinstance(info, dict):
            return
        meeting = info.get("Meeting")
        meeting = meeting if isinstance(meeting, dict) else {}
        if not (
            info.get("Key") is not None
            and meeting.get("Key") is not None
            and info.get("StartDate")
            and _session_kind(info.get("Name"))
        ):
            return
        identity = (str(meeting["Key"]), str(info["Key"]), str(info["StartDate"]))
        qualifying, part = _session_status_mapping_context(
            self._session_status, use_status_part=True
        )
        info_status = _map_session_status_payload(
            {"Status": info.get("SessionStatus")},
            self.hass,
            is_qualifying_like=qualifying
            or _session_kind(info.get("Name")) in {"qualifying", "sprint_qualifying"},
            qualifying_part=part,
        )
        if identity == self._identity:
            if info_status in {"finished", "finalised", "ended"}:
                self._finish()
            return
        initial = self._identity is None
        self._cancel_restore()
        self._identity, self._info = identity, deepcopy(info)
        self._terminal = False
        self._publish(empty_session_rain_risk(info))
        if initial:
            self._on_session_status()
        if info_status in {"finished", "finalised", "ended"}:
            self._finish()
        if not self._terminal and not self._replay():
            self._restore()
        pending = list(self._pending)
        for message in pending:
            self._apply(message)

    def _on_session_status(self) -> None:
        qualifying, part = _session_status_mapping_context(
            self._session_status, use_status_part=True
        )
        state = _map_session_status_payload(
            self._session_status.data,
            self.hass,
            is_qualifying_like=qualifying,
            qualifying_part=part,
            is_testing_session=bool(
                getattr(self._session_status, "is_testing_session", False)
            ),
        )
        if state in {"finished", "finalised", "ended"}:
            self._finish()
        elif state in {"pre", "live", "suspended", "break"}:
            self._terminal = False

    def _finish(self) -> None:
        self._terminal = True
        self._cancel_restore()
        self._pending.clear()
        self._publish(empty_session_rain_risk(self._info))
        self._persist(None)

    def _on_messages(self, payload: Any) -> None:
        if isinstance(payload, dict) and "Messages" in payload:
            payload = payload["Messages"]
            messages = list(payload.values()) if isinstance(payload, dict) else payload
        else:
            messages = payload if isinstance(payload, list) else [payload]
        if not isinstance(messages, list):
            return
        for message in messages:
            if (
                not isinstance(message, dict)
                or parse_session_rain_risk(
                    message.get("Message") or message.get("message")
                )
                is None
            ):
                continue
            self._pending.append(deepcopy(message))
            if self._identity is not None:
                self._apply(message)

    def _session_start(self) -> datetime | None:
        raw = self._info.get("StartDate")
        start = dt_util.parse_datetime(raw) if isinstance(raw, str) else None
        if start is None:
            return None
        if start.tzinfo is not None:
            return start.astimezone(UTC)
        offset = str(self._info.get("GmtOffset") or "00:00:00")
        match = re.fullmatch(r"(-?)(\d{2}):(\d{2}):(\d{2})", offset)
        if match is None:
            return None
        delta = timedelta(
            hours=int(match[2]), minutes=int(match[3]), seconds=int(match[4])
        )
        return start.replace(tzinfo=UTC) - (-delta if match[1] else delta)

    def _apply(self, message: dict, *, restored: bool = False) -> None:
        if self._terminal or self._identity is None:
            return
        if not self._replay():
            manager = self.hass.data.get(DOMAIN, {}).get("no_spoiler_manager")
            if manager is None or manager.is_active:
                return
        text = message.get("Message") or message.get("message")
        parsed = parse_session_rain_risk(text)
        source_time = _utc(message.get("Utc") or message.get("utc"))
        start = self._session_start()
        if (
            parsed is None
            or parsed[0] != _session_kind(self._info.get("Name"))
            or source_time is None
            or start is None
            or source_time < start - DEFAULT_PRE_WINDOW
        ):
            return
        # Only delivered replay frames are authoritative. Live restores must also
        # be behind the viewer's delayed clock, never the wall-clock future.
        if restored and source_time > dt_util.utcnow() - timedelta(
            seconds=self._delay_controller.current
        ):
            self._cancel_restore()
            remaining = (
                source_time
                + timedelta(seconds=self._delay_controller.current)
                - dt_util.utcnow()
            ).total_seconds()
            identity = self._identity

            @callback
            def deliver_restored(_now: datetime) -> None:
                self._restore_handle = None
                if self._identity == identity and not self._replay() and self.available:
                    self._apply(message, restored=True)

            self._restore_handle = async_call_later(
                self.hass, max(0, remaining), deliver_restored
            )
            return
        previous = _utc(self.data.get("utc"))
        if previous is not None and source_time < previous:
            return
        value = empty_session_rain_risk(self._info)
        value.update(
            percentage=parsed[1],
            utc=source_time.isoformat(timespec="seconds"),
            message=text,
        )
        self._publish(value)
        self._persist({"identity": list(self._identity), "message": value})

    def _restore(self) -> None:
        if self._saved and self._saved.get("identity") == list(self._identity):
            message = self._saved.get("message")
            if isinstance(message, dict):
                self._apply(message, restored=True)
                return
        legacy = self._legacy_log
        if not legacy:
            return
        expected = f"{self._identity[0]}|{self._info['StartDate']}|{self._info['Name']}"
        if legacy.get("session_key") == expected:
            for message in legacy.get("items", []):
                if isinstance(message, dict):
                    self._apply(message, restored=True)
        self._legacy_log = None

    def _on_availability(self, is_live: bool, reason: str | None) -> None:
        if reason == "init":
            return
        if not is_live or reason in {"replay", "replay-mode"}:
            self.reset_for_replay()
        self.available = is_live

    def _cancel_restore(self) -> None:
        if self._restore_handle is not None:
            self._restore_handle()
            self._restore_handle = None

    def _on_observation_reset(self) -> None:
        delay = self._delay_controller.current
        if delay != self._delay_seconds:
            self._delay_seconds = delay
            if not self._replay():
                self._cancel_restore()
                self._pending.clear()
                self._publish(empty_session_rain_risk(self._info))
                if self._identity is not None and not self._terminal:
                    self._restore()
            return
        self.reset_for_replay()

    def reset_for_replay(self) -> None:
        """Retire prior-source values before rewind, seek or delay/source changes."""
        self._identity = None
        self._info = {}
        self._terminal = False
        self._cancel_restore()
        self._pending.clear()
        self._publish(empty_session_rain_risk())

    async def async_close(self) -> None:
        self._cancel_restore()
        while self._unsubs:
            self._unsubs.pop()()
        await self._store.async_save(deepcopy(self._saved))
