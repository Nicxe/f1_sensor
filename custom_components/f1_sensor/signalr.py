import json
import logging
import datetime as dt
import asyncio
import time
from typing import AsyncGenerator, Callable, Dict, Iterable, List, Optional, Protocol

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'

# Subscribe to core live streams used across the integration
# Added: TimingData, DriverList, TimingAppData to support driver sensors
# Added: TeamRadio to support team radio sensor
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
        "Heartbeat",
        "ExtrapolatedClock",
        "TimingData",
        "DriverList",
        "TimingAppData",
        "TopThree",
        "TyreStintSeries",
        "TeamRadio",
        "PitStopSeries",
        "ChampionshipPrediction",
    ]],
    "I": 1,
}


class LiveTransport(Protocol):
    async def ensure_connection(self) -> None: ...
    async def messages(self) -> AsyncGenerator[dict, None]: ...
    async def close(self) -> None: ...


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
        _LOGGER.debug(
            "Subscribed to RaceControlMessages, TrackStatus, SessionStatus, WeatherData, "
            "LapCount, SessionInfo, TimingData, DriverList, TimingAppData, TopThree, "
            "TyreStintSeries, TeamRadio"
        )

    async def ensure_connection(self) -> None:
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

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        *,
        transport_factory: Callable[[], LiveTransport] | None = None,
    ) -> None:
        self._hass = hass
        self._session = session
        self._transport_factory = transport_factory
        self._client: Optional[LiveTransport] = None
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
        self._expect_heartbeat = False
        self._last_heartbeat_at: float | None = None
        self._heartbeat_guard: Optional[asyncio.Task] = None
        self._heartbeat_timeout = 45.0
        self._heartbeat_check_interval = 5.0

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
            _LOGGER.debug("LiveBus start requested but already running")
            return
        self._running = True
        _LOGGER.info("LiveBus starting (transport=%s)", "custom" if self._transport_factory else "native")
        self._client = self._create_client()
        self._task = self._hass.loop.create_task(self._run())
        if self._heartbeat_guard is None or self._heartbeat_guard.done():
            self._heartbeat_guard = self._hass.loop.create_task(self._monitor_heartbeat())

    async def _run(self) -> None:
        try:
            while self._running:
                try:
                    if self._client is None:
                        self._client = self._create_client()
                    await self._client.ensure_connection()
                    self._last_heartbeat_at = time.time()
                    _LOGGER.info("LiveBus connected to SignalR")
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
                                                    # Always dispatch so heartbeat/activity bookkeeping
                                                    # works even when there are no explicit subscribers
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
                    # Log replay-related errors at DEBUG since they're expected during replay stop
                    err_str = str(err)
                    if "Replay" in err_str or "replay" in err_str:
                        _LOGGER.debug("LiveBus replay transport closed: %s", err)
                    else:
                        _LOGGER.warning("LiveBus websocket error: %s", err)
                    # Add delay before reconnect to prevent tight loops
                    if self._running:
                        await asyncio.sleep(2)
                finally:
                    if self._client:
                        await self._client.close()
                        self._client = None
                # Periodic compact DEBUG summary
                self._maybe_log_summary()
        except asyncio.CancelledError:
            pass

    def _dispatch(self, stream: str, data: dict) -> None:
        try:
            # Update counters
            self._cnt[stream] = self._cnt.get(stream, 0) + 1
            self._last_ts[stream] = time.time()
            if stream == "Heartbeat":
                self._last_heartbeat_at = time.time()
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
        _LOGGER.info("LiveBus shutting down")
        if self._task:
            self._task.cancel()
            try:
                await self._task  # Wait for task to actually finish
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._heartbeat_guard:
            self._heartbeat_guard.cancel()
            try:
                await self._heartbeat_guard
            except asyncio.CancelledError:
                pass
            self._heartbeat_guard = None
        if self._client:
            await self._client.close()
            self._client = None

    def _create_client(self) -> LiveTransport:
        if callable(self._transport_factory):
            return self._transport_factory()
        return SignalRClient(self._hass, self._session)

    async def _monitor_heartbeat(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(self._heartbeat_check_interval)
                if not self._running:
                    break
                if not self._expect_heartbeat:
                    continue
                hb_age = self.last_heartbeat_age()
                # Fall back to generic activity age if we have no explicit
                # SignalR "Heartbeat" frames; this better matches how F1
                # actually behaves in practice.
                activity_age = self.last_stream_activity_age()
                effective_age = hb_age if hb_age is not None else activity_age
                if effective_age is None or effective_age < self._heartbeat_timeout:
                    continue
                # Treat this as a soft reconnect signal, not a hard warning –
                # it's normal for the upstream to be quiet between bursts.
                _LOGGER.debug(
                    "LiveBus inactivity for %.0fs (hb=%s, activity=%s); forcing SignalR reconnect",
                    effective_age,
                    f"{hb_age:.1f}s" if hb_age is not None else "n/a",
                    f"{activity_age:.1f}s" if activity_age is not None else "n/a",
                )
                if self._client:
                    await self._client.close()
                    self._client = None
        except asyncio.CancelledError:
            pass

    def set_heartbeat_expectation(self, enabled: bool) -> None:
        self._expect_heartbeat = bool(enabled)
        if enabled:
            if self._last_heartbeat_at is None:
                self._last_heartbeat_at = time.time()
            _LOGGER.info("Heartbeat guard ENABLED")
        else:
            self._last_heartbeat_at = None
            _LOGGER.info("Heartbeat guard DISABLED")

    def last_heartbeat_age(self) -> float | None:
        if self._last_heartbeat_at is None:
            return None
        return time.time() - self._last_heartbeat_at

    def last_stream_activity_age(self, streams: Iterable[str] | None = None) -> float | None:
        """Return age in seconds for the most recent payload among given streams."""
        if not self._last_ts:
            return None
        now = time.time()
        if streams:
            ages: list[float] = []
            for stream in streams:
                ts = self._last_ts.get(stream)
                if ts is not None:
                    ages.append(now - ts)
            if not ages:
                return None
            return min(ages)
        ages = [now - ts for ts in self._last_ts.values() if ts is not None]
        if not ages:
            return None
        return min(ages)

    def get_last_payload(self, stream: str) -> dict | None:
        data = self._last_payload.get(stream)
        return data if isinstance(data, dict) else None

    async def swap_transport(
        self, transport_factory: Callable[[], LiveTransport] | None
    ) -> None:
        """Hot-swap transport for replay mode.

        This allows switching between live SignalR and replay transport
        without recreating the bus or losing subscribers.
        """
        was_running = self._running

        if was_running:
            _LOGGER.info("Stopping LiveBus for transport swap")
            await self.async_close()

        self._transport_factory = transport_factory
        self._last_payload.clear()  # Clear cached payloads from previous session
        self._cnt.clear()
        self._last_ts.clear()

        # For replay mode (transport_factory provided), always start the bus
        # For restoring to live (transport_factory=None), only restart if it was running
        # (let LiveSessionSupervisor handle normal reconnection)
        if transport_factory is not None:
            _LOGGER.info("Starting LiveBus with replay transport")
            await self.start()
        elif was_running:
            _LOGGER.info("Restarting LiveBus with live transport")
            await self.start()

    def inject_message(self, stream: str, payload: dict) -> None:
        """Inject a message directly into the bus (for replay mode).

        This allows external code to feed data into the bus without
        going through the transport layer.
        """
        subs_count = len(self._subs.get(stream, []))
        _LOGGER.debug(
            "inject_message: stream=%s, subs=%d, payload_keys=%s",
            stream, subs_count,
            list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        )
        if isinstance(payload, dict):
            self._last_payload[stream] = payload
        self._dispatch(stream, payload)
