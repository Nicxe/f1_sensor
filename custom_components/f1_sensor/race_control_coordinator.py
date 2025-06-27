"""Coordinator for RaceControlMessages with TrackStatus integration."""

from __future__ import annotations
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple, Optional

import asyncio

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .race_control import (
    _get_year_index,
    _get_session_index,
    _is_session_active,
    resolve_racecontrol_url,
)
from .track_status_coordinator import TrackStatusCoordinator
from .signalr_client import F1SignalRClient
from .const import SIGNAL_FLAG_UPDATE, SIGNAL_SC_UPDATE
from .__init__ import F1DataCoordinator

LOGGER = logging.getLogger(__name__)


class RaceControlCoordinator(DataUpdateCoordinator):
    """Coordinator for F1 Race Control messages and TrackStatus."""

    def __init__(
        self, hass: HomeAssistant, race_coordinator: F1DataCoordinator
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name="F1 Race Control Coordinator",
            update_interval=timedelta(seconds=5),
        )
        self._session = async_get_clientsession(hass)
        self._race_coordinator = race_coordinator
        self._yellow_sectors: set[str] = set()
        self._sc_active = False
        self._vsc_active = False
        self._red_flag = False
        self._finished = False
        self._last = {
            "flag_status": None,
            "sc_active": False,
            "vsc_active": False,
            "yellow_sectors": [],
        }
        self._url: str | None = None
        self._last_byte = 0
        self._last_new: datetime | None = None
        self._session_index: Dict[str, Any] | None = None
        self._track: TrackStatusCoordinator | None = None
        self._client: F1SignalRClient | None = None
        self._remove_callbacks: list[callable] = []

    async def async_setup_entry(self) -> None:
        self._client = F1SignalRClient(self.hass, self._session)
        unsub_flag = async_dispatcher_connect(
            self.hass,
            SIGNAL_FLAG_UPDATE,
            lambda data: asyncio.create_task(
                self.async_handle_signalr("TrackStatus", data)
            ),
        )
        self._remove_callbacks.append(unsub_flag)

        unsub_sc = async_dispatcher_connect(
            self.hass,
            SIGNAL_SC_UPDATE,
            lambda data: asyncio.create_task(
                self.async_handle_signalr("RaceControlMessages", data)
            ),
        )
        self._remove_callbacks.append(unsub_sc)

        async def _launch_signalr(_):
            LOGGER.debug("SignalR: calling start()")
            asyncio.create_task(self._client.start())

        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, _launch_signalr
        )

    async def async_close(self, *_: Any) -> None:  # pragma: no cover - placeholder
        for unsub in self._remove_callbacks:
            unsub()
        self._remove_callbacks.clear()
        if self._client:
            await self._client.stop()
        if self._track:
            await self._track.async_close()

    async def _current_session(
        self,
    ) -> (
        Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]] | Tuple[None, None, None]
    ):
        now = datetime.utcnow()
        session = self._session
        year_index = await _get_year_index(session, now.year)
        for meeting in year_index.get("Meetings", []):
            for sess in meeting.get("Sessions", []):
                path = sess.get("Path")
                if not path:
                    continue
                index = await _get_session_index(session, path)
                if await _is_session_active(index):
                    return meeting, sess, index
        return None, None, None

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        flag = str(msg.get("Flag", "")).upper()
        status = str(msg.get("Status", "")).upper()
        text = str(msg.get("Message", "")).upper()
        scope = msg.get("Scope")
        sector = msg.get("Sector")

        if flag in ("YELLOW", "DOUBLE YELLOW"):
            if scope == "Sector" and sector is not None:
                self._yellow_sectors.add(str(sector))
            else:
                self._yellow_sectors.add("track")
        elif flag in ("GREEN", "CLEAR"):
            if scope == "Sector" and sector is not None:
                self._yellow_sectors.discard(str(sector))
            else:
                self._yellow_sectors.clear()
                self._red_flag = False
        if flag == "RED":
            self._red_flag = True

        if "VIRTUAL SAFETY CAR" in text or status.startswith("VSC"):
            if (
                "END" in text
                or "ENDING" in text
                or status.endswith("ENDING")
                or status.endswith("WITHDRAWN")
            ):
                self._vsc_active = False
            elif "DEPLOYED" in text or "DEPLOYED" in status:
                self._vsc_active = True

        if "SAFETY CAR" in text and "VIRTUAL" not in text:
            if (
                "END" in text
                or "IN THIS LAP" in text
                or "ENDING" in text
                or status.endswith("ENDING")
            ):
                self._sc_active = False
            elif "DEPLOYED" in text or status.endswith("DEPLOYED"):
                self._sc_active = True

        if "CHEQUERED" in text or "SESSION FINISHED" in text:
            self._finished = True

    def _reset_state(self) -> None:
        """Clear stored flag and safety car information."""
        self._yellow_sectors.clear()
        self._sc_active = False
        self._vsc_active = False
        self._red_flag = False
        self._last = {
            "flag_status": None,
            "sc_active": False,
            "vsc_active": False,
            "yellow_sectors": [],
        }

    def _derive(self) -> str:
        if self._red_flag:
            return "RED"
        if self._sc_active:
            return "SC"
        if self._vsc_active:
            return "VSC"
        if self._yellow_sectors:
            return "YELLOW"
        return "GREEN"

    async def async_handle_signalr(self, topic: str, payload: Dict[str, Any]) -> None:
        if topic == "TrackStatus":
            code = payload.get("Status")
            if isinstance(code, str) and code.isdigit():
                code = int(code)
            mapping = {
                1: "GREEN",
                2: "YELLOW",
                3: "DOUBLE_YELLOW",
                4: "SC",
                5: "VSC",
                6: "RED",
            }
            status = mapping.get(code)
            if status == "GREEN":
                self._yellow_sectors.clear()
                self._sc_active = False
                self._vsc_active = False
                self._red_flag = False
            elif status in ("YELLOW", "DOUBLE_YELLOW"):
                self._yellow_sectors.add("track")
            elif status == "SC":
                self._sc_active = True
            elif status == "VSC":
                self._vsc_active = True
            elif status == "RED":
                self._red_flag = True
        elif topic == "RaceControlMessages":
            msgs = payload.get("Messages")
            iterable = msgs.values() if isinstance(msgs, dict) else msgs or []
            for msg in iterable:
                self._handle_message(msg)
        elif topic == "SessionStatus":
            status = str(payload.get("Status", "")).upper()
            if status in {"FINISHED", "STOPPED", "CHEQUERED", "CLOSED"}:
                self._finished = True
                if self._client:
                    await self._client.stop()
        self._last = {
            "flag_status": self._derive(),
            "sc_active": self._sc_active or self._vsc_active,
            "vsc_active": self._vsc_active,
            "yellow_sectors": sorted(self._yellow_sectors),
        }
        self.async_set_updated_data(self._last)
        async_dispatcher_send(self.hass, SIGNAL_FLAG_UPDATE, self._last)
        async_dispatcher_send(
            self.hass,
            SIGNAL_SC_UPDATE,
            self._last.get("sc_active", False),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        if self._client and self._client.connected and not self._client.failed:
            return self._last

        if self._finished:
            self._reset_state()
            return self._last

        if not self._url or not self._session_index:
            meeting, sess, index = await self._current_session()
            if not meeting or not sess:
                self._reset_state()
                return self._last
            try:
                self._url, self._session_index = await resolve_racecontrol_url(
                    self._session,
                    int(meeting.get("Year", datetime.utcnow().year)),
                    meeting.get("Name", ""),
                    sess.get("Name", ""),
                )
            except Exception as err:
                LOGGER.warning("Failed resolving race control URL: %s", err)
                self._url = f"https://livetiming.formula1.com/static/{sess.get('Path')}RaceControlMessages.jsonStream"
                self._session_index = index

            ts_path = (
                self._session_index.get("Feeds", {})
                .get("TrackStatus", {})
                .get("StreamPath")
            )
            if ts_path:
                ts_url = f"https://livetiming.formula1.com/{ts_path}"
                self._track = TrackStatusCoordinator(
                    self.hass, ts_url, self._session_index
                )
                await self._track.async_config_entry_first_refresh()

        if self._track and not self._track._finished:
            await self._track.async_refresh()

        try:
            async with async_timeout.timeout(10):
                resp = await self._session.get(
                    self._url, headers={"Range": f"bytes={self._last_byte}-"}
                )
                if resp.status == 404:
                    try:
                        self._url, self._session_index = await resolve_racecontrol_url(
                            self._session,
                            int(meeting.get("Year", datetime.utcnow().year)),
                            meeting.get("Name", ""),
                            sess.get("Name", ""),
                        )
                    except Exception as err:
                        LOGGER.warning("Failed resolving race control URL: %s", err)
                        self._url = f"https://livetiming.formula1.com/static/{sess.get('Path')}RaceControlMessages.jsonStream"
                    self._last_byte = 0
                    resp = await self._session.get(
                        self._url, headers={"Range": f"bytes={self._last_byte}-"}
                    )
                    if resp.status == 404:
                        return self._last
                if resp.status not in (200, 206):
                    raise UpdateFailed(f"Race control fetch failed: {resp.status}")
                data_bytes = await resp.read()
        except Exception as err:  # pragma: no cover - network errors
            raise UpdateFailed(f"Error fetching race control data: {err}") from err

        if not data_bytes:
            now = datetime.now(timezone.utc)
            active = await _is_session_active(self._session_index)
            if (
                not active
                and self._last_new
                and (now - self._last_new).total_seconds() > 60
            ):
                LOGGER.debug("No new race control bytes for 60s, stopping updates")
                self._finished = True
                if self._track:
                    self._track._finished = True
                self._reset_state()
            return self._last

        self._last_new = datetime.now(timezone.utc)
        self._last_byte += len(data_bytes)
        text = data_bytes.decode(errors="ignore")

        for line in text.splitlines():
            if not line:
                continue
            line = line.lstrip("\ufeff")
            json_start = line.find("{")
            if json_start == -1:
                continue
            try:
                data = json.loads(line[json_start:])
            except Exception:
                continue
            msgs = data.get("Messages")
            if isinstance(msgs, dict):
                iterable = msgs.values()
            else:
                iterable = msgs or []
            for msg in iterable:
                self._handle_message(msg)

        track_status = None
        if self._track:
            track_status = (self._track.data or {}).get("track_status")
            if track_status == "GREEN" and self._last.get("flag_status") != "GREEN":
                self._yellow_sectors.clear()
                self._red_flag = False
                self._sc_active = False
                self._vsc_active = False

        flag = track_status or self._derive()

        self._last = {
            "flag_status": flag,
            "sc_active": self._sc_active or self._vsc_active,
            "vsc_active": self._vsc_active,
            "yellow_sectors": sorted(self._yellow_sectors),
        }
        async_dispatcher_send(self.hass, SIGNAL_FLAG_UPDATE, self._last)
        async_dispatcher_send(
            self.hass,
            SIGNAL_SC_UPDATE,
            self._last.get("sc_active", False),
        )
        return self._last
