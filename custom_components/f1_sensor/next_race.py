"""Select upcoming races with a bounded, explicitly provisional offseason fallback."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from homeassistant.util import dt as dt_util

from .const import RACE_SWITCH_GRACE
from .helpers import _parse_race_datetime, get_next_race

# Official date and location checked on 2026-11-01. F1 still lists the race
# time as TBC. 15:00 UTC is a provisional dashboard target, not an official time.
_OPENER_START = datetime(2027, 3, 14, 15, tzinfo=UTC)
_OPENER = {
    "season": "2027",
    "round": "1",
    "raceName": "Bahrain Grand Prix",
    "date": "2027-03-14",
    "time": "15:00:00Z",
    "url": "https://www.formula1.com/en/racing/2027/bahrain",
    "Circuit": {
        "circuitId": "bahrain",
        "circuitName": "Bahrain International Circuit",
        "Location": {
            "lat": "26.0325",
            "long": "50.5106",
            "locality": "Sakhir",
            "country": "Bahrain",
        },
    },
    "schedule_source": "official_calendar_fallback",
    "race_start_estimated": True,
    "schedule_source_url": "https://www.formula1.com/en/racing/2027/bahrain",
}


def resolve_next_race(
    data: dict | None,
    *,
    now: datetime | None = None,
    grace: timedelta = RACE_SWITCH_GRACE,
    default_time: str = "00:00:00Z",
) -> tuple[datetime | None, dict | None]:
    """Prefer API races; bridge only the 2026/2027 calendar gap.

    The original season payload and persistent API cache remain untouched.
    Missing or malformed payloads never establish that the season has ended.
    """
    if not isinstance(data, dict):
        return None, None
    mr_data = data.get("MRData")
    table = mr_data.get("RaceTable") if isinstance(mr_data, dict) else None
    if not isinstance(table, dict) or not isinstance(table.get("Races"), list):
        return None, None
    races = table["Races"]
    now_utc = now or dt_util.utcnow()
    # Jolpica can publish the opener's date before its time. Keep the approved
    # provisional target for that exact event until an API time replaces it.
    candidates = [
        {**race, "time": _OPENER["time"], "race_start_estimated": True}
        if (
            isinstance(race, dict)
            and not race.get("time")
            and race.get("season") == _OPENER["season"]
            and race.get("round") == _OPENER["round"]
            and race.get("date") == _OPENER["date"]
            and isinstance(race.get("Circuit"), dict)
            and race["Circuit"].get("circuitId") == "bahrain"
        )
        else race
        for race in races
    ]
    selected = get_next_race(
        candidates, now=now_utc, grace=grace, default_time=default_time
    )
    if selected[1] is not None:
        if not selected[1].get("time"):
            return selected[0], {**selected[1], "race_start_estimated": True}
        return selected

    season = str(table.get("season") or "")
    if season not in {"2026", "2027"} or now_utc >= _OPENER_START + grace:
        return None, None
    # A published 2027 schedule supersedes this one-off bridge, including when
    # all its races have passed (for example after a changed opening date).
    if season == "2027" and races:
        return None, None

    # Do not activate from an empty or partly malformed calendar during 2026.
    # After New Year a valid empty API calendar can also bridge the gap.
    if now_utc < datetime(2027, 1, 1, tzinfo=UTC):
        if season != "2026" or not races:
            return None, None
    for race in races:
        if (
            not isinstance(race, dict)
            or str(race.get("season") or "") != season
            or not str(race.get("date") or "").startswith(f"{season}-")
        ):
            return None, None
        # An untimed finale must not activate the reserve early on race day.
        latest_start = _parse_race_datetime(
            race.get("date"), race.get("time"), default_time="23:59:59Z"
        )
        if latest_start is None or latest_start + grace > now_utc:
            return None, None

    return _OPENER_START, deepcopy(_OPENER)
