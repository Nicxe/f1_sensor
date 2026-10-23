"""Authenticated access to Formula 1's static timing archive."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Collection
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientSession

from .helpers import normalize_live_timing_auth_header

ARCHIVE_HOST = "livetiming.formula1.com"
ARCHIVE_PATH_PREFIX = "/static/"
ARCHIVE_AUTH_REQUIRED_MESSAGE = (
    "A Formula 1 account with a valid token is required for replay and archive data"
)
ARCHIVE_AUTH_FAILURE_STATUSES = frozenset({401})


class F1ArchiveAuthenticationRequired(RuntimeError):
    """Raised when an archive operation has no usable F1TV authorization."""


class F1ArchiveResponseError(RuntimeError):
    """Raised when an archive response cannot be returned safely."""


class _ArchiveRequestContext:
    """Observe one aiohttp response before returning it to the caller."""

    def __init__(self, request_context: Any, client: F1ArchiveClient) -> None:
        self._request_context = request_context
        self._client = client

    async def __aenter__(self):
        response = await self._request_context.__aenter__()
        if response.status in ARCHIVE_AUTH_FAILURE_STATUSES:
            self._client.mark_auth_rejected()
        return response

    async def __aexit__(self, exc_type, exc, traceback):
        return await self._request_context.__aexit__(exc_type, exc, traceback)


class F1ArchiveClient:
    """Send F1TV authorization only to the official static archive."""

    def __init__(
        self,
        session: ClientSession,
        auth_header: str | None,
        *,
        auth_failed_callback: Callable[[], None] | None = None,
    ) -> None:
        self._session = session
        self._auth_header = normalize_live_timing_auth_header(auth_header)
        self._auth_failed_callback = auth_failed_callback
        self._auth_rejected = False
        self._auth_failed_reported = False

    @property
    def authenticated(self) -> bool:
        """Return whether archive requests can currently use authorization."""
        return bool(self._auth_header and not self._auth_rejected)

    def set_auth_failed_callback(self, callback: Callable[[], None] | None) -> None:
        """Set the entry-owned handler used when Formula 1 rejects the token."""
        self._auth_failed_callback = callback

    def mark_auth_rejected(self) -> None:
        """Stop using a rejected token and report the failure once."""
        self._auth_rejected = True
        if self._auth_failed_reported or self._auth_failed_callback is None:
            return
        self._auth_failed_reported = True
        self._auth_failed_callback()

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(str(url))
        if (
            parsed.scheme != "https"
            or parsed.hostname != ARCHIVE_HOST
            or not parsed.path.startswith(ARCHIVE_PATH_PREFIX)
        ):
            raise ValueError("Invalid Formula 1 archive URL")

    def _request(self, method: str, url: str, **kwargs) -> _ArchiveRequestContext:
        self._validate_url(url)
        if not self.authenticated:
            raise F1ArchiveAuthenticationRequired(ARCHIVE_AUTH_REQUIRED_MESSAGE)
        headers = dict(kwargs.pop("headers", None) or {})
        headers["Authorization"] = self._auth_header
        request = getattr(self._session, method.lower())(
            url,
            headers=headers,
            **kwargs,
        )
        return _ArchiveRequestContext(request, self)

    def get(self, url: str, **kwargs) -> _ArchiveRequestContext:
        """Return an authenticated GET request context."""
        return self._request("GET", url, **kwargs)

    def head(self, url: str, **kwargs) -> _ArchiveRequestContext:
        """Return an authenticated HEAD request context."""
        return self._request("HEAD", url, **kwargs)

    async def async_get_bytes(
        self,
        url: str,
        *,
        timeout_seconds: float,
        max_bytes: int,
        allowed_content_types: Collection[str] | None = None,
        allow_redirects: bool = False,
    ) -> tuple[bytes, str]:
        """Download a bounded archive resource and return its media type."""
        async with asyncio.timeout(timeout_seconds):
            async with self.get(url, allow_redirects=allow_redirects) as response:
                if response.status != 200:
                    raise F1ArchiveResponseError(
                        f"Formula 1 archive request failed with status {response.status}"
                    )
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                if allowed_content_types and content_type not in allowed_content_types:
                    raise F1ArchiveResponseError(
                        "Formula 1 archive returned an unexpected content type"
                    )
                content_length = response.content_length
                if content_length is not None and content_length > max_bytes:
                    raise ValueError("Formula 1 archive response is too large")
                content = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ValueError("Formula 1 archive response is too large")
        if not content:
            raise F1ArchiveResponseError("Formula 1 archive response is empty")
        return bytes(content), content_type
