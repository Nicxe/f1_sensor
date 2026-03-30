from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Iterable
from contextlib import suppress
import datetime as dt
import json
import logging
import time
from typing import Any, Protocol

from aiohttp import ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

StreamPayload = Any

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'

CORE_NEGOTIATE_URL = "https://livetiming.formula1.com/signalrcore/negotiate"
CORE_CONNECT_URL = "wss://livetiming.formula1.com/signalrcore"
RECORD_SEP = "\x1e"

# Capability matrix for the current no-auth SignalR Core implementation.
# Public live streams are subscribed during normal live sessions.
# Auth-gated and replay-only streams stay defined here so future auth support
# can extend the runtime contract without changing entity registration.
PUBLIC_LIVE_STREAMS = (
    "RaceControlMessages",
    "TrackStatus",
    "SessionStatus",
    "WeatherData",
    "LapCount",
    "SessionInfo",
    "SessionData",
    "Heartbeat",
    "ExtrapolatedClock",
    "TimingData",
    "DriverList",
    "TimingAppData",
    "TopThree",
)

AUTH_GATED_LIVE_STREAMS = (
    "CarData.z",
    "DriverRaceInfo",
    "Position.z",
    "ChampionshipPrediction",
)

REPLAY_ONLY_STREAMS = (
    "TeamRadio",
    "PitStopSeries",
)


def build_live_subscribe_streams(
    *, include_auth_gated: bool = False
) -> tuple[str, ...]:
    """Return the SignalR streams that should be subscribed for live mode."""
    streams = list(PUBLIC_LIVE_STREAMS)
    if include_auth_gated:
        streams.extend(AUTH_GATED_LIVE_STREAMS)
    return tuple(streams)


NO_AUTH_LIVE_STREAMS = build_live_subscribe_streams()

SUBSCRIBE_MSG = {
    "H": "Streaming",
    "M": "Subscribe",
    "A": [list(NO_AUTH_LIVE_STREAMS)],
    "I": 1,
}

DEBUG_SUMMARY_STREAMS = (
    "SessionStatus",
    "TrackStatus",
    "TopThree",
    "TimingAppData",
)


class LiveTransport(Protocol):
    async def ensure_connection(self) -> None: ...
    async def messages(self) -> AsyncGenerator[dict]: ...
    async def close(self) -> None: ...


class SignalRLegacyClient:
    """Minimal legacy SignalR client for Formula 1 live timing."""

    def __init__(self, hass: HomeAssistant, session: ClientSession) -> None:
        self._hass = hass
        self._session = session
        self._ws = None
        self._t0 = dt.datetime.now(dt.UTC)
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
        self._t0 = dt.datetime.now(dt.UTC)
        self._startup_cutoff = self._t0 - dt.timedelta(seconds=30)
        _LOGGER.debug("SignalR connection established")
        _LOGGER.debug(
            "Subscribed to %s",
            ", ".join(SUBSCRIBE_MSG["A"][0]),
        )

    async def ensure_connection(self) -> None:
        """Try to (re)connect using exponential back-off."""
        import asyncio

        from .const import BACK_OFF_FACTOR, FAST_RETRY_SEC, MAX_RETRY_SEC

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

    async def messages(self) -> AsyncGenerator[dict]:
        if not self._ws:
            return
        index = 0
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                payload = None
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    payload = None
                if payload is None:
                    continue
                # Per-message payload logging suppressed to reduce verbosity

                if "M" in payload:
                    for hub_msg in payload["M"]:
                        if hub_msg.get("M") == "feed":
                            # Per-message logging suppressed (summarized by LiveBus)
                            pass
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
                except Exception as exc:  # pylint: disable=broad-except
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


