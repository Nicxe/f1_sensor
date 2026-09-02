"""Behavior matrix for normalization, cache, and FIA helper functions."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
import zlib

import pytest

from custom_components.f1_sensor import helpers


def test_race_control_track_status_and_display_helpers(monkeypatch) -> None:
    assert helpers.normalize_live_timing_auth_header(None) == ""
    assert (
        helpers.normalize_live_timing_auth_header(" Authorization: Bearer token ")
        == "Bearer token"
    )
    assert helpers.parse_racecontrol("plain\n{broken") is None
    assert helpers.parse_racecontrol(
        'x {"Messages":[{"Message":"one"},{"Message":"two"}]}'
    ) == {"Message": "two"}
    assert helpers.parse_racecontrol(
        'x {"Messages":{"1":{"Message":"one"},"10":{"Message":"ten"}}}'
    ) == {"Message": "ten", "id": 10}

    assert helpers.normalize_track_status(None) is None
    assert helpers.normalize_track_status({"Message": "DOUBLE YELLOW"}) == "YELLOW"
    assert helpers.normalize_track_status({"Status": "7"}) == "VSC"
    assert helpers.normalize_track_status({"Message": "unknown"}) is None
    assert helpers.normalize_track_status({"Message": "CLEAR"}) == "CLEAR"

    monkeypatch.setattr(helpers, "_tzfpy_get_tz", None)
    monkeypatch.setattr(helpers, "_TZFPY_WARNED", False)
    assert helpers.get_timezone(None, 1) is None
    assert helpers.get_timezone("bad", 1) is None
    assert helpers.get_timezone(57.7, 12.0) is None
    assert helpers.get_timezone(57.7, 12.0) is None
    monkeypatch.setattr(helpers, "_tzfpy_get_tz", lambda lon, lat: "Europe/Stockholm")
    assert helpers.get_timezone(57.7, 12.0) == "Europe/Stockholm"

    assert helpers.get_circuit_timezone(None) is None
    assert helpers.get_country_code(None) is None
    assert helpers.get_country_flag_url("Unknown") is None
    assert helpers.get_country_flag_url("Australia").endswith("/au.png")
    assert helpers.get_circuit_map_url(None) is None
    assert helpers.get_circuit_map_url("unknown", 2026) is None
    assert helpers.get_circuit_outline_url(None) is None
    assert helpers.get_circuit_outline_url("unknown", 2026) is None
    assert "F1 FIA Report" == helpers.format_entity_name("F1", "fia_report")
    assert helpers.format_entity_name("F1", "fia-report", include_base=False) == (
        "FIA Report"
    )
    assert helpers.format_entity_name("F1", None) == "F1"


def test_cache_key_race_selection_and_compressed_payload_edges(monkeypatch) -> None:
    assert helpers._make_cache_key("https://example", {"b": 2, "a": 1}) == (
        "https://example?a=1&b=2"
    )
    assert helpers._make_cache_key("https://example") == "https://example"
    assert helpers._parse_race_datetime(None, None, default_time="00:00:00Z") is None
    monkeypatch.setattr(helpers.dt_util, "parse_datetime", lambda _: None)
    assert helpers._parse_race_datetime("bad", None, default_time="bad") is None
    parsed = helpers._parse_race_datetime(
        "2026-09-01", "12:00:00", default_time="00:00:00"
    )
    assert parsed == datetime(2026, 9, 1, 12, tzinfo=UTC)

    now = datetime(2026, 9, 1, tzinfo=UTC)
    races = [None, {"date": "bad"}, {"date": "2026-09-02", "time": "00:00:00Z"}]
    race_time, race = helpers.get_next_race(
        races, now=now, grace=timedelta(), fallback_last=False
    )
    assert race_time == datetime(2026, 9, 2, tzinfo=UTC)
    assert race is races[-1]
    assert helpers.get_next_race([], now=now, grace=timedelta()) == (None, None)
    assert helpers.get_next_race(
        [{"date": "2025-01-01"}],
        now=now,
        grace=timedelta(),
        fallback_last=False,
    ) == (None, None)
    assert helpers.get_next_race(
        [None], now=now, grace=timedelta(), fallback_last=True
    ) == (None, None)

    assert helpers._extract_jsonstream_encoded_payload("") is None
    assert helpers._extract_jsonstream_encoded_payload("URL: source") is None
    assert helpers._extract_jsonstream_encoded_payload('time ""') is None
    assert (
        helpers.decode_raw_deflate_json_payload(
            "not-base64", max_line_bytes=100, max_decompressed_bytes=100
        )
        is None
    )
    assert (
        helpers.decode_raw_deflate_json_payload(
            "x" * 101, max_line_bytes=100, max_decompressed_bytes=100
        )
        is None
    )

    raw = json.dumps([1, 2]).encode()
    compressor = zlib.compressobj(wbits=-15)
    encoded = base64.b64encode(compressor.compress(raw) + compressor.flush()).decode()
    assert (
        helpers.decode_raw_deflate_json_payload(
            encoded, max_line_bytes=100, max_decompressed_bytes=100
        )
        is None
    )
    assert helpers.parse_cardata_lines(["bad"], lambda _: None) == []

    class BrokenSplit(str):
        def split(self, *_args, **_kwargs):
            raise ValueError("split")

    assert helpers._extract_jsonstream_encoded_payload(BrokenSplit('"payload"')) is None

    class OversizedFlush:
        unconsumed_tail = b""

        def decompress(self, _raw, _limit):
            return b"{}"

        def flush(self):
            return b"extra"

    monkeypatch.setattr(
        helpers.zlib, "decompressobj", lambda **_kwargs: OversizedFlush()
    )
    assert (
        helpers.decode_raw_deflate_json_payload(
            "eA==", max_line_bytes=100, max_decompressed_bytes=2
        )
        is None
    )


def test_fia_document_parsing_dates_containers_and_url_policy(monkeypatch) -> None:
    assert helpers._extract_published("") == (None, "")
    assert helpers._extract_published("No published date") == (
        None,
        "No published date",
    )
    published, cleaned = helpers._extract_published(
        "Decision Published on 01.09.26 12:30 CEST"
    )
    assert published == "2026-09-01T10:30:00+00:00"
    assert cleaned == "Decision"
    published, _ = helpers._extract_published(
        "Decision Published on 99.99.26 12:30 UTC"
    )
    assert published is None

    assert helpers._get_attr([("CLASS", "Document")], "class") == "Document"
    assert helpers._get_attr([], "class") is None
    assert helpers._is_doc_container("li", None) is True
    assert helpers._is_doc_container("div", [("class", "document-row")]) is True
    assert helpers._is_doc_container("span", None) is False
    assert helpers._safe_fia_document_url("image.png") is None
    assert helpers._safe_fia_document_url("https://evil.example/file.pdf") is None
    assert helpers._safe_fia_document_url("http://www.fia.com/file.pdf") is None
    assert helpers._safe_fia_document_url("https://www.fia.com/file?name=x.pdf") is None
    assert helpers._safe_fia_document_url("https://www.fia.com/path.pdf") == (
        "https://www.fia.com/path.pdf"
    )
    assert helpers.parse_fia_documents("") == []
    docs = helpers.parse_fia_documents(
        '<div class="document-row">Published on 01.09.26 12:30 UTC '
        '<a href="/decision.pdf"><span>Decision</span></a></div>'
    )
    assert docs[0]["name"] == "Decision"
    assert docs[0]["published"] == "2026-09-01T12:30:00+00:00"

    parser = helpers._FiaDocumentHTMLParser()
    parser.handle_data("")
    parser.handle_starttag("a", [("href", "/open.pdf")])
    parser.handle_data("Open")
    parser.close()
    assert parser.documents()[0]["anchor_text"] == "Open"

    class BrokenParser:
        def feed(self, _html):
            raise ValueError

        def close(self):
            return None

    monkeypatch.setattr(helpers, "_FiaDocumentHTMLParser", BrokenParser)
    assert helpers._parse_fia_documents_html("broken") == []
    assert (
        helpers._parse_fia_documents_regex(
            '<a href="/fallback.pdf"><b>Fallback</b></a>'
        )[0]["name"]
        == "Fallback"
    )


async def test_fetch_helpers_cache_coalesce_force_refresh_and_jolpica(hass) -> None:
    now = helpers.time.monotonic()
    validator = Mock()
    assert await helpers.fetch_json(
        hass,
        MagicMock(),
        "https://example/data",
        cache={"https://example/data": (now + 60, {"cached": True})},
        validator=validator,
    ) == {"cached": True}
    validator.assert_called_once()

    pending = hass.loop.create_future()
    inflight = {"https://example/data": pending}
    task = asyncio.create_task(
        helpers.fetch_json(
            hass,
            MagicMock(),
            "https://example/data",
            inflight=inflight,
            validator=validator,
        )
    )
    await asyncio.sleep(0)
    pending.set_result({"shared": True})
    assert await task == {"shared": True}

    save = Mock()
    text_key = "text::https://example/text"
    cache = {text_key: (now + 60, "cached")}
    persisted = {text_key: {"data": "cached"}}
    assert (
        await helpers.fetch_text(
            hass,
            MagicMock(),
            "https://example/text",
            cache=cache,
            persist_map=persisted,
        )
        == "cached"
    )

    response = MagicMock()
    response.raise_for_status = Mock()
    response.text = AsyncMock(side_effect=['{"fresh": true}', "fresh"])
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get.return_value = context
    json_key = "https://example/json"
    json_cache = {json_key: (now + 60, {"cached": True})}
    json_persisted = {json_key: {"data": {"cached": True}}}
    assert await helpers.fetch_json(
        hass,
        session,
        json_key,
        cache=json_cache,
        persist_map=json_persisted,
        persist_save=save,
        force_refresh=True,
    ) == {"fresh": True}
    assert (
        await helpers.fetch_text(
            hass,
            session,
            "https://example/text",
            cache=cache,
            persist_map=persisted,
            persist_save=save,
            force_refresh=True,
        )
        == "fresh"
    )
    assert save.call_count == 4

    with pytest.raises(RuntimeError, match="not initialized"):
        await helpers.fetch_json(
            hass,
            MagicMock(),
            "https://api.jolpi.ca/ergast/f1/current.json",
            inflight={},
        )


async def test_fetch_helpers_validator_jolpica_and_error_cleanup_matrix(
    hass, monkeypatch
) -> None:
    monkeypatch.setattr(helpers.const, "ENABLE_DEVELOPMENT_MODE_UI", True)
    helpers._record_jolpica_miss(hass, "key")
    assert hass.data[helpers.DOMAIN]["__jolpica_stats__"]["counts"]["key"] == 1

    integration = MagicMock(version="9.9.9")
    monkeypatch.setattr(
        helpers, "async_get_integration", AsyncMock(return_value=integration)
    )
    assert "HomeAssistantF1Sensor/9.9.9" in await helpers.build_user_agent(hass)

    class BrokenItems(dict):
        def items(self):
            raise RuntimeError("items")

    assert helpers._make_cache_key("url", BrokenItems(a=1)) == "url"

    now = helpers.time.monotonic()
    cache = {"https://example/data": (now + 60, {"stale": True})}
    persisted = {"https://example/data": {"data": {"stale": True}}}
    save = Mock()
    response = MagicMock()
    response.raise_for_status = Mock()
    response.text = AsyncMock(return_value='{"fresh": true}')
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get.return_value = context
    validator = Mock(side_effect=[ValueError("stale"), None])
    assert await helpers.fetch_json(
        hass,
        session,
        "https://example/data",
        cache=cache,
        persist_map=persisted,
        persist_save=save,
        validator=validator,
    ) == {"fresh": True}
    assert save.call_count >= 2

    pending = hass.loop.create_future()
    invalidator = Mock(side_effect=ValueError("invalid"))
    invalid_task = asyncio.create_task(
        helpers.fetch_json(
            hass,
            MagicMock(),
            "https://example/shared",
            inflight={"https://example/shared": pending},
            cache={"https://example/shared": (now + 60, {})},
            persist_map={"https://example/shared": {"data": {}}},
            persist_save=save,
            validator=invalidator,
        )
    )
    await asyncio.sleep(0)
    pending.set_result({"invalid": True})
    with pytest.raises(ValueError, match="invalid"):
        await invalid_task

    client = SimpleNamespace(
        async_get_json=AsyncMock(return_value={"MRData": {}}),
        async_get_text=AsyncMock(return_value="fia text"),
    )
    from custom_components.f1_sensor.jolpica import JOLPICA_CLIENT_KEY

    hass.data[helpers.DOMAIN][JOLPICA_CLIENT_KEY] = client
    assert await helpers.fetch_json(
        hass,
        MagicMock(),
        "https://api.jolpi.ca/ergast/f1/current.json",
        params={"limit": 1},
        inflight={},
    ) == {"MRData": {}}
    assert (
        await helpers.fetch_text(
            hass,
            MagicMock(),
            "https://api.jolpi.ca/ergast/f1/current.xml",
            inflight={},
        )
        == "fia text"
    )

    text_pending = hass.loop.create_future()
    text_task = asyncio.create_task(
        helpers.fetch_text(
            hass,
            MagicMock(),
            "https://example/shared-text",
            inflight={"text::https://example/shared-text": text_pending},
        )
    )
    await asyncio.sleep(0)
    text_pending.set_result("shared")
    assert await text_task == "shared"

    failing = MagicMock()
    failing.get.side_effect = RuntimeError("network")
    inflight = {}
    with pytest.raises(RuntimeError, match="network"):
        await helpers.fetch_text(
            hass,
            failing,
            "https://example/fail",
            inflight=inflight,
        )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert inflight == {}


async def test_persistent_cache_load_save_and_prune_fallbacks(
    hass, monkeypatch
) -> None:
    cache = helpers.PersistentCache(hass, "matrix", max_entries=1, max_bytes=100)
    cache._store.async_load = AsyncMock(side_effect=RuntimeError("load"))
    assert await cache.load() == {}

    cache._data = {"one": {"data": "x", "saved_at": 0, "ttl_seconds": "bad"}}
    cache._store.async_save = AsyncMock()
    cache.schedule_save(delay=0)
    cache.schedule_save(delay=0)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await cache.async_close()
    cache._store.async_save.assert_awaited()

    removed, size = helpers.PersistentCache._plan_prune(
        [("bad", {"value": object()})],
        helpers.time.time(),
        1,
        1,
    )
    assert removed == ["bad"]
    assert size == 0


async def test_fetch_cache_force_refresh_failure_and_cleanup_exact_matrix(
    hass, monkeypatch
) -> None:
    class BadGet(dict):
        def get(self, *_args, **_kwargs):
            raise RuntimeError("cache get")

    class BadSet(dict):
        def __setitem__(self, _key, _value):
            raise RuntimeError("cache set")

    response = MagicMock()
    response.raise_for_status = Mock()
    response.text = AsyncMock(return_value='{"ok": true}')
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get.return_value = context

    assert await helpers.fetch_json(
        hass,
        session,
        "https://example/exact",
        cache=BadGet(),
        persist_map=BadSet(),
        persist_save=Mock(side_effect=RuntimeError("save")),
    ) == {"ok": True}
    assert await helpers.fetch_json(
        hass,
        session,
        "https://example/exact-set",
        cache=BadSet(),
        persist_map=BadSet(),
    ) == {"ok": True}

    text_response = MagicMock()
    text_response.raise_for_status = Mock()
    text_response.text = AsyncMock(return_value="text")
    text_context = MagicMock()
    text_context.__aenter__ = AsyncMock(return_value=text_response)
    text_context.__aexit__ = AsyncMock(return_value=False)
    text_session = MagicMock()
    text_session.get.return_value = text_context
    assert (
        await helpers.fetch_text(
            hass,
            text_session,
            "https://example/text-exact",
            cache=BadGet(),
            persist_map=BadSet(),
            persist_save=Mock(side_effect=RuntimeError("save")),
        )
        == "text"
    )
    with pytest.raises(RuntimeError, match="not initialized"):
        hass.data.setdefault(helpers.DOMAIN, {}).clear()
        await helpers.fetch_text(
            hass,
            MagicMock(),
            "https://api.jolpi.ca/ergast/f1/exact.txt",
            inflight={},
        )


def test_cardata_fallback_race_and_fia_parser_exact_matrix(monkeypatch) -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    fallback = {"date": "2025-01-01", "time": "12:00:00Z"}
    dt_value, race = helpers.get_next_race(
        ["bad", fallback], now=now, grace=timedelta(), fallback_last=True
    )
    assert race is fallback
    assert dt_value == datetime(2025, 1, 1, 12, tzinfo=UTC)

    payload = {"Entries": ["bad", {"Utc": "2026-09-01T12:00:00Z"}]}
    raw = json.dumps(payload).encode()
    compressor = zlib.compressobj(wbits=-15)
    encoded = base64.b64encode(compressor.compress(raw) + compressor.flush()).decode()
    line = f'00:00:00.000"{encoded}"'
    parsed = helpers.parse_cardata_line(
        line,
        lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
    )
    assert parsed == [datetime(2026, 9, 1, 12, tzinfo=UTC)]

    class BrokenParser:
        def feed(self, _html):
            raise ValueError("html")

        def close(self):
            return None

    monkeypatch.setattr(helpers, "_FiaDocumentHTMLParser", BrokenParser)
    docs = helpers.parse_fia_documents('<a href="/fallback.pdf">Fallback</a>')
    assert docs[0]["name"] == "Fallback"
