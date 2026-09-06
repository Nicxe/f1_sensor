from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Iterable
from contextlib import suppress
import datetime as dt
from enum import StrEnum
from http.cookies import SimpleCookie
import json
import logging
import random
import time
from typing import Any, Protocol

from aiohttp import ClientResponseError, ClientSession, WSMsgType
from homeassistant.core import HomeAssistant

from .helpers import normalize_live_timing_auth_header
from .providers import ProviderRegistry

_LOGGER = logging.getLogger(__name__)

StreamPayload = Any

NEGOTIATE_URL = "https://livetiming.formula1.com/signalr/negotiate"
CONNECT_URL = "wss://livetiming.formula1.com/signalr/connect"
HUB_DATA = '[{"name":"Streaming"}]'

CORE_NEGOTIATE_URL = "https://livetiming.formula1.com/signalrcore/negotiate"
CORE_CONNECT_URL = "wss://livetiming.formula1.com/signalrcore"
RECORD_SEP = "\x1e"

# Capability matrix for the current SignalR live implementation.
# Public live streams are always subscribed during live sessions. Auth-gated
# streams are added only when Live Timing authentication is configured.
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
    "Position.z",
    "DriverRaceInfo",
    "ChampionshipPrediction",
    "TeamRadio",
    "PitStopSeries",
)

REPLAY_ONLY_STREAMS: tuple[str, ...] = ("LapHistory",)

AUTH_FAILURE_STATUSES = frozenset({401, 403})
SIGNALR_CONNECT_TIMEOUT = 30.0
SIGNALR_BACKOFF_JITTER = 0.2


class LiveConnectionState(StrEnum):
    """Lifecycle states for the shared live timing transport."""

    STOPPED = "stopped"
    CONNECTING = "connecting"
    LIVE = "live"
    RETRYING = "retrying"
    AUTH_LIMITED = "auth_limited"


