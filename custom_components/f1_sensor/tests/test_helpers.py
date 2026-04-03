from __future__ import annotations

import asyncio
import gc
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.f1_sensor.__init__ import FiaDocumentsCoordinator
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


def _future_race_payload() -> dict:
    return {
        "MRData": {
            "RaceTable": {
                "Races": [
                    {
                        "season": "2026",
                        "round": "1",
                        "raceName": "Australian Grand Prix",
                        "date": "2026-03-15",
                        "time": "05:00:00Z",
                        "Circuit": {
                            "circuitId": "albert_park",
                            "circuitName": "Albert Park",
                            "Location": {
                                "locality": "Melbourne",
                                "country": "Australia",
                            },
                        },
                    }
                ]
            }
        }
    }


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


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_json, fetch_text])
async def test_http_fetch_helpers_drain_unretrieved_future_exceptions(
    hass, fetcher
) -> None:
    session = MagicMock()
    session.headers = {"User-Agent": "ua"}
    session.get = MagicMock(return_value=_TimeoutResponse())

    contexts: list[dict] = []
    previous_handler = hass.loop.get_exception_handler()
    hass.loop.set_exception_handler(lambda _loop, context: contexts.append(context))
    try:
        with pytest.raises(TimeoutError):
            await fetcher(
                hass,
                session,
                "https://example.com/data",
                cache={},
                inflight={},
                persist_map={},
            )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)
    finally:
        hass.loop.set_exception_handler(previous_handler)

    assert contexts == []


@pytest.mark.asyncio
async def test_fia_documents_coordinator_passes_user_agent_to_season_lookup(
    hass,
) -> None:
    race_coordinator = MagicMock()
    race_coordinator.data = _future_race_payload()
    coordinator = FiaDocumentsCoordinator(
        hass,
        race_coordinator,
        session=MagicMock(),
        user_agent="test-ua",
        cache={},
        inflight={},
        persist_map={},
        persist_save=MagicMock(),
    )

    mock_fetch = AsyncMock(
        return_value=(
            '<a href="https://www.fia.com/documents/championships/'
            'fia-formula-one-world-championship-14/season/season-2026-9999">'
            "2026</a>"
        )
    )
    with pytest.MonkeyPatch().context() as monkeypatch:
        monkeypatch.setattr(
            "custom_components.f1_sensor.__init__.fetch_text",
            mock_fetch,
        )
        url = await coordinator._get_season_url("2026")

    assert url.endswith("/season/season-2026-9999")
    assert mock_fetch.await_args.kwargs["headers"] == {"User-Agent": "test-ua"}
