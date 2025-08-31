import json
import logging
import datetime as dt
import asyncio
from typing import AsyncGenerator

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

from .const import FLAG_MACHINE
from .flag_state import FlagState

from . import rc_transform

_LOGGER = logging.getLogger(__name__)

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'

# Subscribe to RaceControl, TrackStatus and SessionStatus streams
SUBSCRIBE_MSG = {
    "H": "Streaming",
    "M": "Subscribe",
    "A": [["RaceControlMessages", "TrackStatus", "SessionStatus"]],
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
        _LOGGER.debug("Subscribed to RaceControlMessages, TrackStatus and SessionStatus")

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
                                raw = hub_msg["A"][1]["Messages"]
                                if isinstance(raw, list):
                                    iterable = raw
                                elif isinstance(raw, dict):
                                    iterable = sorted(
                                        raw.values(), key=lambda m: m.get("Utc")
                                    )
                                else:
                                    _LOGGER.warning("Unknown RC format: %s", type(raw))
                                    continue
                                # Defer processing of RaceControl messages to coordinators
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
                elif "R" in payload:
                    if "RaceControlMessages" in payload["R"]:
                        raw = payload["R"]["RaceControlMessages"]["Messages"]
                        if isinstance(raw, list):
                            iterable = raw
                        elif isinstance(raw, dict):
                            iterable = sorted(
                                raw.values(), key=lambda m: m.get("Utc")
                            )
                        else:
                            _LOGGER.warning("Unknown RC format: %s", type(raw))
                            continue
                        # Defer processing of RaceControl messages to coordinators
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

                index += 1
                yield payload
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break

    async def _handle_rc(self, rc_raw) -> None:
        try:
            clean = rc_transform.clean_rc(rc_raw, self._t0)
            if not clean:
                return

            if self._startup_cutoff:
                rc_time = dt.datetime.fromisoformat(clean["utc"].replace("Z", "+00:00"))
                if rc_time.tzinfo is None:
                    rc_time = rc_time.replace(tzinfo=dt.timezone.utc)
                if rc_time < self._startup_cutoff:
                    return

            hass = self._hass
            machine = hass.data.get(FLAG_MACHINE)
            if machine is None:
                machine = FlagState()
                hass.data[FLAG_MACHINE] = machine

            changed, attrs = await machine.apply(clean)
            if changed is not None:
                self._async_update_flag_sensor(changed, attrs)
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.warning(
                "Race control transform failed: %s", exc, exc_info=True
            )

    def _async_update_flag_sensor(self, state: str, attrs: dict) -> None:
        self._hass.states.async_set(
            "sensor.f1_flag",
            state,
            attrs,
        )

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
