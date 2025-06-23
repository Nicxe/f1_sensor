import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict

import aiohttp

_LOGGER = logging.getLogger(__name__)

_INDEX_CACHE: dict[int, tuple[datetime, Dict[str, Any]]] = {}
_CACHE_LOCK = asyncio.Lock()


async def _get_year_index(session: aiohttp.ClientSession, year: int) -> Dict[str, Any]:
    async with _CACHE_LOCK:
        entry = _INDEX_CACHE.get(year)
        now = datetime.utcnow()
        if entry and entry[0] > now:
            return entry[1]

    url = f"https://livetiming.formula1.com/static/{year}/Index.json"
    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.json()

    async with _CACHE_LOCK:
        ttl = timedelta(minutes=30) + timedelta(seconds=random.randint(-300, 300))
        _INDEX_CACHE[year] = (datetime.utcnow() + ttl, data)

    return data


async def resolve_racecontrol_url(year: int, grand_prix: str, session_type: str) -> str:
    """Resolve RaceControlMessages stream URL from F1 index files."""
    async with aiohttp.ClientSession() as session:
        year_index = await _get_year_index(session, year)

        gp = grand_prix.lower()
        meeting = None
        for m in year_index.get("Meetings", []):
            name = str(m.get("Name", "")).lower()
            off = str(m.get("OfficialName", "")).lower()
            if gp in (name, off):
                meeting = m
                break
        if not meeting:
            raise ValueError("Meeting not found")

        session_obj = None
        for s in meeting.get("Sessions", []):
            if str(s.get("Name", "")).lower() == session_type.lower():
                session_obj = s
                break
        if not session_obj:
            raise ValueError("Session not found")

        session_path = session_obj.get("Path", "")
        index_url = f"https://livetiming.formula1.com/static/{session_path}Index.json"
        fallback = f"https://livetiming.formula1.com/static/{session_path}RaceControlMessages.jsonStream"

        delay = 30
        for attempt in range(10):
            async with session.get(index_url) as resp:
                if resp.status == 404:
                    data = {}
                else:
                    resp.raise_for_status()
                    data = await resp.json()
            stream_path = (
                data.get("Feeds", {}).get("RaceControlMessages", {}).get("StreamPath")
            )
            if stream_path:
                return f"https://livetiming.formula1.com/{stream_path}"
            if attempt >= 2:
                level = _LOGGER.warning if attempt < 9 else _LOGGER.error
                level(
                    "Race control stream for %s %s not ready (attempt %d)",
                    grand_prix,
                    session_type,
                    attempt + 1,
                )
            await asyncio.sleep(delay)
            delay *= 2
        return fallback