class SignalRCoreClient:
    """SignalR Core client for Formula 1 live timing (/signalrcore endpoint).

    Translates Core protocol messages (type 1/3/6/7 with \\x1e separator)
    into legacy-format dicts so LiveBus._run() needs no changes.
    """

    def __init__(self, hass: HomeAssistant, session: ClientSession) -> None:
        self._hass = hass
        self._session = session
        self._ws = None
        self._cookie: str | None = None

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to F1 SignalR Core service")
        negotiate_params = {"negotiateVersion": "1"}

        # Step 1: OPTIONS to obtain AWSALBCORS load-balancer cookie
        try:
            async with self._session.options(
                CORE_NEGOTIATE_URL, params=negotiate_params
            ) as resp:
                cookie_header = resp.headers.get("Set-Cookie", "")
                for part in cookie_header.split(","):
                    part = part.strip()
                    if "AWSALBCORS=" in part:
                        self._cookie = part.split("AWSALBCORS=")[1].split(";")[0]
                        break
        except Exception:  # noqa: BLE001
            _LOGGER.debug("OPTIONS request failed, continuing without cookie")

        # Step 2: POST negotiate to obtain connectionToken
        headers = {}
        if self._cookie:
            headers["Cookie"] = f"AWSALBCORS={self._cookie}"
        async with self._session.post(
            CORE_NEGOTIATE_URL, params=negotiate_params, headers=headers
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = data.get("connectionToken") or data.get("ConnectionToken", "")

        # Step 3: WebSocket connect
        ws_headers = {}
        if self._cookie:
            ws_headers["Cookie"] = f"AWSALBCORS={self._cookie}"
        self._ws = await self._session.ws_connect(
            CORE_CONNECT_URL, params={"id": token}, headers=ws_headers
        )

        # Step 4: Handshake
        await self._ws.send_str(
            json.dumps({"protocol": "json", "version": 1}) + RECORD_SEP
        )
        hs_msg = await self._ws.receive()
        if hs_msg.type == WSMsgType.TEXT:
            hs_data = hs_msg.data.replace(RECORD_SEP, "").strip()
            if hs_data:
                hs_json = json.loads(hs_data)
                if "error" in hs_json:
                    raise ConnectionError(
                        f"SignalR Core handshake error: {hs_json['error']}"
                    )
        elif hs_msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
            raise ConnectionError("WebSocket closed during handshake")

        # Step 5: Subscribe
        subscribe = {
            "type": 1,
            "target": "Subscribe",
            "arguments": SUBSCRIBE_MSG["A"],
            "invocationId": "0",
        }
        await self._ws.send_str(json.dumps(subscribe) + RECORD_SEP)

        _LOGGER.debug("SignalR Core connection established and subscribed")

    async def ensure_connection(self) -> None:
        """Try to (re)connect using exponential back-off."""
        from .const import BACK_OFF_FACTOR, FAST_RETRY_SEC, MAX_RETRY_SEC

        delay = FAST_RETRY_SEC
        while True:
            try:
                await self.connect()
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "SignalR Core reconnect failed (%s). Retrying in %s s …",
                    err,
                    delay,
                )
                await asyncio.sleep(delay)
                delay = min(delay * BACK_OFF_FACTOR, MAX_RETRY_SEC)

    async def messages(self) -> AsyncGenerator[dict]:
        if not self._ws:
            return
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                for segment in msg.data.split(RECORD_SEP):
                    segment = segment.strip()
                    if not segment:
                        continue
                    try:
                        payload = json.loads(segment)
                    except json.JSONDecodeError:
                        continue
                    msg_type = payload.get("type")
                    if msg_type == 1:
                        # Invocation (feed) → translate to legacy M-format
                        target = payload.get("target", "")
                        arguments = payload.get("arguments", [])
                        yield {"M": [{"H": "Streaming", "M": target, "A": arguments}]}
                    elif msg_type == 3:
                        # Completion (initial state) → translate to legacy R-format
                        result = payload.get("result")
                        if isinstance(result, dict):
                            yield {"R": result}
                    elif msg_type == 6:
                        # Ping → respond with pong
                        try:
                            await self._ws.send_str(
                                json.dumps({"type": 6}) + RECORD_SEP
                            )
                        except Exception:  # noqa: BLE001
                            break
                    elif msg_type == 7:
                        # Close
                        error = payload.get("error", "")
                        _LOGGER.warning(
                            "SignalR Core server closed connection: %s", error
                        )
                        return
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break

    async def close(self) -> None:
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
        self._client: LiveTransport | None = None
        self._task: asyncio.Task | None = None
        self._subs: dict[str, list[Callable[[StreamPayload], None]]] = {}
        self._running = False
        # Lightweight per-stream counters for DEBUG summaries
        self._cnt: dict[str, int] = {}
        self._stream_frames: dict[str, int] = {}
        self._stream_last_keys: dict[str, list[str] | None] = {}
        self._last_ts: dict[str, float] = {}
        self._last_logged: float = time.time()
        self._log_interval: float = 10.0  # seconds
        # Cache last payload per stream so new subscribers receive latest snapshot immediately
        self._last_payload: dict[str, dict[str, Any]] = {}
        self._expect_heartbeat = False
        self._last_heartbeat_at: float | None = None
        self._heartbeat_guard: asyncio.Task | None = None
        self._heartbeat_timeout = 45.0
        self._heartbeat_check_interval = 5.0

    def subscribe(
        self, stream: str, callback: Callable[[StreamPayload], None]
    ) -> Callable[[], None]:
        lst = self._subs.setdefault(stream, [])
        lst.append(callback)

        # Immediately replay last payload for this stream (if available)
        with suppress(Exception):
            if stream in self._last_payload:
                data = self._last_payload.get(stream)
                if isinstance(data, dict):
                    with suppress(Exception):
                        callback(data)

        def _unsub() -> None:
            with suppress(Exception):
                if stream in self._subs and callback in self._subs[stream]:
                    self._subs[stream].remove(callback)
                    if not self._subs[stream]:
                        self._subs.pop(stream, None)

        return _unsub

    async def start(self) -> None:
        if self._running:
            _LOGGER.debug("LiveBus start requested but already running")
            return
        self._running = True
        _LOGGER.info(
            "LiveBus starting (transport=%s)",
            "custom" if self._transport_factory else "native",
        )
        self._client = self._create_client()
        self._task = self._hass.loop.create_task(self._run())
        if self._heartbeat_guard is None or self._heartbeat_guard.done():
            self._heartbeat_guard = self._hass.loop.create_task(
                self._monitor_heartbeat()
            )

    async def _run(self) -> None:
        with suppress(asyncio.CancelledError):
            while self._running:
                try:
                    if self._client is None:
                        self._client = self._create_client()
                    # Reset heartbeat timestamp *before* connecting so the
                    # heartbeat monitor does not close the new client while
                    # ensure_connection() is in progress (the monitor checks
                    # every 5 s and would kill the client if the stale age
                    # from the previous connection exceeds 45 s).
                    self._last_heartbeat_at = time.time()
                    await self._client.ensure_connection()
                    _LOGGER.info("LiveBus connected to SignalR")
                    async for payload in self._client.messages():
                        # Dispatch feed messages by stream name
                        with suppress(Exception):
                            if isinstance(payload, dict):
                                # Live feed frames under "M" with hub messages
                                msgs = payload.get("M")
                                if isinstance(msgs, list):
                                    for hub_msg in msgs:
                                        with suppress(Exception):
                                            if hub_msg.get("M") == "feed":
                                                args = hub_msg.get("A", [])
                                                if len(args) >= 2:
                                                    stream = args[0]
                                                    data = args[1]
                                                    # Cache latest even if no subscribers yet
                                                    if isinstance(data, dict):
                                                        self._last_payload[stream] = (
                                                            data
                                                        )
                                                    # Always dispatch so heartbeat/activity bookkeeping
                                                    # works even when there are no explicit subscribers
                                                    self._dispatch(stream, data)
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

    def _dispatch(self, stream: str, data: StreamPayload) -> None:
        with suppress(Exception):
            # Update counters
            self._cnt[stream] = self._cnt.get(stream, 0) + 1
            self._stream_frames[stream] = self._stream_frames.get(stream, 0) + 1
            self._last_ts[stream] = time.time()
            if isinstance(data, dict):
                self._stream_last_keys[stream] = list(data.keys())[:10]
            if stream == "Heartbeat":
                self._last_heartbeat_at = time.time()
            # Cache last payload for new subscribers
            if isinstance(data, dict):
                self._last_payload[stream] = data
            if _LOGGER.isEnabledFor(logging.DEBUG) and self._stream_frames[stream] == 1:
                _LOGGER.debug(
                    "LiveBus first frame for %s with keys=%s",
                    stream,
                    self._stream_last_keys.get(stream),
                )
            callbacks = list(self._subs.get(stream, []) or [])
            for cb in callbacks:
                with suppress(Exception):
                    cb(data)
            self._maybe_log_summary()

    def _maybe_log_summary(self) -> None:
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        now = time.time()
        if (now - self._last_logged) < self._log_interval:
            return
        self._last_logged = now
        with suppress(Exception):
            parts: list[str] = []
            streams = sorted(
                set(self._cnt) | set(self._stream_frames) | set(DEBUG_SUMMARY_STREAMS)
            )
            for stream in streams:
                count = self._cnt.get(stream, 0)
                total = self._stream_frames.get(stream, 0)
                last_age = None
                try:
                    ts = self._last_ts.get(stream)
                    last_age = now - ts if ts is not None else None
                except Exception:
                    last_age = None
                if last_age is not None:
                    parts.append(f"{stream}:{count}/{total} (last {last_age:.1f}s)")
                else:
                    parts.append(f"{stream}:{count}/{total} (none)")
            if parts:
                _LOGGER.debug(
                    "LiveBus summary (last %.0fs): %s",
                    self._log_interval,
                    ", ".join(parts),
                )
            # Reset window counters
            for k in list(self._cnt.keys()):
                self._cnt[k] = 0

    # Debug helpers removed to keep options surface minimal

    async def async_close(self) -> None:
        self._running = False
        _LOGGER.info("LiveBus shutting down")
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task  # Wait for task to actually finish
            self._task = None
        if self._heartbeat_guard:
            self._heartbeat_guard.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_guard
            self._heartbeat_guard = None
        if self._client:
            await self._client.close()
            self._client = None

    def _create_client(self) -> LiveTransport:
        if callable(self._transport_factory):
            return self._transport_factory()
        from .const import SIGNALR_USE_CORE

        if SIGNALR_USE_CORE:
            return SignalRCoreClient(self._hass, self._session)
        return SignalRLegacyClient(self._hass, self._session)

    async def _monitor_heartbeat(self) -> None:
        with suppress(asyncio.CancelledError):
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

    def last_stream_activity_age(
        self, streams: Iterable[str] | None = None
    ) -> float | None:
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

    def get_last_payload(self, stream: str) -> dict[str, Any] | None:
        data = self._last_payload.get(stream)
        return data if isinstance(data, dict) else None

    def stream_diagnostics(
        self, streams: Iterable[str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Return compact per-stream telemetry for diagnostics sensors."""
        selected = (
            list(dict.fromkeys(streams))
            if streams is not None
            else sorted(set(self._stream_frames) | set(self._last_ts))
        )
        now = time.time()
        return {
            stream: {
                "frame_count": self._stream_frames.get(stream, 0),
                "last_seen_age_s": (
                    round(now - self._last_ts[stream], 1)
                    if stream in self._last_ts
                    else None
                ),
                "last_payload_keys": self._stream_last_keys.get(stream),
            }
            for stream in selected
        }

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
        self._stream_frames.clear()
        self._stream_last_keys.clear()
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

    def inject_message(self, stream: str, payload: StreamPayload) -> None:
        """Inject a message directly into the bus (for replay mode).

        This allows external code to feed data into the bus without
        going through the transport layer.
        """
        subs_count = len(self._subs.get(stream, []))
        _LOGGER.debug(
            "inject_message: stream=%s, subs=%d, payload_keys=%s",
            stream,
            subs_count,
            list(payload.keys())
            if isinstance(payload, dict)
            else type(payload).__name__,
        )
        if isinstance(payload, dict):
            self._last_payload[stream] = payload
        self._dispatch(stream, payload)
