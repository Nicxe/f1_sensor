import asyncio
import contextlib
import json
import logging
import random
import urllib.parse
from typing import List

from aiohttp import (
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
    ClientError,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .const import (
    SIGNAL_FLAG_UPDATE,
    SIGNAL_SC_UPDATE,
    SUBSCRIBE_FEEDS,
    NEGOTIATE_URL,
)

_LOGGER = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "BestHTTP",
    "Accept-Encoding": "gzip, identity",
    "Accept": "application/json",
}

# SignalR record separator
RS = "\x1e"


def _frame(obj: str | dict) -> str:
    """Return websocket-ready frame string with RS suffix."""
    if isinstance(obj, dict):
        obj = json.dumps(obj, separators=(",", ":"))
    return f"{obj}{RS}"


class F1SignalRClient:
    """Minimal SignalR client using aiohttp/websocket."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        feeds: List[str] = SUBSCRIBE_FEEDS,
    ) -> None:
        self.hass = hass
        self.session = session
        self.feeds = feeds
        self._ws: ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._buf: str = ""
        self.connected = False
        self.failed = False
        self._stop_unsub = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._handle_ha_stop
        )

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            async_dispatcher_send(self.hass, "f1_signalr_state")

    async def _handle_ha_stop(self, _event):
        await self.stop()

    async def start(self) -> None:
        """Start background task to maintain the websocket."""
        if not self._task:
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop background task and close websocket."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._set_connected(False)

    # --------------------------------------------------------------------- #
    # Low-level connection helpers
    # --------------------------------------------------------------------- #

    async def _connect_once(self) -> ClientWebSocketResponse:
        """Do negotiate + WebSocket connect, return open WS object."""
        params = {
            "clientProtocol": "1.5",
            "connectionData": '[{"name":"Streaming"}]',
            "tid": random.randint(0, 9),
        }
        _LOGGER.debug("Negotiate params: %s", params)
        async with self.session.get(
            NEGOTIATE_URL, params=params, headers=HEADERS
        ) as resp:
            resp.raise_for_status()
            nego = await resp.json()
            _LOGGER.debug("Negotiate OK: %s", nego)
            t0_cookie = resp.cookies.get("t0")
            cookie_val = t0_cookie.value if t0_cookie else ""

        params.update(
            {
                "transport": "webSockets",
                "connectionToken": nego.get("ConnectionToken"),
            }
        )
        ws_url = (
            "wss://livetiming.formula1.com"
            + nego.get("Url", "")
            + "/connect?"
            + urllib.parse.urlencode(params)
        )
        _LOGGER.debug("WebSocket URL: %s", ws_url)

        headers = HEADERS | {"Cookie": f"t0={cookie_val}"}
        return await self.session.ws_connect(
            ws_url,
            headers=headers,
            autoping=False,  # F1 använder egen ping
            heartbeat=30,
            ssl=False,
        )

    async def _handshake_and_subscribe(self) -> None:
        """Run the initial server handshake and send Subscribe."""
        init_msg = await self._ws.receive()
        if init_msg.type is not WSMsgType.TEXT:
            raise RuntimeError(f"Unexpected init frame type: {init_msg}")

        raw = init_msg.data.rstrip(RS)
        try:
            init_obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Init JSON invalid: {raw}") from exc

        if init_obj.get("S") != 1:
            _LOGGER.warning("Init frame utan S=1: %s", init_obj)
        _LOGGER.debug("Init OK: C=%s", init_obj.get("C"))

        payload = {
            "H": "Streaming",
            "M": "Subscribe",
            "A": [self.feeds],
            "I": 1,
        }
        await self._ws.send_str(_frame(payload))
        _LOGGER.debug("Subscribe sent")

    # --------------------------------------------------------------------- #
    # Main listen loop
    # --------------------------------------------------------------------- #

    async def _listen(self) -> None:
        retry_delay = 1
        while True:
            hb_task: asyncio.Task | None = None
            try:
                self._ws = await self._connect_once()
                self.failed = False
                self._set_connected(True)
                await self._handshake_and_subscribe()

                hb_task = asyncio.create_task(self._heartbeat(self._ws))

                async for msg in self._ws:
                    if msg.type == WSMsgType.TEXT:
                        await self._process_text(msg.data)
                    elif msg.type in (
                        WSMsgType.CLOSE,
                        WSMsgType.CLOSED,
                        WSMsgType.ERROR,
                    ):
                        break

            except asyncio.CancelledError:
                raise
            except ClientError:
                self.failed = True
                _LOGGER.exception("SignalR client error")
            except Exception:  # pylint: disable=broad-except
                self.failed = True
                _LOGGER.exception("Unhandled SignalR client exception")
            finally:
                self._set_connected(False)
                if hb_task:
                    hb_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await hb_task
                if self._ws:
                    await self._ws.close()
                    self._ws = None
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 300)

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #

    async def _process_text(self, text: str) -> None:
        """Buffer until RS, then parse each frame."""
        self._buf += text
        if RS not in self._buf:
            return
        frames = self._buf.split(RS)
        self._buf = frames.pop()  # leftover
        for frame in frames:
            if not frame:
                continue
            try:
                data = json.loads(frame)
            except json.JSONDecodeError:
                _LOGGER.debug("Skip non-JSON frame: %s", frame[:50])
                continue
            await self._handle_frame(data)

    async def _handle_frame(self, data: dict) -> None:
        # Server cursors / keepalives
        if data.get("C") or data.get("S"):
            return

        for item in data.get("M", []):
            args = item.get("A", [])
            if len(args) < 2:
                continue
            topic, payload = args[0], args[1]
            if topic == "TrackStatus":
                async_dispatcher_send(self.hass, SIGNAL_FLAG_UPDATE, payload)
            elif topic == "RaceControlMessages":
                async_dispatcher_send(self.hass, SIGNAL_SC_UPDATE, payload)

    async def _heartbeat(self, ws: ClientWebSocketResponse) -> None:
        """Send ping replies to keep the websocket alive."""
        while True:
            await asyncio.sleep(5)
            await ws.send_str(_frame("6::"))
