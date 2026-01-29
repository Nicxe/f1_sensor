from __future__ import annotations

import asyncio
import json
import logging
import time
import re
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

import async_timeout
from typing import Any, Dict, Optional, Callable, List
from urllib.parse import urlencode, urljoin
from json import JSONDecodeError

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.loader import async_get_integration
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    ENABLE_DEVELOPMENT_MODE_UI,
    F1_COUNTRY_CODES,
    FLAG_CDN_BASE_URL,
)

try:
    from tzfpy import get_tz as _tzfpy_get_tz
except ImportError:  # pragma: no cover - handled gracefully when dependency missing
    _tzfpy_get_tz = None

_LOGGER = logging.getLogger(__name__)

# Avoid log spam: only log Jolpica cache-hit UA once per cache key per runtime.
_JOLPICA_UA_HIT_LOGGED: set[str] = set()
_JOLPICA_UA_TEXT_HIT_LOGGED: set[str] = set()


def _record_jolpica_miss(hass, key: str) -> None:
    """Dev-only: count Jolpica network MISS calls for periodic summary logging."""
    if not ENABLE_DEVELOPMENT_MODE_UI:
        return
    try:
        root = hass.data.setdefault(DOMAIN, {})
        stats = root.setdefault("__jolpica_stats__", {})
        counts = stats.setdefault("counts", {})
        counts[key] = int(counts.get(key, 0)) + 1
    except Exception:
        # Never let stats break normal operation
        return


def parse_racecontrol(text: str):
    last = None
    for line in text.splitlines():
        if "{" not in line:
            continue
        _, json_part = line.split("{", 1)
        try:
            obj = json.loads("{" + json_part)
        except JSONDecodeError:
            continue
        msgs = obj.get("Messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
        elif isinstance(msgs, dict) and msgs:
            numeric_keys = [k for k in msgs.keys() if str(k).isdigit()]
            if numeric_keys:
                key = max(numeric_keys, key=lambda x: int(x))
                last = msgs[key]
                if isinstance(last, dict):
                    last.setdefault("id", int(key))
    return last


def normalize_track_status(raw: dict | None) -> str | None:
    """Map various TrackStatus payloads to canonical states.

    Canonical states: CLEAR, YELLOW, VSC, SC, RED.
    """
    if not raw:
        return None
    message = (raw.get("Message") or raw.get("TrackStatus") or "").upper()
    status = str(raw.get("Status") or "").strip()

    aliases = {
        "ALLCLEAR": "CLEAR",
        "CLEAR": "CLEAR",
        "YELLOW": "YELLOW",
        "DOUBLE YELLOW": "YELLOW",
        "DOUBLEYELLOW": "YELLOW",
        "VSC": "VSC",
        "VSCDEPLOYED": "VSC",
        "VSC ENDING": "VSC",
        "VSCENDING": "VSC",
        "SAFETY CAR": "SC",
        "SAFETYCAR": "SC",
        "SC": "SC",
        "SC DEPLOYED": "SC",
        "SC ENDING": "SC",
        "RED": "RED",
        "RED FLAG": "RED",
        "REDFLAG": "RED",
    }

    numeric = {
        "1": "CLEAR",
        "2": "YELLOW",
        "4": "SC",  # Säkrast stöd för Safety Car
        "5": "RED",
        "6": "VSC",
        # Code "7" represents VSC ending phase; map to canonical VSC
        "7": "VSC",
        "8": "CLEAR",  # Fallback, observerad som CLEAR i praktiken
        # "3": okänd/kontextberoende – logga och validera mot Race Control
    }

    # Prefer explicit message aliases when present to avoid wrong numeric overrides
    for key, val in aliases.items():
        if key in message:
            return val
    if status in numeric:
        return numeric[status]
    if message in {"CLEAR", "YELLOW", "VSC", "SC", "RED"}:
        return message
    return None


_TZFPY_WARNED = False


def get_timezone(lat: Any, lon: Any) -> Optional[str]:
    """Return an IANA timezone name for the provided coordinates via tzfpy."""
    if lat is None or lon is None:
        return None

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None

    if _tzfpy_get_tz is None:
        global _TZFPY_WARNED
        if not _TZFPY_WARNED:
            _LOGGER.error(
                "tzfpy dependency missing; timezone lookups disabled for coordinates"
            )
            _TZFPY_WARNED = True
        return None

    try:
        tz = _tzfpy_get_tz(lon_f, lat_f)
    except Exception as err:  # pragma: no cover - defensive guard
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "tzfpy lookup failed for lat=%s lon=%s: %s", lat, lon, err, exc_info=err
            )
        return None
    return tz


