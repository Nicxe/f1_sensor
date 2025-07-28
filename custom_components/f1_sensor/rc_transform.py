"""Helpers to clean raw RaceControlMessages."""
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
    "VIRTUAL SAFETY CAR": "VSC",
    "CLEAR": "CLEAR",
}

FLAG_MAP.update({
    "GREEN": "GREEN",
    "CLEAR": "CLEAR",
    "BLACK AND WHITE": "BLACK AND WHITE",
})

CATEGORY_MAP.update({
    "Flag": "Flag",
    "SafetyCar": "SafetyCar",
    "Other": "Other",
})
SCOPE_MAP = {
    0: "Track",
    1: "Sector",
    2: "Driver",
    "Track": "Track",
    "Sector": "Sector",
    "Driver": "Driver",
}


def _parse_date(raw, t0: dt.datetime) -> str:
    """Return ISO-8601 timestamp in UTC regardless of input."""
    if isinstance(raw, (int, float)):
        dt_obj = t0 + dt.timedelta(milliseconds=raw)
    else:
        dt_obj = dparse.parse(raw)

    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)

    return dt_obj.astimezone(dt.timezone.utc).isoformat()


def clean_rc(data, t0: dt.datetime):
    """Normalisera RaceControl-rad oavsett nyckeltyp."""
    if not isinstance(data, (dict, bytes, bytearray)):
        return None
    if isinstance(data, (bytes, bytearray)):
        data = json.loads(gzip.decompress(data))

    category_val = data.get("m", data.get("Category"))
    flag_val = data.get("f", data.get("Flag"))
    scope_val = data.get("s", data.get("Scope"))

    category = CATEGORY_MAP.get(category_val, category_val)
    flag_raw = FLAG_MAP.get(flag_val, flag_val)
    if isinstance(flag_raw, str):
        flag = flag_raw.upper()
    else:
        flag = flag_raw
    scope = SCOPE_MAP.get(scope_val, scope_val)
    sector = data.get("sc", data.get("Sector"))
    status = data.get("st", data.get("Status"))
    mode = data.get("mo", data.get("Mode"))
    message = data.get("mes", data.get("Message"))
    utc = _parse_date(data.get("utc", data.get("Utc")), t0)

    return {
        "category": category,
        "flag": flag,
        "scope": scope,
        "sector": sector,
        "message": message,
        "utc": utc,
        "Status": status,
        "Mode": mode,
    }
