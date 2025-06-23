import asyncio
import contextlib
import json
import logging
import ssl
from urllib.parse import quote_plus, urlencode
from typing import List

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    SIGNAL_FLAG_UPDATE,
    SIGNAL_SC_UPDATE,
    SUBSCRIBE_FEEDS,
    NEGOTIATE_URL,
)

LOGGER = logging.getLogger(__name__)


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
        backoff = 1
        while True:
            try:
                await self._connect_once()
                self.connected = True
                self._attempts = 0
                await self._listen()
                backoff = 1
            except asyncio.CancelledError:
                break
            except Exception as err:  # pragma: no cover - network errors
                LOGGER.warning("SignalR connection error: %s", err)
                self.connected = False
                self._attempts += 1
                if self._attempts >= 3:
                    self.failed = True
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)
            finally:
                if self._ws:
                    await self._ws.close()
                    self._ws = None

    async def _connect_once(self) -> None:
        params = {"clientProtocol": "1.5"}
        async with self.session.get(NEGOTIATE_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = data.get("ConnectionToken")
            cookie = resp.headers.get("Set-Cookie", "")

        ws_params = {
            "transport": "webSockets",
            "clientProtocol": "1.5",
            "connectionToken": token,
            "connectionData": json.dumps([{"name": "streaming"}]),
        }
        ws_url = "wss://livetiming.formula1.com/signalr/connect?" + urlencode(
            ws_params, quote_via=quote_plus
        )

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, ctx.load_default_certs)

        self._ws = await self.session.ws_connect(
            ws_url, heartbeat=30, ssl=ctx, headers={"Cookie": cookie}
        )
        self.failed = False

        payload = {"H": "Streaming", "M": "Subscribe", "A": [self.feeds], "I": 1}
        await self._ws.send_str(json.dumps(payload) + "\x1e")
        self._buf = ""

    async def _listen(self) -> None:
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                await self._process_text(msg.data)
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
                break
        self.connected = False

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