def get_country_code(country_name: str | None) -> str | None:
    """Return ISO 3166-1 alpha-2 code for F1 circuit country name."""
    if not country_name:
        return None
    return F1_COUNTRY_CODES.get(country_name)


def get_country_flag_url(country_name: str | None) -> str | None:
    """Return flag CDN URL for F1 circuit country name."""
    code = get_country_code(country_name)
    if not code:
        return None
    return f"{FLAG_CDN_BASE_URL}/{code}.png"


async def build_user_agent(hass) -> str:
    """Return UA like 'HomeAssistantF1Sensor/<integration> HomeAssistant/<core>'."""
    integration = await async_get_integration(hass, DOMAIN)
    return f"HomeAssistantF1Sensor/{integration.version} HomeAssistant/{HA_VERSION}"


def _make_cache_key(url: str, params: Optional[Dict[str, Any]] = None) -> str:
    if params:
        try:
            # Stable ordering of query params
            qp = urlencode(sorted([(str(k), str(v)) for k, v in params.items()]))
            return f"{url}?{qp}"
        except Exception:
            return url
    return url


async def fetch_json(
    hass,
    session,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    ttl_seconds: int = 30,
    cache: Optional[Dict[str, tuple[float, Any]]] = None,
    inflight: Optional[Dict[str, asyncio.Future]] = None,
    persist_map: Optional[Dict[str, Any]] = None,
    persist_save: Optional[Callable[[], None]] = None,
) -> Any:
    """Fetch JSON with TTL cache and in-flight request de-duplication.

    - Only intended for regular HTTP GETs (Jolpica/Ergast). Do not use for live WS.
    - Returns parsed JSON (dict/list).
    """
    key = _make_cache_key(url, params)
    now = time.monotonic()
    cache_map: Dict[str, tuple[float, Any]] = cache if isinstance(cache, dict) else {}
    inflight_map: Dict[str, asyncio.Future] = (
        inflight if isinstance(inflight, dict) else {}
    )
    persist_store: Dict[str, Any] = persist_map if isinstance(persist_map, dict) else {}

    # Cache hit
    try:
        exp, data = cache_map.get(key, (0.0, None))
        if exp and now < exp:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                is_jolpica = "api.jolpi.ca" in str(url) or "/ergast/" in str(url)
                if is_jolpica:
                    # ua_sent: prefer explicit per-request headers when provided
                    ua_sent = None
                    try:
                        if isinstance(headers, dict) and headers.get("User-Agent"):
                            ua_sent = headers.get("User-Agent")
                        else:
                            ua_sent = (
                                session.headers.get("User-Agent")
                                if getattr(session, "headers", None) is not None
                                else None
                            )
                    except Exception:
                        ua_sent = None
                    # Log cache-hit UA once per key to keep logs readable
                    if key not in _JOLPICA_UA_HIT_LOGGED:
                        _JOLPICA_UA_HIT_LOGGED.add(key)
                        _LOGGER.debug(
                            "Jolpica cache HIT key=%s ttl_left=%.1fs ua_sent=%s",
                            key,
                            exp - now,
                            ua_sent,
                        )
                else:
                    _LOGGER.debug(
                        "HTTP cache HIT key=%s ttl_left=%.1fs", key, exp - now
                    )
            return data
    except Exception:
        _LOGGER.debug("Cache lookup failed for key=%s", key, exc_info=True)

    # In-flight dedup
    fut = inflight_map.get(key)
    if fut is not None and not fut.done():
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("HTTP request COALESCED key=%s (awaiting in-flight)", key)
        return await asyncio.shield(fut)

    # First requester: perform network call
    loop = hass.loop
    fut = loop.create_future()
    inflight_map[key] = fut
    try:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            ua_sent = None
            try:
                if isinstance(headers, dict) and headers.get("User-Agent"):
                    ua_sent = headers.get("User-Agent")
                else:
                    # aiohttp ClientSession exposes default headers via `.headers`
                    ua_sent = (
                        session.headers.get("User-Agent")
                        if getattr(session, "headers", None) is not None
                        else None
                    )
            except Exception:
                ua_sent = None
            if "api.jolpi.ca" in str(url) or "/ergast/" in str(url):
                _LOGGER.debug(
                    "Jolpica request MISS -> url=%s ua_sent=%s key=%s",
                    url,
                    ua_sent,
                    key,
                )
            else:
                _LOGGER.debug("HTTP cache MISS key=%s -> fetching", key)
        if "api.jolpi.ca" in str(url) or "/ergast/" in str(url):
            _record_jolpica_miss(hass, key)
        async with async_timeout.timeout(30):
            async with session.get(url, params=params, headers=headers) as resp:
                resp.raise_for_status()
                text = await resp.text()
        data = json.loads(text.lstrip("\ufeff"))
        # Update cache
        try:
            cache_map[key] = (now + max(1, int(ttl_seconds)), data)
        except Exception:
            _LOGGER.debug("Failed to update cache for key=%s", key, exc_info=True)
        # Persist simplified record (data only). Validation headers are optional future work.
        try:
            persist_store[key] = {
                "data": data,
                "saved_at": time.time(),
            }
            if callable(persist_save):
                # Save debounced by caller; we just request a save
                persist_save()
        except Exception:
            _LOGGER.debug("Failed to persist data for key=%s", key, exc_info=True)
        fut.set_result(data)
        return data
    except Exception as err:
        if not fut.done():
            fut.set_exception(err)
        raise
    finally:
        # Allow future consumers to see completed future for a short while,
        # then remove to avoid unbounded growth in inflight map.
        try:

            async def _cleanup_later():
                await asyncio.sleep(0)  # next loop tick
                inflight_map.pop(key, None)

            loop.create_task(_cleanup_later())
        except Exception:
            try:
                inflight_map.pop(key, None)
            except Exception:
                pass


