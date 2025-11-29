import asyncio
import json
import logging
import time
from json import JSONDecodeError
from typing import Callable, Optional
from urllib.parse import urlencode

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def parse_racecontrol(text: str) -> dict | None:
    """
    Parse Race Control output and return the most recent message.

    Parameters
    ----------
    text : str
        Multiline raw text containing JSON fragments.

    Returns
    -------
    dict | None
        The last message object extracted or None if no message is found.
    """
    last: dict | None = None

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
            numeric_keys = [k for k in msgs if str(k).isdigit()]
            if numeric_keys:
                key = max(numeric_keys, key=lambda x: int(x))
                data = msgs.get(key)
                if isinstance(data, dict):
                    data.setdefault("id", int(key))
                last = data

    return last


def normalize_track_status(raw: dict | None) -> str | None:
    """
    Normalize various race-control TrackStatus variants to canonical states.

    Returns one of: CLEAR, YELLOW, VSC, SC, RED.

    Parameters
    ----------
    raw : dict | None
        Incoming raw payload from Race Control.

    Returns
    -------
    str | None
        Canonical track status or None when unrecognized.
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
    """
    Build a standardized User-Agent for outgoing HTTP requests.

    Parameters
    ----------
    hass
        Home Assistant instance.

    Returns
    -------
    str
        UA string including integration version and HA core version.
    """
    integration = await async_get_integration(hass, DOMAIN)
    return "HomeAssistantF1Sensor/%s HomeAssistant/%s" % (
        integration.version,
        HA_VERSION,
    )


def _make_cache_key(url: str, params: Optional[dict[str, object]] = None) -> str:
    """
    Build a deterministic cache key from URL + sorted query parameters.

    Parameters
    ----------
    url : str
        Base URL.
    params : dict[str, object] | None
        Optional query parameters.

    Returns
    -------
    str
        Stable cache key.
    """
    if not params:
        return url

    try:
        qp = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        return f"{url}?{qp}"
    except Exception:
        return url


async def fetch_json(
    hass,
    session,
    url: str,
    *,
    params: Optional[dict[str, object]] = None,
    ttl_seconds: int = 30,
    cache: Optional[dict[str, tuple[float, object]]] = None,
    inflight: Optional[dict[str, asyncio.Future]] = None,
    persist_map: Optional[dict[str, object]] = None,
    persist_save: Optional[Callable[[], None]] = None,
) -> object:
    """Fetch JSON with TTL cache and in-flight request de-duplication.

    - Only intended for regular HTTP GETs (Jolpica/Ergast). Do not use for live WS.
    - Returns parsed JSON (dict/list).
    """
    key = _make_cache_key(url, params)
    now = time.monotonic()
    cache_map = cache if isinstance(cache, dict) else {}
    inflight_map = inflight if isinstance(inflight, dict) else {}
    store_map = persist_map if isinstance(persist_map, dict) else {}

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
    if fut and not fut.done():
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("HTTP request COALESCED key=%s (awaiting in-flight)", key)
        return await asyncio.shield(fut)

    # First requester: perform network call
    fut = hass.loop.create_future()
    inflight_map[key] = fut
    try:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("HTTP cache MISS key=%s -> fetching", key)
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            text = await resp.text()
            data = json.loads(text.lstrip("\ufeff"))
            # Update in-memory cache
            try:
                cache_map[key] = (now + max(1, int(ttl_seconds)), data)
            except Exception:
                pass
            # Persist simplified record (data only). Validation headers are optional future work.
            try:
                store_map[key] = {
                    "data": data,
                    "saved_at": time.time(),
                }
                if callable(persist_save):
                    # Save debounced by caller; we just request a save
                    persist_save()
            except Exception:
                pass
            fut.set_result(data)
            return data
    except Exception as err:
        if not fut.done():
            fut.set_exception(err)
        raise
    finally:
        # Cleanup the in-flight map on next loop iteration
        async def _cleanup() -> None:
            await asyncio.sleep(0)
            inflight_map.pop(key, None)

        try:
            hass.loop.create_task(_cleanup())
        except Exception:
            inflight_map.pop(key, None)


class PersistentCache:
    """
    Versioned persistent HTTP cache using Home Assistant's Store.

    Provides:
    - Per-config-entry namespacing
    - Deferred writes
    - Safe async file operations
    """

    def __init__(self, hass, entry_id: str, version: int = 1) -> None:
        """
        Initialize persistent cache.

        Parameters
        ----------
        hass
            Home Assistant instance.
        entry_id : str
            Config entry identifier.
        version : int
            Schema version for stored data.
        """
        self._hass = hass
        self._store = Store(hass, version, f"{DOMAIN}_{entry_id}_http_cache_v1")
        self._data: dict[str, object] = {}
        self._save_task: asyncio.Task | None = None

    async def load(self) -> dict[str, object]:
        """
        Load stored cache data.

        Returns
        -------
        dict[str, object]
            Cache dictionary.
        """
        try:
            stored = await self._store.async_load()
            self._data = stored if isinstance(stored, dict) else {}
        except Exception:
            self._data = {}
        return self._data

    def map(self) -> dict[str, object]:
        """
        Return the internal cache dictionary.

        Returns
        -------
        dict[str, object]
            The persistent cache data.
        """
        return self._data

    def schedule_save(self, delay: float = 0.1) -> None:
        """
        Schedule a deferred save.

        Parameters
        ----------
        delay : float
            Delay before saving to disk.
        """
        if self._save_task and not self._save_task.done():
            return

        async def _save() -> None:
            await asyncio.sleep(delay)
            try:
                await self._store.async_save(self._data)
            except Exception:
                pass

        try:
            self._save_task = self._hass.loop.create_task(_save())
        except Exception:
            # Worst-case fallback: attempt immediate save
            try:
                self._hass.loop.create_task(self._store.async_save(self._data))
            except Exception:
                pass
