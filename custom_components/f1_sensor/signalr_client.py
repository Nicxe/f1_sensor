import asyncio
import json
import logging
import ssl
from typing import Awaitable, Callable, Dict
from urllib.parse import urlencode, quote_plus

import aiohttp

# ---- Monkey-patch: gör Subject synlig för signalrcore_async ----
from rx.subjects import Subject  # RxPY v1.x
import signalrcore_async.hub.base_hub_connection as _base
_base.Subject = Subject          # injicera symbolen i bibliotekets modul
# ----------------------------------------------------------------

from signalrcore_async.hub_connection_builder import HubConnectionBuilder

# Home Assistant requires that any potentially blocking operation is moved
# out of the event loop. ``ssl.SSLContext.load_default_certs`` performs disk
# I/O which triggers a warning if executed directly. ``get_ssl_context``
# builds the context in a background thread so the loop never blocks.


async def get_ssl_context() -> ssl.SSLContext:
    """Create SSL context without blocking the event loop."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, ctx.load_default_certs)
    return ctx

# The signalrcore-async library still relies on the legacy ``websockets`` API
# which exposes ``extra_headers``. In newer versions of ``websockets`` the
# default ``connect`` helper dropped this argument in favour of
# ``additional_headers``. This results in ``create_connection`` receiving an
# unexpected ``extra_headers`` keyword argument when a proxy is configured. To
# stay compatible with both old and new ``websockets`` releases we patch
# ``websockets.connect`` to point at the legacy implementation if needed.
try:  # pragma: no cover - only runs on newer websockets versions
    import inspect
    import websockets

    if "additional_headers" in inspect.signature(websockets.connect).parameters:
        from websockets.legacy.client import connect as legacy_connect

        websockets.connect = legacy_connect  # type: ignore[assignment]
except Exception:  # pragma: no cover - fail silently if patching is impossible
    pass

LOGGER = logging.getLogger(__name__)


class F1SignalRClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        callback: Callable[[str, Dict], Awaitable[None]],
    ) -> None:
        self._session = session
        self._callback = callback
        self._hub = None
        self.connected = False
        self.failed = False
        self._stopped = False
        self._attempts = 0
        self.on_open: Callable[[], Awaitable[None]] | None = None
        self.on_close: Callable[[], Awaitable[None]] | None = None

    async def start(self) -> None:
        self._stopped = False
        self.failed = False
        self._attempts = 0
        await self._connect()

    async def stop(self) -> None:
        self._stopped = True
        if self._hub:
            await self._hub.stop()
            self._hub = None
        self.connected = False

    async def _connect(self) -> None:
        while not self._stopped:
            try:
                await self._start_once()
                return
            except Exception as err:  # pragma: no cover - network errors
                LOGGER.warning("SignalR connect failed: %s", err)
                self._attempts += 1
                if self._attempts >= 3:
                    self.failed = True
                    if self.on_close:
                        await self.on_close()
                    return
                await asyncio.sleep(min(2**self._attempts, 30))

    async def _start_once(self) -> None:
        url = "https://livetiming.formula1.com/signalr/negotiate?clientProtocol=1.5"
        async with self._session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = data.get("ConnectionToken")
            cookie = resp.headers.get("Set-Cookie", "")
        params = {
            "transport": "webSockets",
            "clientProtocol": "1.5",
            "connectionToken": token,
            "connectionData": json.dumps([{"name": "streaming"}]),
        }
        ws_url = "wss://livetiming.formula1.com/signalr/connect?" + urlencode(
            params, quote_via=quote_plus
        )
        builder = HubConnectionBuilder()
        ssl_context = await get_ssl_context()
        self._hub = (
            builder.with_url(
                ws_url,
                options={
                    "headers": {"Cookie": cookie},
                    "skip_negotiation": True,
                    "ssl": ssl_context,
                },
            )
            .build()
        )
        self._hub.on_open(lambda: asyncio.create_task(self._on_open()))
        self._hub.on_close(lambda: asyncio.create_task(self._on_close()))
        for topic in [
            "TrackStatus",
            "RaceControlMessages",
            "SessionStatus",
            "Heartbeat",
        ]:
            self._hub.on(
                topic,
                lambda args, t=topic: asyncio.create_task(
                    self._callback(t, args[0] if args else {})
                ),
            )
        # ``start`` internally sets up SSL certificates which may trigger
        # synchronous disk access. Running it in a thread avoids blocking the
        # Home Assistant event loop.
        await asyncio.to_thread(lambda: asyncio.run(self._hub.start()))

    async def _on_open(self) -> None:
        self.connected = True
        self._attempts = 0
        if self.on_open:
            await self.on_open()
        if self._hub:
            self._hub.send(
                "Subscribe",
                [[
                    "TrackStatus",
                    "RaceControlMessages",
                    "SessionStatus",
                    "Heartbeat",
                ]],
            )

    async def _on_close(self) -> None:
        if self.connected:
            self.connected = False
            if self.on_close:
                await self.on_close()
        if not self._stopped:
            await self._connect()
