"""Shared, policy-compliant transport for the public Jolpica API."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
import logging
import math
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from aiohttp import ClientError, ClientResponseError
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

JOLPICA_CLIENT_KEY = "__jolpica_client__"
JOLPICA_HOST = "api.jolpi.ca"
JOLPICA_ORIGIN = f"https://{JOLPICA_HOST}"

_SECOND_LIMIT = 3
_HOUR_LIMIT = 450
_SECOND_WINDOW = 1.0
_HOUR_WINDOW = 3600.0
_MAX_QUEUE_WAIT = 5.0
_MAX_SERVER_RETRY_DELAY = 10.0
_MAX_BACKOFF = 60.0
_STORE_VERSION = 1
_STORE_KEY = f"{DOMAIN}_jolpica_transport"
_SAVE_DELAY = 1.0
_USER_AGENT_PATTERN = re.compile(
    r"^HomeAssistantF1Sensor/[A-Za-z0-9][A-Za-z0-9._+-]* "
    r"HomeAssistant/[A-Za-z0-9][A-Za-z0-9._+-]*$"
)


class JolpicaError(Exception):
    """Base class for Jolpica transport failures."""


class JolpicaConfigurationError(JolpicaError):
    """The client cannot safely make a Jolpica request."""


class JolpicaInvalidRequestError(JolpicaError):
    """A request violates the Jolpica transport policy."""


class JolpicaTemporaryError(JolpicaError):
    """A temporary problem prevented a request."""


class JolpicaRateLimitError(JolpicaTemporaryError):
    """A local or server-side rate limit prevented a request."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        source: str,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.source = source


class JolpicaRouteNotFoundError(JolpicaError):
    """The requested Jolpica route does not exist."""

    status = 404


