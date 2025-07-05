import base64
import json
import logging
import datetime as dt
from typing import AsyncGenerator, Optional

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

from . import rc_transform

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

    def __init__(self, hass: HomeAssistant, session: ClientSession) -> None:
        self._hass = hass
        self._session = session
        self._ws = None
        self._t0 = dt.datetime.utcnow()

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to F1 SignalR service")
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
        self._t0 = dt.datetime.utcnow()
        _LOGGER.debug("SignalR connection established")
        _LOGGER.debug("Subscribed to RaceControlMessages")

    async def messages(self) -> AsyncGenerator[dict, None]:
        if not self._ws:
            return
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                _LOGGER.debug("Stream payload: %s", payload)
                messages = payload.get("M") if isinstance(payload, dict) else None
                if messages:
                    for update in messages:
                        args = update.get("A", [])
                        if len(args) >= 2 and args[0] == "RaceControlMessages":
                            await self._on_rc(base64.b64decode(args[1]))
                yield payload
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _on_rc(self, payload: bytes) -> None:
        """Handle RaceControlMessages by updating sensor state."""
        clean = rc_transform.clean_rc(payload, self._t0)
        _LOGGER.debug("Race control message: %s", clean)
        self._hass.states.async_set("sensor.f1_flag", clean["flag"], clean)