async def fetch_text(
    hass,
    session,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    ttl_seconds: int = 30,
    cache: Optional[Dict[str, tuple[float, Any]]] = None,
    inflight: Optional[Dict[str, asyncio.Future]] = None,
    persist_map: Optional[Dict[str, Any]] = None,
    persist_save: Optional[Callable[[], None]] = None,
) -> str:
    """Fetch raw text with TTL cache and in-flight de-duplication."""
    base_key = _make_cache_key(url, params)
    key = f"text::{base_key}"
    now = time.monotonic()
    cache_map: Dict[str, tuple[float, Any]] = cache if isinstance(cache, dict) else {}
    inflight_map: Dict[str, asyncio.Future] = (
        inflight if isinstance(inflight, dict) else {}
    )
    persist_store: Dict[str, Any] = persist_map if isinstance(persist_map, dict) else {}

    try:
        exp, data = cache_map.get(key, (0.0, None))
        if exp and now < exp and isinstance(data, str):
            if _LOGGER.isEnabledFor(logging.DEBUG):
                is_jolpica = "api.jolpi.ca" in str(url) or "/ergast/" in str(url)
                if is_jolpica:
                    ua_sent = None
                    try:
                        if isinstance(headers, dict) and headers.get("User-Agent"):
                            ua_sent = headers.get("User-Agent")
                        else:
                            ua_sent = (
                                session.headers.get("User-Agent")
                                if getattr(session, "headers", None) is not None
                                else None
                            )
                    except Exception:
                        ua_sent = None
                    if key not in _JOLPICA_UA_TEXT_HIT_LOGGED:
                        _JOLPICA_UA_TEXT_HIT_LOGGED.add(key)
                        _LOGGER.debug(
                            "Jolpica text cache HIT key=%s ttl_left=%.1fs ua_sent=%s",
                            key,
                            exp - now,
                            ua_sent,
                        )
                else:
                    _LOGGER.debug(
                        "HTTP text cache HIT key=%s ttl_left=%.1fs", key, exp - now
                    )
            return data
    except Exception:
        _LOGGER.debug("Text cache lookup failed for key=%s", key, exc_info=True)

    fut = inflight_map.get(key)
    if fut is not None and not fut.done():
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("HTTP text request COALESCED key=%s", key)
        return await asyncio.shield(fut)

    loop = hass.loop
    fut = loop.create_future()
    inflight_map[key] = fut
    try:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            ua_sent = None
            try:
                if isinstance(headers, dict) and headers.get("User-Agent"):
                    ua_sent = headers.get("User-Agent")
                else:
                    ua_sent = (
                        session.headers.get("User-Agent")
                        if getattr(session, "headers", None) is not None
                        else None
                    )
            except Exception:
                ua_sent = None
            if "api.jolpi.ca" in str(url) or "/ergast/" in str(url):
                _LOGGER.debug(
                    "Jolpica text request MISS -> url=%s ua_sent=%s key=%s",
                    url,
                    ua_sent,
                    key,
                )
            else:
                _LOGGER.debug("HTTP text cache MISS key=%s -> fetching", key)
        if "api.jolpi.ca" in str(url) or "/ergast/" in str(url):
            _record_jolpica_miss(hass, key)
        async with async_timeout.timeout(30):
            async with session.get(url, params=params, headers=headers) as resp:
                resp.raise_for_status()
                text = await resp.text()
        try:
            cache_map[key] = (now + max(1, int(ttl_seconds)), text)
        except Exception:
            _LOGGER.debug("Failed to update text cache for key=%s", key, exc_info=True)
        try:
            persist_store[key] = {
                "data": text,
                "saved_at": time.time(),
            }
            if callable(persist_save):
                persist_save()
        except Exception:
            _LOGGER.debug("Failed to persist text data for key=%s", key, exc_info=True)
        fut.set_result(text)
        return text
    except Exception as err:
        if not fut.done():
            fut.set_exception(err)
        raise
    finally:
        try:

            async def _cleanup_later():
                await asyncio.sleep(0)
                inflight_map.pop(key, None)

            loop.create_task(_cleanup_later())
        except Exception:
            try:
                inflight_map.pop(key, None)
            except Exception:
                pass


