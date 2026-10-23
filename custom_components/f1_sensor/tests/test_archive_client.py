"""Regression tests for authenticated Formula 1 archive access."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.archive import (
    F1ArchiveAuthenticationRequired,
    F1ArchiveClient,
    F1ArchiveResponseError,
)


class _Content:
    def __init__(self, chunks: tuple[bytes, ...] = (b"one", b"two")) -> None:
        self._chunks = chunks

    async def iter_chunked(self, _size: int):
        for chunk in self._chunks:
            yield chunk


class _Response:
    def __init__(
        self,
        status: int = 200,
        *,
        content_type: str = "application/json",
        chunks: tuple[bytes, ...] = (b"one", b"two"),
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.content_length = sum(len(chunk) for chunk in chunks)
        self.content = _Content(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def __init__(self, response: _Response | None = None) -> None:
        self.response = response or _Response()
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.response

    def head(self, url: str, **kwargs):
        self.calls.append(("HEAD", url, kwargs))
        return self.response


@pytest.mark.asyncio
async def test_archive_client_requires_auth_and_never_sends_it_to_other_hosts() -> None:
    unauthenticated = F1ArchiveClient(_Session(), "")

    with pytest.raises(F1ArchiveAuthenticationRequired, match="Formula 1 account"):
        unauthenticated.get("https://livetiming.formula1.com/static/2026/Index.json")

    authenticated = F1ArchiveClient(_Session(), "Bearer secret")
    with pytest.raises(ValueError, match="archive URL"):
        authenticated.get("https://example.com/static/2026/Index.json")


@pytest.mark.asyncio
async def test_archive_client_adds_auth_to_get_and_head_requests() -> None:
    session = _Session()
    client = F1ArchiveClient(session, "Authorization: Bearer secret")
    url = "https://livetiming.formula1.com/static/2026/Index.json"

    async with client.get(url, headers={"Accept": "application/json"}):
        pass
    async with client.head(url):
        pass

    assert session.calls == [
        (
            "GET",
            url,
            {
                "headers": {
                    "Accept": "application/json",
                    "Authorization": "Bearer secret",
                }
            },
        ),
        ("HEAD", url, {"headers": {"Authorization": "Bearer secret"}}),
    ]


@pytest.mark.asyncio
async def test_archive_client_invalidates_rejected_auth_once() -> None:
    callback = Mock()
    session = _Session(_Response(401))
    client = F1ArchiveClient(
        session,
        "Bearer secret",
        auth_failed_callback=callback,
    )
    url = "https://livetiming.formula1.com/static/2026/Index.json"

    async with client.get(url) as response:
        assert response.status == 401

    callback.assert_called_once_with()
    assert client.authenticated is False
    with pytest.raises(F1ArchiveAuthenticationRequired):
        client.get(url)

    client.mark_auth_rejected()
    callback.assert_called_once_with()


def test_archive_client_reports_rejection_after_callback_is_attached() -> None:
    client = F1ArchiveClient(_Session(), "Bearer secret")
    callback = Mock()

    client.mark_auth_rejected()
    client.set_auth_failed_callback(callback)
    client.mark_auth_rejected()

    callback.assert_called_once_with()


@pytest.mark.asyncio
async def test_archive_client_downloads_bounded_audio() -> None:
    session = _Session(
        _Response(200, content_type="audio/mpeg", chunks=(b"ID3", b"radio"))
    )
    client = F1ArchiveClient(session, "Bearer secret")
    url = "https://livetiming.formula1.com/static/2026/race/TeamRadio/clip.mp3"

    audio, content_type = await client.async_get_bytes(
        url,
        timeout_seconds=5,
        max_bytes=32,
        allowed_content_types={"audio/mpeg"},
    )

    assert audio == b"ID3radio"
    assert content_type == "audio/mpeg"

    session.response.content_length = 33
    with pytest.raises(ValueError, match="too large"):
        await client.async_get_bytes(
            url,
            timeout_seconds=5,
            max_bytes=32,
            allowed_content_types={"audio/mpeg"},
        )


@pytest.mark.asyncio
async def test_archive_client_rejects_invalid_archive_responses() -> None:
    url = "https://livetiming.formula1.com/static/2026/race/TeamRadio/clip.mp3"

    for response, error, message, max_bytes in (
        (_Response(503), F1ArchiveResponseError, "status 503", 32),
        (
            _Response(200, content_type="text/html"),
            F1ArchiveResponseError,
            "unexpected content type",
            32,
        ),
        (
            _Response(200, content_type="audio/mpeg", chunks=(b"123", b"456")),
            ValueError,
            "too large",
            5,
        ),
        (
            _Response(200, content_type="audio/mpeg", chunks=()),
            F1ArchiveResponseError,
            "empty",
            32,
        ),
    ):
        if message == "too large":
            response.content_length = None
        client = F1ArchiveClient(_Session(response), "Bearer secret")
        with pytest.raises(error, match=message):
            await client.async_get_bytes(
                url,
                timeout_seconds=5,
                max_bytes=max_bytes,
                allowed_content_types={"audio/mpeg"},
            )
