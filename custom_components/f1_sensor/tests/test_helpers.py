from __future__ import annotations

import asyncio
from types import TracebackType
from unittest.mock import MagicMock

import pytest

from custom_components.f1_sensor.helpers import fetch_json, fetch_text


class _TimeoutResponse:
    async def __aenter__(self):
        raise TimeoutError

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        del exc_type, exc, tb
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_json, fetch_text])
async def test_http_fetch_helpers_propagate_timeout(hass, fetcher) -> None:
    session = MagicMock()
    session.headers = {"User-Agent": "ua"}
    session.get = MagicMock(return_value=_TimeoutResponse())
    inflight = {}

    with pytest.raises(TimeoutError):
        await fetcher(
            hass,
            session,
            "https://example.com/data",
            cache={},
            inflight=inflight,
            persist_map={},
        )

    session.get.assert_called_once()
    future = next(iter(inflight.values()))
    with pytest.raises(TimeoutError):
        await future
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert inflight == {}
