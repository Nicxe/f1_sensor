import json
import logging
import asyncio
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from json import JSONDecodeError

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
        "4": "SC",          # Säkrast stöd för Safety Car
        "5": "RED",
        "6": "VSC",
        # Code "7" represents VSC ending phase; map to canonical VSC
        "7": "VSC",
        "8": "CLEAR",       # Fallback, observerad som CLEAR i praktiken
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
    ttl_seconds: int = 30,
    cache: Optional[Dict[str, tuple[float, Any]]] = None,
    inflight: Optional[Dict[str, asyncio.Future]] = None,
) -> Any:
    """Fetch JSON with TTL cache and in-flight request de-duplication.

    - Only intended for regular HTTP GETs (Jolpica/Ergast). Do not use for live WS.
    - Returns parsed JSON (dict/list).
    """
    key = _make_cache_key(url, params)
    now = time.monotonic()
    cache_map: Dict[str, tuple[float, Any]] = cache if isinstance(cache, dict) else {}
    inflight_map: Dict[str, asyncio.Future] = inflight if isinstance(inflight, dict) else {}

    # Cache hit
    try:
        exp, data = cache_map.get(key, (0.0, None))
        if exp and now < exp:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("HTTP cache HIT key=%s ttl_left=%.1fs", key, exp - now)
            return data
    except Exception:
        pass

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
            _LOGGER.debug("HTTP cache MISS key=%s -> fetching", key)
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            text = await resp.text()
            data = json.loads(text.lstrip("\ufeff"))
            # Update cache
            try:
                cache_map[key] = (now + max(1, int(ttl_seconds)), data)
            except Exception:
                pass
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