class JolpicaHTTPError(JolpicaError):
    """Jolpica returned an HTTP error other than a rate limit."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class JolpicaResponseError(JolpicaError):
    """Jolpica returned a response that could not be decoded."""


class JolpicaClient:
    """Apply shared identity, traffic, retry, and lifecycle policy."""

    def __init__(
        self,
        hass,
        session,
        user_agent: str,
        *,
        max_queue_wait: float = _MAX_QUEUE_WAIT,
    ) -> None:
        self._hass = hass
        self._session = session
        self._user_agent = str(user_agent or "").strip()
        self._max_queue_wait = max(0.0, float(max_queue_wait))
        self._store = Store(hass, _STORE_VERSION, _STORE_KEY)

        self._second_requests: deque[float] = deque()
        self._hour_requests: deque[float] = deque()
        self._inflight: dict[str, asyncio.Task[str]] = {}
        self._limiter_lock = asyncio.Lock()
        self._inflight_lock = asyncio.Lock()

        self._cooldown_until = 0.0
        self._latest_429: float | None = None
        self._backoff_step = 0
        self._blocked_requests = 0
        self._queue_length = 0
        self._save_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._closed = False
        self._limit_problem_active = False
        self._cooldown_problem_active = False

    async def async_initialize(self) -> None:
        """Load persisted hourly request budget and active cooldown."""
        if self._initialized:
            return
        if not self._valid_user_agent:
            raise JolpicaConfigurationError(
                "A valid integration-specific User-Agent is required"
            )

        stored: Any = None
        with suppress(Exception):
            stored = await self._store.async_load()
        if isinstance(stored, dict):
            now = time.time()
            timestamps = stored.get("request_timestamps")
            if isinstance(timestamps, list):
                for raw_timestamp in timestamps:
                    try:
                        timestamp = float(raw_timestamp)
                    except (TypeError, ValueError):
                        continue
                    if now - _HOUR_WINDOW < timestamp <= now + 1:
                        self._hour_requests.append(timestamp)

            try:
                cooldown_until = float(stored.get("cooldown_until", 0.0))
            except (TypeError, ValueError):
                cooldown_until = 0.0
            if cooldown_until > now:
                self._cooldown_until = cooldown_until

            try:
                backoff_step = int(stored.get("backoff_step", 0))
            except (TypeError, ValueError):
                backoff_step = 0
            self._backoff_step = max(0, min(backoff_step, 6))

            try:
                latest_429 = float(stored.get("latest_429", 0.0))
            except (TypeError, ValueError):
                latest_429 = 0.0
            self._latest_429 = latest_429 or None

        self._initialized = True

    async def async_get_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
        retry_on_rate_limit: bool = True,
    ) -> str:
        """Return text from a policy-compliant, coalesced Jolpica GET."""
        self._ensure_ready()
        self._validate_request(url, params)
        request_key = (
            f"retry_429={bool(retry_on_rate_limit)}:{self._request_key(url, params)}"
        )

        async with self._inflight_lock:
            task = self._inflight.get(request_key)
            if task is None or task.done():
                task = self._hass.loop.create_task(
                    self._async_request_text(
                        url,
                        params=params,
                        timeout=timeout,
                        retry_on_rate_limit=retry_on_rate_limit,
                    )
                )
                self._inflight[request_key] = task
                task.add_done_callback(
                    lambda completed, key=request_key: self._remove_inflight(
                        key, completed
                    )
                )
        return await asyncio.shield(task)

    async def async_get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        timeout: float = 30.0,
        retry_on_rate_limit: bool = True,
    ) -> Any:
        """Return decoded JSON from a policy-compliant Jolpica GET."""
        text = await self.async_get_text(
            url,
            params=params,
            timeout=timeout,
            retry_on_rate_limit=retry_on_rate_limit,
        )
        try:
            return json.loads(text.lstrip("\ufeff"))
        except (TypeError, ValueError) as err:
            raise JolpicaResponseError("Jolpica returned invalid JSON") from err

    def diagnostics(self) -> dict[str, Any]:
        """Return safe runtime diagnostics without URLs or headers."""
        now_mono = time.monotonic()
        now_wall = time.time()
        self._prune_requests(now_mono, now_wall)
        cache_entries = 0
        domain_data = self._hass.data.get(DOMAIN)
        if isinstance(domain_data, dict):
            for runtime in domain_data.values():
                if not isinstance(runtime, dict):
                    continue
                cache = runtime.get("http_cache")
                if isinstance(cache, dict):
                    cache_entries += len(cache)
        latest_429 = None
        if self._latest_429 is not None:
            latest_429 = datetime.fromtimestamp(self._latest_429, tz=UTC).isoformat()
        return {
            "user_agent_configured": self._valid_user_agent,
            "second_limit": _SECOND_LIMIT,
            "hour_limit": _HOUR_LIMIT,
            "max_queue_wait_seconds": self._max_queue_wait,
            "requests_last_second": len(self._second_requests),
            "requests_last_hour": len(self._hour_requests),
            "queue_length": self._queue_length,
            "blocked_requests": self._blocked_requests,
            "cooldown_remaining_seconds": max(
                0.0, round(self._cooldown_until - now_wall, 3)
            ),
            "latest_429": latest_429,
            "cache_entries": cache_entries,
            "inflight_requests": len(self._inflight),
        }

    async def async_close(self) -> None:
        """Cancel owned tasks and flush limiter state on normal shutdown."""
        if self._closed:
            return
        self._closed = True

        tasks = tuple(self._inflight.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._inflight.clear()

        if self._save_task is not None and not self._save_task.done():
            self._save_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._save_task
        with suppress(Exception):
            await self._store.async_save(self._storage_payload())

    @property
    def _valid_user_agent(self) -> bool:
        return bool(_USER_AGENT_PATTERN.fullmatch(self._user_agent))

    def _ensure_ready(self) -> None:
        if not self._initialized:
            raise JolpicaConfigurationError(
                "Jolpica client must be initialized before use"
            )
        if self._closed:
            raise JolpicaConfigurationError("Jolpica client is closed")
        if not self._valid_user_agent:
            raise JolpicaConfigurationError(
                "A valid integration-specific User-Agent is required"
            )

    @staticmethod
    def _validate_request(url: str, params: Mapping[str, Any] | None) -> None:
        parsed = urlsplit(str(url))
        if (
            parsed.scheme != "https"
            or parsed.netloc != JOLPICA_HOST
            or not parsed.path.startswith("/")
        ):
            raise JolpicaInvalidRequestError(
                "Only the canonical Jolpica HTTPS origin is allowed"
            )

        query = parse_qs(parsed.query, keep_blank_values=True)
        if params:
            for key, value in params.items():
                values = value if isinstance(value, (list, tuple)) else (value,)
                query.setdefault(str(key), []).extend(str(item) for item in values)
        for raw_limit in query.get("limit", []):
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError) as err:
                raise JolpicaInvalidRequestError(
                    "Jolpica limit must be an integer"
                ) from err
            if not 1 <= limit <= 100:
                raise JolpicaInvalidRequestError(
                    "Jolpica limit must be between 1 and 100"
                )

    @staticmethod
    def _request_key(url: str, params: Mapping[str, Any] | None) -> str:
        if not params:
            return url
        normalized: list[tuple[str, str]] = []
        for key, value in params.items():
            values = value if isinstance(value, (list, tuple)) else (value,)
            normalized.extend((str(key), str(item)) for item in values)
        return f"{url}?{urlencode(sorted(normalized))}"

    async def _async_request_text(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None,
        timeout: float,
        retry_on_rate_limit: bool = True,
    ) -> str:
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise JolpicaInvalidRequestError("Request timeout must be positive")
        deadline = time.monotonic() + timeout
        retry_number = 0

        while True:
            await self._async_acquire_slot(deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JolpicaTemporaryError("Jolpica request budget expired")

            try:
                async with asyncio.timeout(remaining):
                    async with self._session.get(
                        url,
                        params=params,
                        headers={"User-Agent": self._user_agent},
                        allow_redirects=False,
                    ) as response:
                        try:
                            response.raise_for_status()
                        except ClientResponseError as err:
                            if response.status == 429:
                                retry_after = self._record_server_limit(
                                    response.headers.get("Retry-After")
                                )
                                if (
                                    retry_on_rate_limit
                                    and retry_number == 0
                                    and retry_after <= _MAX_SERVER_RETRY_DELAY
                                    and retry_after < deadline - time.monotonic()
                                ):
                                    retry_number += 1
                                    if retry_after > 0:
                                        await asyncio.sleep(retry_after)
                                    continue
                                raise JolpicaRateLimitError(
                                    "Jolpica rate limit reached",
                                    retry_after=retry_after,
                                    source="server",
                                ) from err
                            if response.status == 404:
                                raise JolpicaRouteNotFoundError(
                                    "Jolpica route was not found"
                                ) from err
                            raise JolpicaHTTPError(
                                response.status,
                                f"Jolpica returned HTTP {response.status}",
                            ) from err
                        if not 200 <= response.status < 300:
                            raise JolpicaHTTPError(
                                response.status,
                                f"Jolpica returned HTTP {response.status}",
                            )
                        text = await response.text()
            except TimeoutError as err:
                raise JolpicaTemporaryError("Jolpica request timed out") from err
            except ClientError as err:
                raise JolpicaTemporaryError("Jolpica network request failed") from err

            self._record_success()
            return text

    async def _async_acquire_slot(self, deadline: float) -> None:
        queue_deadline = time.monotonic() + self._max_queue_wait
        self._queue_length += 1
        try:
            while True:
                async with self._limiter_lock:
                    now_mono = time.monotonic()
                    now_wall = time.time()
                    self._prune_requests(now_mono, now_wall)

                    cooldown_delay = max(0.0, self._cooldown_until - now_wall)
                    second_delay = 0.0
                    if len(self._second_requests) >= _SECOND_LIMIT:
                        second_delay = max(
                            0.0,
                            self._second_requests[0] + _SECOND_WINDOW - now_mono,
                        )
                    hour_delay = 0.0
                    if len(self._hour_requests) >= _HOUR_LIMIT:
                        hour_delay = max(
                            0.0,
                            self._hour_requests[0] + _HOUR_WINDOW - now_wall,
                        )
                    delay = max(cooldown_delay, second_delay, hour_delay)
                    remaining = deadline - now_mono

                    if delay <= 0:
                        self._second_requests.append(now_mono)
                        self._hour_requests.append(now_wall)
                        self._schedule_save()
                        if self._limit_problem_active:
                            _LOGGER.info("Jolpica request limiter recovered")
                            self._limit_problem_active = False
                        return

                    if delay > queue_deadline - now_mono or delay >= remaining:
                        self._blocked_requests += 1
                        if not self._limit_problem_active:
                            _LOGGER.warning(
                                "Jolpica request deferred by shared traffic limits"
                            )
                            self._limit_problem_active = True
                        source = (
                            "server"
                            if cooldown_delay >= max(second_delay, hour_delay)
                            else "local"
                        )
                        raise JolpicaRateLimitError(
                            "Jolpica request cannot run within the local wait budget",
                            retry_after=delay,
                            source=source,
                        )
                await asyncio.sleep(delay)
        finally:
            self._queue_length -= 1

    def _record_server_limit(self, raw_retry_after: str | None) -> float:
        now = time.time()
        retry_after = self._parse_retry_after(raw_retry_after, now=now)
        if retry_after is None:
            retry_after = min(2**self._backoff_step, _MAX_BACKOFF)
            self._backoff_step = min(self._backoff_step + 1, 6)
        self._cooldown_until = max(self._cooldown_until, now + retry_after)
        self._latest_429 = now
        self._schedule_save()
        if not self._cooldown_problem_active:
            _LOGGER.warning("Jolpica server cooldown activated")
            self._cooldown_problem_active = True
        return retry_after

    def _record_success(self) -> None:
        self._backoff_step = 0
        if self._cooldown_until <= time.time():
            self._cooldown_until = 0.0
            if self._cooldown_problem_active:
                _LOGGER.info("Jolpica server cooldown recovered")
                self._cooldown_problem_active = False
        self._schedule_save()

    @staticmethod
    def _parse_retry_after(raw_value: str | None, *, now: float) -> float | None:
        if raw_value is None:
            return None
        value = str(raw_value).strip()
        if not value:
            return None
        try:
            delay = float(value)
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            delay = parsed.timestamp() - now
        if not math.isfinite(delay):
            return None
        return max(0.0, delay)

    def _prune_requests(self, now_mono: float, now_wall: float) -> None:
        while (
            self._second_requests
            and self._second_requests[0] <= now_mono - _SECOND_WINDOW
        ):
            self._second_requests.popleft()
        while self._hour_requests and self._hour_requests[0] <= now_wall - _HOUR_WINDOW:
            self._hour_requests.popleft()

    def _remove_inflight(self, request_key: str, completed: asyncio.Task[str]) -> None:
        if self._inflight.get(request_key) is completed:
            self._inflight.pop(request_key, None)
        with suppress(asyncio.CancelledError, Exception):
            completed.exception()

    def _schedule_save(self) -> None:
        if self._closed or (self._save_task is not None and not self._save_task.done()):
            return

        async def _save_later() -> None:
            await asyncio.sleep(_SAVE_DELAY)
            with suppress(Exception):
                await self._store.async_save(self._storage_payload())

        self._save_task = self._hass.loop.create_task(_save_later())

    def _storage_payload(self) -> dict[str, Any]:
        return {
            "request_timestamps": list(self._hour_requests),
            "cooldown_until": self._cooldown_until,
            "backoff_step": self._backoff_step,
            "latest_429": self._latest_429,
        }
