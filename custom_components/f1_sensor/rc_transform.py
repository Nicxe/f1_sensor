"""Helpers to clean raw RaceControlMessages."""
import gzip
import json
import datetime as dt
import dateutil.parser as dparse

FLAG_MAP = {
    0: None,
    1: "GREEN",
    2: "YELLOW",
    3: "DOUBLE YELLOW",
    4: "RED",
    5: "BLUE",
    6: "WHITE",
    7: "BLACK",
    8: "CHEQUERED",
}
CATEGORY_MAP = {
    0: "CarEvent",
    1: "SafetyCar",
    2: "Flag",
    3: "Session",
    4: "Message",
    5: "Other",
}
SCOPE_MAP = {0: "Track", 1: "Sector", 2: "Driver"}


def _parse_date(raw, t0: dt.datetime) -> str:
    """Return ISO timestamp from UTC ms offset or ISO string."""
    if isinstance(raw, (int, float)):
        return (t0 + dt.timedelta(milliseconds=raw)).isoformat() + "Z"
    return dparse.parse(str(raw)).isoformat()


def clean_rc(data_or_bytes, t0: dt.datetime) -> dict:
    """Return a readable dict from RaceControl payload."""
    if isinstance(data_or_bytes, (bytes, bytearray)):
        data = json.loads(gzip.decompress(data_or_bytes))
    else:
        data = data_or_bytes
    return {
        "category": CATEGORY_MAP.get(data["m"]),
        "flag": FLAG_MAP.get(data.get("f")),
        "scope": SCOPE_MAP.get(data["s"]),
        "sector": data.get("sc"),
        "lap_number": data.get("lap"),
        "driver_number": data.get("drv"),
        "message": data.get("mes"),
        "date": _parse_date(data["utc"], t0),
    }
