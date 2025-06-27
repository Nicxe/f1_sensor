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

# SignalR record separator used to terminate frames
RS = "\x1e"


def _frame(obj: str | dict) -> str:
    """Return websocket-ready frame string."""
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
        self._attempts = 0
        self.connected = False
        self.failed = False

    async def start(self) -> None:
        """Start background task to maintain the websocket."""
        if not self._task:
            self._task = asyncio.create_task(self._run_forever())

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
        self.connected = False

    async def _run_forever(self) -> None:
        await self._listen()

    async def _connect_once(self) -> None:
        params = {
            "clientProtocol": "1.5",
            "connectionData": '[{"name":"Streaming"}]',
            "tid": random.randint(0, 9),
        }
        _LOGGER.debug("GET negotiate %s", params)
        async with self.session.get(
            NEGOTIATE_URL, params=params, headers=HEADERS
        ) as resp:
            resp.raise_for_status()
            nego = await resp.json()
            _LOGGER.debug("Negotiate response: %s", nego)
            t0_cookie = resp.cookies.get("t0")
            t0_cookie = t0_cookie.value if t0_cookie else ""

        params.update(
            {
                "transport": "webSockets",
                "connectionToken": nego.get("ConnectionToken"),
            }
        )

        ws_url = (
            "wss://livetiming.formula1.com" + nego.get("Url", "") + "/connect?" +
            urllib.parse.urlencode(params)
        )
        _LOGGER.debug("WebSocket connecting to %s", ws_url)
        headers = HEADERS | {"Cookie": f"t0={t0_cookie}"}
        self._ws = await self.session.ws_connect(
            ws_url, headers=headers, autoping=False, heartbeat=30, ssl=False
        )
        self.failed = False

        # Wait for init frame from server before subscribing
        init = await self._ws.receive()
        if init.type is WSMsgType.TEXT and init.data.endswith(RS):
            _LOGGER.debug("Init from server: %s", init.data.rstrip(RS))
        else:
            _LOGGER.warning("Unexpected init frame: %s", init)

        payload = {
            "H": "Streaming",
            "M": "Subscribe",
            "A": [self.feeds],
            "I": 1,
        }
        await self._ws.send_str(_frame(payload))
        _LOGGER.debug("Sent Subscribe")
        self._buf = ""

    async def _listen(self) -> None:
        retry_delay = 1
        while True:
            hb_task = None
            try:
                await self._connect_once()
                self.connected = True
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
                self.connected = False
                retry_delay = 1
            except asyncio.CancelledError:
                raise
            except ClientError:
                _LOGGER.exception("SignalR error")
                self.connected = False
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 300)
            finally:
                if hb_task:
                    hb_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await hb_task
                if self._ws:
                    await self._ws.close()
                    self._ws = None

    async def _process_text(self, text: str) -> None:
        self._buf += text
        if "\x1e" not in self._buf:
            return
        frames = self._buf.split("\x1e")
        self._buf = frames.pop()
        for frame in frames:
            if not frame:
                continue
            try:
                data = json.loads(frame)
            except Exception:
                continue
            await self._handle_frame(data)

    async def _handle_frame(self, data: dict) -> None:
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
