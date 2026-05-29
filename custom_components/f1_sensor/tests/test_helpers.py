from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
import gc
import json
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock
import zlib

import pytest

from custom_components.f1_sensor.__init__ import FiaDocumentsCoordinator
from custom_components.f1_sensor.helpers import (
    CARDATA_MAX_DECOMPRESSED_BYTES,
    CARDATA_MAX_ENTRIES,
    CARDATA_MAX_LINE_BYTES,
    fetch_json,
    fetch_text,
    parse_cardata_line,
    parse_fia_documents,
)


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


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _cardata_line(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return f'00:00:01.000"{base64.b64encode(compressed).decode()}"'


def test_parse_cardata_line_applies_size_limits() -> None:
    assert parse_cardata_line(
        _cardata_line({"Entries": [{"Utc": "2026-05-03T17:00:00Z"}]}),
        _parse_utc,
    ) == [datetime(2026, 5, 3, 17, 0, tzinfo=UTC)]

    oversized_line = f'00:00:01.000"{"A" * CARDATA_MAX_LINE_BYTES}"'
    assert parse_cardata_line(oversized_line, _parse_utc) == []

    oversized_payload = {
        "Entries": [{"Utc": "2026-05-03T17:00:00Z"}],
        "Pad": "x" * (CARDATA_MAX_DECOMPRESSED_BYTES + 1),
    }
    assert parse_cardata_line(_cardata_line(oversized_payload), _parse_utc) == []

    too_many_entries = {
        "Entries": [
            {"Utc": "2026-05-03T17:00:00Z"} for _idx in range(CARDATA_MAX_ENTRIES + 1)
        ]
    }
    assert parse_cardata_line(_cardata_line(too_many_entries), _parse_utc) == []


def test_parse_fia_documents_rejects_unsafe_document_urls() -> None:
    docs = parse_fia_documents(
        """
        <a href="/sites/default/files/decision.pdf">Decision</a>
        <a href="javascript:alert(1).pdf">Bad script</a>
        <a href="//evil.example/file.pdf">Bad host</a>
        <a href="http://www.fia.com/insecure.pdf">Bad scheme</a>
        """
    )

    assert docs == [
        {
            "name": "Decision",
            "url": "https://www.fia.com/sites/default/files/decision.pdf",
            "published": None,
        }
    ]


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
