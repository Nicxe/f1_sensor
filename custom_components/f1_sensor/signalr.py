import json
import logging
import datetime as dt
import asyncio
import time
from typing import AsyncGenerator, Callable, Dict, List, Optional

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'

# Subscribe to core live streams used across the integration
# Added: TimingData, DriverList, TimingAppData to support driver sensors
SUBSCRIBE_MSG = {
    "H": "Streaming",
    "M": "Subscribe",
    "A": [[
        "RaceControlMessages",
        "TrackStatus",
        "SessionStatus",
        "WeatherData",
        "LapCount",
        "SessionInfo",
        "TimingData",
        "DriverList",
        "TimingAppData",
    ]],
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
        _LOGGER.debug("Subscribed to RaceControlMessages, TrackStatus, SessionStatus, WeatherData, LapCount, SessionInfo, TimingData, DriverList, TimingAppData")

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
                # Per-message payload logging suppressed to reduce verbosity

                if "M" in payload:
                    for hub_msg in payload["M"]:
                        if hub_msg.get("M") == "feed":
                            stream_name = hub_msg["A"][0]
                            # Per-message logging suppressed (summarized by LiveBus)
                elif "R" in payload:
                    # Per-message RPC logging suppressed
                    pass

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


class LiveBus:
    """Single shared SignalR connection with per-stream subscribers.

    Subscribers receive already-extracted stream payloads (e.g. dict for "TrackStatus").
    """

    def __init__(self, hass: HomeAssistant, session: ClientSession) -> None:
        self._hass = hass
        self._session = session
        self._client: Optional[SignalRClient] = None
        self._task: Optional[asyncio.Task] = None
        self._subs: Dict[str, List[Callable[[dict], None]]] = {}
        self._running = False
        # Lightweight per-stream counters for DEBUG summaries
        self._cnt: Dict[str, int] = {}
        self._last_ts: Dict[str, float] = {}
        self._last_logged: float = time.time()
        self._log_interval: float = 10.0  # seconds
        # Cache last payload per stream so new subscribers receive latest snapshot immediately
        self._last_payload: Dict[str, dict] = {}

    def subscribe(self, stream: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        lst = self._subs.setdefault(stream, [])
        lst.append(callback)

        # Immediately replay last payload for this stream (if available)
        try:
            if stream in self._last_payload:
                data = self._last_payload.get(stream)
                if isinstance(data, dict):
                    try:
                        callback(data)
                    except Exception:
                        pass
        except Exception:
            pass

        def _unsub() -> None:
            try:
                if stream in self._subs and callback in self._subs[stream]:
                    self._subs[stream].remove(callback)
                    if not self._subs[stream]:
                        self._subs.pop(stream, None)
            except Exception:
                pass

        return _unsub

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._client = SignalRClient(self._hass, self._session)
        self._task = self._hass.loop.create_task(self._run())

    async def _run(self) -> None:
        assert self._client is not None
        try:
            while self._running:
                try:
                    await self._client._ensure_connection()
                    async for payload in self._client.messages():
                        # Dispatch feed messages by stream name
                        try:
                            if isinstance(payload, dict):
                                # Live feed frames under "M" with hub messages
                                msgs = payload.get("M")
                                if isinstance(msgs, list):
                                    for hub_msg in msgs:
                                        try:
                                            if hub_msg.get("M") == "feed":
                                                args = hub_msg.get("A", [])
                                                if len(args) >= 2:
                                                    stream = args[0]
                                                    data = args[1]
                                                    # Cache latest even if no subscribers yet
                                                    if isinstance(data, dict):
                                                        self._last_payload[stream] = data
                                                    # Dispatch to current subscribers (if any)
                                                    if stream in self._subs:
                                                        self._dispatch(stream, data)
                                        except Exception:  # noqa: BLE001
                                            continue
                                # RPC results under "R" (rare)
                                result = payload.get("R")
                                if isinstance(result, dict):
                                    for key, value in result.items():
                                        # Cache last payload for key
                                        if isinstance(value, dict):
                                            self._last_payload[key] = value
                                        # Dispatch if there are subscribers now
                                        if key in self._subs:
                                            self._dispatch(key, value)
                        except Exception:  # noqa: BLE001
                            continue
                except Exception as err:  # pragma: no cover - network errors
                    _LOGGER.warning("LiveBus websocket error: %s", err)
                finally:
                    if self._client:
                        await self._client.close()
                # Periodic compact DEBUG summary
                self._maybe_log_summary()
        except asyncio.CancelledError:
            pass

    def _dispatch(self, stream: str, data: dict) -> None:
        try:
            # Update counters
            self._cnt[stream] = self._cnt.get(stream, 0) + 1
            self._last_ts[stream] = time.time()
            # Cache last payload for new subscribers
            if isinstance(data, dict):
                self._last_payload[stream] = data
            callbacks = list(self._subs.get(stream, []) or [])
            for cb in callbacks:
                try:
                    cb(data)
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass

    def _maybe_log_summary(self) -> None:
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        now = time.time()
        if (now - self._last_logged) < self._log_interval:
            return
        self._last_logged = now
        try:
            parts: List[str] = []
            for stream, count in sorted(self._cnt.items()):
                last_age = None
                try:
                    last_age = now - self._last_ts.get(stream, now)
                except Exception:
                    last_age = None
                if last_age is not None:
                    parts.append(f"{stream}:{count} (last {last_age:.1f}s)")
                else:
                    parts.append(f"{stream}:{count}")
            if parts:
                _LOGGER.debug("LiveBus summary (last %.0fs): %s", self._log_interval, ", ".join(parts))
            # Reset window counters
            for k in list(self._cnt.keys()):
                self._cnt[k] = 0
        except Exception:
            pass

    # Debug helpers removed to keep options surface minimal

    async def async_close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._client:
            await self._client.close()
            self._client = None