def build_live_subscribe_streams(
    *,
    include_auth_gated: bool = False,
    requested_streams: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Return the SignalR streams that should be subscribed for live mode."""
    streams = list(PUBLIC_LIVE_STREAMS)
    if include_auth_gated:
        streams.extend(AUTH_GATED_LIVE_STREAMS)
    if requested_streams is not None:
        requested = frozenset(str(stream) for stream in requested_streams)
        streams = [stream for stream in streams if stream in requested]
    return tuple(streams)


def build_subscribe_message(
    *,
    include_auth_gated: bool = False,
    requested_streams: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a SignalR legacy subscribe message for the selected capability set."""
    return {
        "H": "Streaming",
        "M": "Subscribe",
        "A": [
            list(
                build_live_subscribe_streams(
                    include_auth_gated=include_auth_gated,
                    requested_streams=requested_streams,
                )
            )
        ],
        "I": 1,
    }


NO_AUTH_LIVE_STREAMS = build_live_subscribe_streams()

SUBSCRIBE_MSG = build_subscribe_message()

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
    async def update_streams(self, streams: Iterable[str]) -> None: ...


class SignalRAuthenticationError(Exception):
    """Raised when F1 Live Timing rejects the configured authorization."""


def _normalize_auth_header(auth_header: str | None) -> str | None:
    value = normalize_live_timing_auth_header(auth_header)
    return value or None


def _authorization_headers(auth_header: str | None) -> dict[str, str]:
    if not auth_header:
        return {}
    return {"Authorization": auth_header}


def _is_authentication_error(err: Exception) -> bool:
    if isinstance(err, ClientResponseError):
        return err.status in AUTH_FAILURE_STATUSES
    text = str(err).lower()
    return any(
        marker in text
        for marker in (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "auth",
            "credential",
        )
    )


def _is_authentication_close_error(error: object) -> bool:
    text = str(error or "").lower()
    return any(
        marker in text
        for marker in (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "auth",
            "credential",
        )
    )


def _response_cookie_value(response: Any, name: str) -> str | None:
    """Return one response cookie without forwarding Set-Cookie attributes."""
    cookies = getattr(response, "cookies", None)
    if cookies:
        with suppress(KeyError, TypeError):
            value = cookies[name].value
            if isinstance(value, str) and value:
                return value

    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    values: list[str] = []
    getall = getattr(headers, "getall", None)
    if callable(getall):
        values.extend(getall("Set-Cookie", []))
    elif raw_header := headers.get("Set-Cookie"):
        values.append(raw_header)
    for raw_header in values:
        parsed = SimpleCookie()
        with suppress(Exception):
            parsed.load(raw_header)
            if name in parsed and parsed[name].value:
                return str(parsed[name].value)
    return None


def _decode_core_records(raw: str) -> list[dict[str, Any]]:
    """Decode independent SignalR Core records from one websocket frame."""
    records: list[dict[str, Any]] = []
    for segment in raw.split(RECORD_SEP):
        segment = segment.strip()
        if not segment:
            continue
        payload = json.loads(segment)
        if isinstance(payload, dict):
            records.append(payload)
    return records


class SignalRLegacyClient:
    """Minimal legacy SignalR client for Formula 1 live timing."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        *,
        auth_header: str | None = None,
        streams: Iterable[str] | None = None,
    ) -> None:
        self._hass = hass
        self._session = session
        self._auth_header = _normalize_auth_header(auth_header)
        self._subscribe_msg = build_subscribe_message(
            include_auth_gated=self._auth_header is not None,
            requested_streams=streams,
        )
        self._ws = None
        self._t0 = dt.datetime.now(dt.UTC)
        self._startup_cutoff = None
        self._heartbeat_task: asyncio.Task | None = None

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to F1 SignalR service")
        params = {"clientProtocol": "1.5", "connectionData": HUB_DATA}
        async with self._session.get(
            NEGOTIATE_URL,
            params=params,
            headers=_authorization_headers(self._auth_header),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = data.get("ConnectionToken")
            cookie = _response_cookie_value(resp, "ARRAffinity")

        if not token:
            raise ConnectionError("F1 SignalR negotiation returned no connection token")

        headers = {
            "User-Agent": "BestHTTP",
            "Accept-Encoding": "gzip,identity",
        }
        if cookie:
            headers["Cookie"] = f"ARRAffinity={cookie}"
        headers.update(_authorization_headers(self._auth_header))

        params = {
            "transport": "webSockets",
            "clientProtocol": "1.5",
            "connectionToken": token,
            "connectionData": HUB_DATA,
        }
        self._ws = await self._session.ws_connect(
            CONNECT_URL, params=params, headers=headers
        )
        await self._ws.send_json(self._subscribe_msg)
        # Renew the subscription every 5 minutes so Azure SignalR
        # inte stänger grupp‑anslutningen (20 min timeout).
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
        self._t0 = dt.datetime.now(dt.UTC)
        self._startup_cutoff = self._t0 - dt.timedelta(seconds=30)
        _LOGGER.debug("SignalR connection established")
        _LOGGER.debug(
            "Subscribed to %s",
            ", ".join(self._subscribe_msg["A"][0]),
        )

    async def ensure_connection(self) -> None:
        """Make one bounded connection attempt.

        LiveBus owns retry policy so normal closes, handshakes and transport
        errors all use the same state machine.
        """
        try:
            async with asyncio.timeout(SIGNALR_CONNECT_TIMEOUT):
                await self.connect()
        except SignalRAuthenticationError:
            raise
        except Exception as err:
            if self._auth_header and _is_authentication_error(err):
                raise SignalRAuthenticationError(
                    "F1 SignalR authorization was rejected"
                ) from err
            raise

    async def messages(self) -> AsyncGenerator[dict]:
        websocket = self._ws
        if websocket is None:
            return
        index = 0
        async for msg in websocket:
            if msg.type == WSMsgType.TEXT:
                payload = None
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    payload = None
                if payload is None:
                    continue
                if (
                    isinstance(payload, dict)
                    and isinstance(payload.get("E"), str)
                    and _is_authentication_close_error(payload.get("E"))
                ):
                    raise SignalRAuthenticationError(
                        "F1 SignalR authorization was rejected"
                    )
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
                    await self._ws.send_json(self._subscribe_msg)
                    _LOGGER.debug("Heartbeat: subscriptions renewed")
                except Exception as exc:  # pylint: disable=broad-except
                    _LOGGER.warning("Heartbeat failed: %s", exc)
                    break
        except asyncio.CancelledError:
            # Normalt vid nedstängning / reconnect
            pass

    async def close(self) -> None:
        if self._heartbeat_task:
            task = self._heartbeat_task
            self._heartbeat_task = None
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def update_streams(self, streams: Iterable[str]) -> None:
        """Replace the active subscription without opening another connection."""
        self._subscribe_msg = build_subscribe_message(
            include_auth_gated=self._auth_header is not None,
            requested_streams=streams,
        )
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_json(self._subscribe_msg)


class SignalRCoreClient:
    """SignalR Core client for Formula 1 live timing (/signalrcore endpoint).

    Translates Core protocol messages (type 1/3/6/7 with \\x1e separator)
    into legacy-format dicts so LiveBus._run() needs no changes.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        session: ClientSession,
        *,
        auth_header: str | None = None,
        streams: Iterable[str] | None = None,
    ) -> None:
        self._hass = hass
        self._session = session
        self._auth_header = _normalize_auth_header(auth_header)
        self._subscribe_msg = build_subscribe_message(
            include_auth_gated=self._auth_header is not None,
            requested_streams=streams,
        )
        self._ws = None
        self._cookie: str | None = None
        self._pending_records: list[dict[str, Any]] = []

    async def connect(self) -> None:
        _LOGGER.debug("Connecting to F1 SignalR Core service")
        negotiate_params = {"negotiateVersion": "1"}

        # Step 1: OPTIONS to obtain AWSALBCORS load-balancer cookie
        try:
            async with self._session.options(
                CORE_NEGOTIATE_URL,
                params=negotiate_params,
                headers=_authorization_headers(self._auth_header),
            ) as resp:
                self._cookie = _response_cookie_value(resp, "AWSALBCORS")
        except Exception:  # noqa: BLE001
            _LOGGER.debug("OPTIONS request failed, continuing without cookie")

        # Step 2: POST negotiate to obtain connectionToken
        headers = _authorization_headers(self._auth_header)
        if self._cookie:
            headers["Cookie"] = f"AWSALBCORS={self._cookie}"
        async with self._session.post(
            CORE_NEGOTIATE_URL, params=negotiate_params, headers=headers
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            token = data.get("connectionToken") or data.get("ConnectionToken", "")

        if not token:
            raise ConnectionError(
                "F1 SignalR Core negotiation returned no connection token"
            )

        # Step 3: WebSocket connect
        ws_headers = _authorization_headers(self._auth_header)
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
            records = _decode_core_records(hs_msg.data)
            if records:
                handshake = records[0]
                if "error" in handshake:
                    if self._auth_header and _is_authentication_close_error(
                        handshake["error"]
                    ):
                        raise SignalRAuthenticationError(
                            "F1 SignalR Core authorization was rejected"
                        )
                    raise ConnectionError(
                        f"SignalR Core handshake error: {handshake['error']}"
                    )
                self._pending_records.extend(records[1:])
        elif hs_msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
            raise ConnectionError("WebSocket closed during handshake")

        # Step 5: Subscribe
        subscribe = {
            "type": 1,
            "target": "Subscribe",
            "arguments": self._subscribe_msg["A"],
            "invocationId": "0",
        }
        await self._ws.send_str(json.dumps(subscribe) + RECORD_SEP)

        _LOGGER.debug("SignalR Core connection established and subscribed")

    async def ensure_connection(self) -> None:
        """Make one bounded connection attempt."""
        try:
            async with asyncio.timeout(SIGNALR_CONNECT_TIMEOUT):
                await self.connect()
        except SignalRAuthenticationError:
            raise
        except Exception as err:
            if self._auth_header and _is_authentication_error(err):
                raise SignalRAuthenticationError(
                    "F1 SignalR Core authorization was rejected"
                ) from err
            raise

    async def messages(self) -> AsyncGenerator[dict]:
        websocket = self._ws
        if websocket is None:
            return
        for payload in self._pending_records:
            if payload.get("type") == 7:
                self._raise_for_close_record(payload)
                return
            translated = await self._translate_record(payload, websocket=websocket)
            if translated is not None:
                yield translated
        self._pending_records.clear()
        async for msg in websocket:
            if msg.type == WSMsgType.TEXT:
                try:
                    records = _decode_core_records(msg.data)
                except json.JSONDecodeError:
                    continue
                for payload in records:
                    if payload.get("type") == 7:
                        self._raise_for_close_record(payload)
                        return
                    translated = await self._translate_record(
                        payload, websocket=websocket
                    )
                    if translated is not None:
                        yield translated
            elif msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                break

    async def _translate_record(
        self, payload: dict[str, Any], *, websocket: Any | None = None
    ) -> dict | None:
        """Translate one Core protocol record to the legacy bus format."""
        msg_type = payload.get("type")
        if msg_type == 1:
            return {
                "M": [
                    {
                        "H": "Streaming",
                        "M": payload.get("target", ""),
                        "A": payload.get("arguments", []),
                    }
                ]
            }
        if msg_type == 3:
            result = payload.get("result")
            return {"R": result} if isinstance(result, dict) else None
        if msg_type == 6:
            active_websocket = websocket or self._ws
            if active_websocket is not None and not active_websocket.closed:
                await active_websocket.send_str(json.dumps({"type": 6}) + RECORD_SEP)
            return None
        return None

    def _raise_for_close_record(self, payload: dict[str, Any]) -> None:
        """Raise for an errored close while allowing a clean close to return."""
        error = payload.get("error", "")
        if self._auth_header and _is_authentication_close_error(error):
            raise SignalRAuthenticationError(
                "F1 SignalR Core authorization was rejected"
            )
        if error:
            raise ConnectionError(f"SignalR Core server closed connection: {error}")

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def update_streams(self, streams: Iterable[str]) -> None:
        """Replace the active Core subscription on the current connection."""
        self._subscribe_msg = build_subscribe_message(
            include_auth_gated=self._auth_header is not None,
            requested_streams=streams,
        )
        if self._ws is None or self._ws.closed:
            return
        subscribe = {
            "type": 1,
            "target": "Subscribe",
            "arguments": self._subscribe_msg["A"],
            "invocationId": str(self._monotonic_invocation_id()),
        }
        await self._ws.send_str(json.dumps(subscribe) + RECORD_SEP)

    def _monotonic_invocation_id(self) -> int:
        """Return a connection-local invocation identifier."""
        value = getattr(self, "_next_invocation_id", 1)
        self._next_invocation_id = value + 1
        return value


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
        auth_header: str | None = None,
        auth_failed_callback: Callable[[], None] | None = None,
        requested_streams: Iterable[str] | None = None,
        provider_registry: ProviderRegistry | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        jitter_source: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._hass = hass
        self._session = session
        self._transport_factory = transport_factory
        self._auth_header = _normalize_auth_header(auth_header)
        self._auth_enabled = self._auth_header is not None
        self._auth_failed_callback = auth_failed_callback
        self._requested_streams = (
            frozenset(requested_streams)
            if requested_streams is not None
            else frozenset(
                build_live_subscribe_streams(include_auth_gated=self._auth_enabled)
            )
        )
        self._provider_registry = provider_registry or ProviderRegistry()
        self._auth_failed_reported = False
        self._monotonic = monotonic
        self._jitter_source = jitter_source
        self._client: LiveTransport | None = None
        self._task: asyncio.Task | None = None
        self._subs: dict[str, list[Callable[[StreamPayload], None]]] = {}
        self._running = False
        # Lightweight per-stream counters for DEBUG summaries
        self._cnt: dict[str, int] = {}
        self._stream_frames: dict[str, int] = {}
        self._stream_last_keys: dict[str, list[str] | None] = {}
        self._last_ts: dict[str, float] = {}
        self._last_logged: float = self._monotonic()
        self._log_interval: float = 10.0  # seconds
        # Cache last payload per stream so new subscribers receive latest snapshot immediately
        self._last_payload: dict[str, StreamPayload] = {}
        self._expect_heartbeat = False
        self._last_heartbeat_at: float | None = None
        self._heartbeat_guard: asyncio.Task | None = None
        self._heartbeat_timeout = 45.0
        self._heartbeat_check_interval = 5.0
        self._connection_state = LiveConnectionState.STOPPED
        self._retry_delay: float = 0
        self._outage_logged = False
        self._reset_retry_delay()

    @property
    def auth_enabled(self) -> bool:
        """Return whether the live connection is currently using auth."""
        return self._auth_enabled

    @property
    def connection_state(self) -> LiveConnectionState:
        """Return the current live transport lifecycle state."""
        return self._connection_state

    @property
    def requested_streams(self) -> frozenset[str]:
        """Return the declared stream demand for this bus."""
        return self._requested_streams

    @property
    def active_streams(self) -> frozenset[str]:
        """Return streams supported by the current live transport capability."""
        if self._transport_factory is not None:
            supported = frozenset(
                (*PUBLIC_LIVE_STREAMS, *AUTH_GATED_LIVE_STREAMS, *REPLAY_ONLY_STREAMS)
            )
            return self._requested_streams & supported
        return frozenset(
            build_live_subscribe_streams(
                include_auth_gated=self._auth_enabled,
                requested_streams=self._requested_streams,
            )
        )

    def subscribe(
        self, stream: str, callback: Callable[[StreamPayload], None]
    ) -> Callable[[], None]:
        lst = self._subs.setdefault(stream, [])
        lst.append(callback)

        # Immediately replay last payload for this stream (if available)
        with suppress(Exception):
            if stream in self._last_payload:
                data = self._last_payload.get(stream)
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
        if not self.active_streams and self._transport_factory is None:
            _LOGGER.debug("LiveBus start skipped because no streams are requested")
            return
        self._running = True
        self._connection_state = LiveConnectionState.CONNECTING
        self._reset_retry_delay()
        _LOGGER.info(
            "LiveBus starting (transport=%s)",
            "custom" if self._transport_factory else "native",
        )
        self._task = self._hass.loop.create_task(self._run())
        if self._heartbeat_guard is None or self._heartbeat_guard.done():
            self._heartbeat_guard = self._hass.loop.create_task(
                self._monitor_heartbeat()
            )

    async def _run(self) -> None:
        try:
            while self._running:
                retry_reason = "connection closed"
                self._connection_state = LiveConnectionState.CONNECTING
                client = self._create_client()
                self._client = client
                try:
                    if self._expect_heartbeat:
                        self._last_heartbeat_at = self._monotonic()
                    await client.ensure_connection()
                    async for payload in client.messages():
                        if self._process_payload(payload):
                            self._mark_connection_live()
                except SignalRAuthenticationError:
                    retry_reason = "authorization was rejected"
                    if self._auth_enabled:
                        self._auth_enabled = False
                        self._connection_state = LiveConnectionState.AUTH_LIMITED
                        if (
                            self._auth_failed_callback is not None
                            and not self._auth_failed_reported
                        ):
                            self._auth_failed_reported = True
                            self._auth_failed_callback()
                except TimeoutError:
                    retry_reason = "connection attempt timed out"
                except Exception as err:  # noqa: BLE001
                    retry_reason = self._retry_reason(err)
                finally:
                    if self._client is client:
                        self._client = None
                    try:
                        await client.close()
                    except Exception as err:  # noqa: BLE001
                        retry_reason = f"cleanup failed: {type(err).__name__}"

                self._maybe_log_summary()
                if self._running:
                    await self._wait_before_retry(retry_reason)
        except asyncio.CancelledError:
            raise
        finally:
            if self._task is None or self._task is asyncio.current_task():
                self._connection_state = LiveConnectionState.STOPPED

    def _process_payload(self, payload: Any) -> bool:
        """Dispatch one transport payload and report meaningful activity."""
        if not isinstance(payload, dict):
            return False
        meaningful = False
        msgs = payload.get("M")
        if isinstance(msgs, list):
            for hub_msg in msgs:
                if not isinstance(hub_msg, dict) or hub_msg.get("M") != "feed":
                    continue
                args = hub_msg.get("A", [])
                if not isinstance(args, list) or len(args) < 2:
                    continue
                stream, data = args[0], args[1]
                if not isinstance(stream, str) or data is None:
                    continue
                self._dispatch(stream, data)
                meaningful = True
        result = payload.get("R")
        if isinstance(result, dict):
            for stream, data in result.items():
                if not isinstance(stream, str) or data is None:
                    continue
                self._dispatch(stream, data)
                meaningful = True
        return meaningful

    def _mark_connection_live(self) -> None:
        """Mark a connection healthy only after receiving usable stream data."""
        if self._connection_state is LiveConnectionState.LIVE:
            return
        self._connection_state = LiveConnectionState.LIVE
        self._reset_retry_delay()
        if self._outage_logged:
            _LOGGER.info("Live timing connection recovered")
            self._outage_logged = False

    def _reset_retry_delay(self) -> None:
        from .const import FAST_RETRY_SEC

        self._retry_delay = float(FAST_RETRY_SEC)

    async def _wait_before_retry(self, reason: str) -> None:
        """Apply capped exponential backoff with bounded jitter."""
        from .const import BACK_OFF_FACTOR, MAX_RETRY_SEC

        self._connection_state = LiveConnectionState.RETRYING
        delay = self._jitter_source(
            self._retry_delay * (1 - SIGNALR_BACKOFF_JITTER),
            self._retry_delay * (1 + SIGNALR_BACKOFF_JITTER),
        )
        if reason == "connection closed":
            _LOGGER.debug(
                "Live timing connection closed cleanly; reconnecting in %.1f seconds",
                delay,
            )
        elif not self._outage_logged:
            _LOGGER.warning(
                "Live timing connection unavailable (%s); retrying in %.1f seconds",
                reason,
                delay,
            )
            self._outage_logged = True
        else:
            _LOGGER.debug(
                "Live timing reconnect still pending (%s); retrying in %.1f seconds",
                reason,
                delay,
            )
        self._retry_delay = min(
            self._retry_delay * BACK_OFF_FACTOR, float(MAX_RETRY_SEC)
        )
        await asyncio.sleep(delay)

    @staticmethod
    def _retry_reason(err: Exception) -> str:
        """Return a stable non-sensitive reconnect reason."""
        if "replay" in str(err).lower():
            return "replay transport closed"
        return type(err).__name__

    def _dispatch(self, stream: str, data: StreamPayload) -> None:
        with suppress(Exception):
            provider = "replay" if self._transport_factory is not None else "f1_live"
            data = self._provider_registry.normalize(provider, stream, data).payload
            # Update counters
            self._cnt[stream] = self._cnt.get(stream, 0) + 1
            self._stream_frames[stream] = self._stream_frames.get(stream, 0) + 1
            now = self._monotonic()
            self._last_ts[stream] = now
            if isinstance(data, dict):
                self._stream_last_keys[stream] = list(data.keys())[:10]
            if stream == "Heartbeat":
                self._last_heartbeat_at = now
            # Cache last payload for new subscribers
            if data is not None:
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
        now = self._monotonic()
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
        # Detach this generation before awaiting transport cleanup. A replay
        # takeover may start another generation while the old client closes.
        task, self._task = self._task, None
        heartbeat_guard, self._heartbeat_guard = self._heartbeat_guard, None
        client, self._client = self._client, None
        self._running = False
        self._connection_state = LiveConnectionState.STOPPED
        _LOGGER.info("LiveBus shutting down")
        if task:
            task.cancel()
        if heartbeat_guard:
            heartbeat_guard.cancel()
        if task:
            with suppress(asyncio.CancelledError):
                await task
        if heartbeat_guard:
            with suppress(asyncio.CancelledError):
                await heartbeat_guard
        if client:
            try:
                await client.close()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Live timing cleanup failed during shutdown: %s", err)

    def _create_client(self) -> LiveTransport:
        if callable(self._transport_factory):
            return self._transport_factory()
        from .const import SIGNALR_USE_CORE

        if SIGNALR_USE_CORE:
            return SignalRCoreClient(
                self._hass,
                self._session,
                auth_header=self._auth_header if self._auth_enabled else None,
                streams=self._requested_streams,
            )
        return SignalRLegacyClient(
            self._hass,
            self._session,
            auth_header=self._auth_header if self._auth_enabled else None,
            streams=self._requested_streams,
        )

    async def async_update_streams(self, streams: Iterable[str]) -> None:
        """Apply a changed demand set without creating a second transport."""
        requested = frozenset(str(stream) for stream in streams if str(stream))
        if requested == self._requested_streams:
            return
        self._requested_streams = requested
        client = self._client
        if client is None:
            return
        update_streams = getattr(client, "update_streams", None)
        if callable(update_streams):
            await update_streams(self._requested_streams)
            return
        await client.close()

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
                ages = [age for age in (hb_age, activity_age) if age is not None]
                effective_age = min(ages) if ages else None
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
                client = self._client
                if client:
                    try:
                        await client.close()
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.debug(
                            "Live timing cleanup failed after inactivity: %s", err
                        )
                    if self._client is client:
                        self._client = None

    def set_heartbeat_expectation(self, enabled: bool) -> None:
        self._expect_heartbeat = bool(enabled)
        if enabled:
            if self._last_heartbeat_at is None:
                self._last_heartbeat_at = self._monotonic()
            _LOGGER.info("Heartbeat guard ENABLED")
        else:
            self._last_heartbeat_at = None
            _LOGGER.info("Heartbeat guard DISABLED")

    def last_heartbeat_age(self) -> float | None:
        if self._last_heartbeat_at is None:
            return None
        return self._monotonic() - self._last_heartbeat_at

    def last_stream_activity_age(
        self, streams: Iterable[str] | None = None
    ) -> float | None:
        """Return age in seconds for the most recent payload among given streams."""
        if not self._last_ts:
            return None
        now = self._monotonic()
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
        now = self._monotonic()
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
        self.reset_for_replay()

        # For replay mode (transport_factory provided), always start the bus
        # For restoring to live (transport_factory=None), only restart if it was running
        # (let LiveSessionSupervisor handle normal reconnection)
        if transport_factory is not None:
            _LOGGER.info("Starting LiveBus with replay transport")
            await self.start()
        elif was_running:
            _LOGGER.info("Restarting LiveBus with live transport")
            await self.start()

    def reset_for_replay(self) -> None:
        """Clear retained frames when live/replay session ownership changes."""
        self._last_payload.clear()
        self._cnt.clear()
        self._stream_frames.clear()
        self._stream_last_keys.clear()
        self._last_ts.clear()

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
