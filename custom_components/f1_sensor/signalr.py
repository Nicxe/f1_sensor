import json
import logging
from typing import AsyncGenerator, Optional

from aiohttp import ClientSession, WSMsgType

_LOGGER = logging.getLogger(__name__)

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'
SUBSCRIBE_MSG = {
    "H": "Streaming",
    "M": "Subscribe",
    "A": [["RaceControlMessages"]],
    "I": 1,
}


class SignalRClient:
    """Minimal SignalR client for Formula 1 live timing."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._ws = None

    async def connect(self) -> None:
        params = {"clientProtocol": "1.5", "connectionData": HUB_DATA}
        async with self._session.get(NEGOTIATE_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = data.get("ConnectionToken")
            cookie = resp.headers.get("Set-Cookie")

        headers = {
            "User-Agent": "BestHTTP",
            "Accept-Encoding": "gzip,identity",
        }
        if cookie:
            headers["Cookie"] = cookie

        params = {
            "transport": "webSockets",
            "clientProtocol": "1.5",
            "connectionToken": token,
            "connectionData": HUB_DATA,
        }
        self._ws = await self._session.ws_connect(
            CONNECT_URL, params=params, headers=headers
        )
        await self._ws.send_json(SUBSCRIBE_MSG)

    async def messages(self) -> AsyncGenerator[dict, None]:
        if not self._ws:
            return
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                yield payload
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
