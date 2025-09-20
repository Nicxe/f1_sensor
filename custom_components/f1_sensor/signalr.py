import json
import logging
import datetime as dt
import asyncio
from typing import AsyncGenerator

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'

# Subscribe to RaceControl, TrackStatus, SessionStatus, WeatherData and LapCount streams
SUBSCRIBE_MSG = {
    "H": "Streaming",
    "M": "Subscribe",
    "A": [["RaceControlMessages", "TrackStatus", "SessionStatus", "WeatherData", "LapCount"]],
    "I": 1,
}


class SignalRClient:
    """Minimal SignalR client for Formula 1 live timing."""

    def __init__(self, hass: HomeAssistant, session: ClientSession) -> None:
        self._hass = hass
        self._session = session
        self._ws = None
        self._t0 = dt.datetime.now(dt.timezone.utc)
        self._startup_cutoff = None
        self._heartbeat_task: asyncio.Task | None = None

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
        # Renew the subscription every 5 minutes so Azure SignalR
        # inte stänger grupp‑anslutningen (20 min timeout).
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        self._t0 = dt.datetime.now(dt.timezone.utc)
        self._startup_cutoff = self._t0 - dt.timedelta(seconds=30)
        _LOGGER.debug("SignalR connection established")
        _LOGGER.debug("Subscribed to RaceControlMessages, TrackStatus, SessionStatus, WeatherData and LapCount")

    async def _ensure_connection(self) -> None:
        """Try to (re)connect using exponential back-off."""
        import asyncio
        from .const import FAST_RETRY_SEC, MAX_RETRY_SEC, BACK_OFF_FACTOR

        delay = FAST_RETRY_SEC
        while True:
            try:
                await self.connect()
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "SignalR reconnect failed (%s). Retrying in %s s …", err, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * BACK_OFF_FACTOR, MAX_RETRY_SEC)

    async def messages(self) -> AsyncGenerator[dict, None]:
        if not self._ws:
            return
        index = 0
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                _LOGGER.debug("Stream payload %s: %s", index, payload)

                if "M" in payload:
                    for hub_msg in payload["M"]:
                        if hub_msg.get("M") == "feed":
                            stream_name = hub_msg["A"][0]
                            if stream_name == "RaceControlMessages":
                                try:
                                    _LOGGER.debug("Race control message: %s", hub_msg["A"][1])
                                except Exception:  # noqa: BLE001 - defensive logging
                                    _LOGGER.debug("Race control message received (unparsed)")
                            elif stream_name == "TrackStatus":
                                # Log TrackStatus updates at debug level similar to RaceControl
                                try:
                                    _LOGGER.debug("Track status message: %s", hub_msg["A"][1])
                                except Exception:  # noqa: BLE001 - defensive logging
                                    _LOGGER.debug("Track status message received (unparsed)")
                            elif stream_name == "SessionStatus":
                                try:
                                    _LOGGER.debug("Session status message: %s", hub_msg["A"][1])
                                except Exception:  # noqa: BLE001 - defensive logging
                                    _LOGGER.debug("Session status message received (unparsed)")
                            elif stream_name == "WeatherData":
                                try:
                                    _LOGGER.debug("Weather data message: %s", hub_msg["A"][1])
                                except Exception:  # noqa: BLE001 - defensive logging
                                    _LOGGER.debug("Weather data message received (unparsed)")
                            elif stream_name == "LapCount":
                                try:
                                    _LOGGER.debug("Lap count message: %s", hub_msg["A"][1])
                                except Exception:  # noqa: BLE001 - defensive logging
                                    _LOGGER.debug("Lap count message received (unparsed)")
                elif "R" in payload:
                    if "RaceControlMessages" in payload["R"]:
                        try:
                            _LOGGER.debug("Race control message: %s", payload["R"]["RaceControlMessages"]) 
                        except Exception:  # noqa: BLE001 - defensive logging
                            _LOGGER.debug("Race control message received (unparsed)")
                    if "TrackStatus" in payload["R"]:
                        try:
                            _LOGGER.debug("Track status message: %s", payload["R"]["TrackStatus"]) 
                        except Exception:  # noqa: BLE001 - defensive logging
                            _LOGGER.debug("Track status message received (unparsed)")
                    if "SessionStatus" in payload["R"]:
                        try:
                            _LOGGER.debug("Session status message: %s", payload["R"]["SessionStatus"]) 
                        except Exception:  # noqa: BLE001 - defensive logging
                            _LOGGER.debug("Session status message received (unparsed)")
                    if "WeatherData" in payload["R"]:
                        try:
                            _LOGGER.debug("Weather data message: %s", payload["R"]["WeatherData"]) 
                        except Exception:  # noqa: BLE001 - defensive logging
                            _LOGGER.debug("Weather data message received (unparsed)")
                    if "LapCount" in payload["R"]:
                        try:
                            _LOGGER.debug("Lap count message: %s", payload["R"]["LapCount"]) 
                        except Exception:  # noqa: BLE001 - defensive logging
                            _LOGGER.debug("Lap count message received (unparsed)")

                index += 1
                yield payload
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break

    # Flag-specific processing removed; coordinators handle TrackStatus/SessionStatus only

    async def _heartbeat(self) -> None:
        """Send Subscribe‑kommandot var 5:e minut för att hålla strömmen vid liv."""
        try:
            while True:
                await asyncio.sleep(300)  # 5 min
                if self._ws is None or self._ws.closed:
                    break
                try:
                    await self._ws.send_json(SUBSCRIBE_MSG)
                    _LOGGER.debug("Heartbeat: subscriptions renewed")
                except Exception as exc:          # pylint: disable=broad-except
                    _LOGGER.warning("Heartbeat failed: %s", exc)
                    break
        except asyncio.CancelledError:
            # Normalt vid nedstängning / reconnect
            pass

    async def close(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
