import gzip
import json
import datetime as dt
from dateutil import parser as dparse

CATEGORY_MAP = {
    0: "CarEvent",
    1: "SafetyCar",
    2: "Flag",
    3: "Session",
    4: "Message",
    5: "Other",
}
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
    "CLEAR": "CLEAR",
}
SCOPE_MAP = {
    0: "Track",
    1: "Sector",
    2: "Driver",
    "Track": "Track",
    "Sector": "Sector",
    "Driver": "Driver",
}

def _parse_date(raw, t0):
    """Return ISO-8601 regardless if raw is milliseconds or ISO string."""
    if isinstance(raw, (int, float)):
        return (t0 + dt.timedelta(milliseconds=raw)).isoformat() + "Z"
    return dparse.parse(raw).isoformat()


def clean_rc(data: dict, t0: dt.datetime) -> dict:
    """Normalize RaceControl row regardless of key type."""
    if isinstance(data, (bytes, bytearray)):
        data = json.loads(gzip.decompress(data))

    category_val = data.get("m", data.get("Category"))
    flag_val = data.get("f", data.get("Flag"))
    scope_val = data.get("s", data.get("Scope"))

    return {
        "category": CATEGORY_MAP.get(category_val, category_val),
        "flag": FLAG_MAP.get(flag_val, flag_val),
        "scope": SCOPE_MAP.get(scope_val, scope_val),
        "sector": data.get("sc", data.get("Sector")),
        "lap_number": data.get("lap", data.get("Lap")),
        "driver_number": data.get("drv", data.get("RacingNumber")),
        "message": data.get("mes", data.get("Message")),
        "date": _parse_date(data.get("utc", data.get("Utc")), t0),
    }