class PersistentCache:
    """Versioned persistent cache using HA Store, per config-entry."""

    def __init__(self, hass, entry_id: str, version: int = 1) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(hass, version, f"{DOMAIN}_{entry_id}_http_cache_v1")
        self._data: Dict[str, Any] = {}
        self._save_task: asyncio.Task | None = None

    async def load(self) -> Dict[str, Any]:
        try:
            data = await self._store.async_load()
            if isinstance(data, dict):
                self._data = data
            else:
                self._data = {}
        except Exception:
            self._data = {}
        return self._data

    def map(self) -> Dict[str, Any]:
        return self._data

    def schedule_save(self, delay: float = 0.1) -> None:
        try:
            if self._save_task and not self._save_task.done():
                return

            async def _save_later():
                try:
                    await asyncio.sleep(delay)
                    await self._store.async_save(self._data)
                except Exception:
                    pass

            self._save_task = self._hass.loop.create_task(_save_later())
        except Exception:
            # Fallback to immediate save
            try:
                self._hass.loop.create_task(self._store.async_save(self._data))
            except Exception:
                pass


_PDF_ANCHOR_RE = re.compile(
    r"<a[^>]*href=(['\"])(?P<href>[^'\"]+?\.pdf)\1[^>]*>(?P<label>[\s\S]*?)</a>",
    re.IGNORECASE,
)
_PUBLISHED_ON_RE = re.compile(
    r"Published on (\d{2})\.(\d{2})\.(\d{2}) (\d{2}):(\d{2})(?:\s*(CET|CEST|UTC))?",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TZ_OFFSETS = {
    "CET": 1,
    "CEST": 2,
    "UTC": 0,
}


def _normalize_text(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").replace("\xa0", " ")).strip()


def _strip_html(text: str) -> str:
    return _WS_RE.sub(
        " ",
        _TAG_RE.sub(" ", text or ""),
    ).strip()


def _extract_published(text: str) -> tuple[Optional[str], str]:
    if not text:
        return None, text
    match = _PUBLISHED_ON_RE.search(text)
    if not match:
        return None, text
    day, month, year_short, hour, minute, zone = match.groups()
    try:
        year = int(year_short)
        year += 2000 if year < 50 else 1900
        dt = datetime(
            year,
            int(month),
            int(day),
            int(hour),
            int(minute),
        )
        zone = (zone or "UTC").upper()
        offset = _TZ_OFFSETS.get(zone, 0)
        tzinfo = timezone(timedelta(hours=offset))
        dt = dt.replace(tzinfo=tzinfo)
        iso = dt.astimezone(timezone.utc).isoformat()
    except Exception:
        iso = None
    cleaned = text.replace(match.group(0), "").strip()
    cleaned = _WS_RE.sub(" ", cleaned.replace(zone or "", "")).strip()
    return iso, cleaned


def _get_attr(attrs: list[tuple[str, str | None]], name: str) -> str | None:
    for key, value in attrs:
        if key.lower() == name:
            return value
    return None


def _is_doc_container(tag: str, attrs: list[tuple[str, str | None]] | None) -> bool:
    if tag in {"li", "tr"}:
        return True
    if tag in {"div", "article", "section"}:
        class_attr = _get_attr(attrs or [], "class")
        if class_attr and "document" in class_attr.lower():
            return True
    return False


class _FiaDocumentHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._documents: list[dict[str, str]] = []
        self._container_stack: list[tuple[int, list[str]]] = []
        self._tag_stack: list[str] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []
        self._current_container: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if _is_doc_container(tag, attrs):
            self._container_stack.append((len(self._tag_stack), []))
        if tag == "a":
            href = _get_attr(attrs, "href")
            if href and ".pdf" in href.lower():
                self._current_href = href
                self._current_text = []
                self._current_container = (
                    self._container_stack[-1][1] if self._container_stack else None
                )

    def handle_data(self, data: str) -> None:
        if not data:
            return
        for _, buffer in self._container_stack:
            buffer.append(data)
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "a" and self._current_href is not None:
            anchor_text = "".join(self._current_text)
            container_text = (
                "".join(self._current_container) if self._current_container else ""
            )
            self._documents.append(
                {
                    "href": self._current_href,
                    "anchor_text": anchor_text,
                    "container_text": container_text,
                }
            )
            self._current_href = None
            self._current_text = []
            self._current_container = None
        if self._tag_stack:
            self._tag_stack.pop()
        while self._container_stack and self._container_stack[-1][0] > len(
            self._tag_stack
        ):
            self._container_stack.pop()

    def close(self) -> None:
        super().close()
        if self._current_href is not None:
            anchor_text = "".join(self._current_text)
            container_text = (
                "".join(self._current_container) if self._current_container else ""
            )
            self._documents.append(
                {
                    "href": self._current_href,
                    "anchor_text": anchor_text,
                    "container_text": container_text,
                }
            )
            self._current_href = None
            self._current_text = []
            self._current_container = None

    def documents(self) -> list[dict[str, str]]:
        return list(self._documents)


def _build_fia_documents(entries: list[tuple[str, str]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for href, text in entries:
        if not href:
            continue
        normalized = _normalize_text(text)
        published, clean_text = _extract_published(normalized)
        absolute = urljoin("https://www.fia.com", href)
        doc = {
            "name": clean_text or absolute,
            "url": absolute,
            "published": published,
        }
        docs.append(doc)
    return docs


def _parse_fia_documents_html(html: str) -> list[dict[str, Any]]:
    parser = _FiaDocumentHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return []
    entries: list[tuple[str, str]] = []
    for item in parser.documents():
        href = item.get("href") or ""
        anchor_text = item.get("anchor_text") or ""
        container_text = item.get("container_text") or ""
        text = anchor_text
        if container_text and ("Published on" in container_text or not text.strip()):
            text = container_text
        entries.append((href, text))
    return _build_fia_documents(entries)


def _parse_fia_documents_regex(html: str) -> list[dict[str, Any]]:
    entries: list[tuple[str, str]] = []
    for match in _PDF_ANCHOR_RE.finditer(html):
        href = match.group("href")
        label = match.group("label") or ""
        text = _strip_html(label)
        entries.append((href, text))
    return _build_fia_documents(entries)


def parse_fia_documents(html: str) -> List[Dict[str, Any]]:
    """Extract FIA PDF links from HTML."""
    if not isinstance(html, str) or not html:
        return []
    docs = _parse_fia_documents_html(html)
    if docs:
        return docs
    return _parse_fia_documents_regex(html)
