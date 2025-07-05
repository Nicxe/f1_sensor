"""Helpers to clean raw RaceControlMessages."""
import gzip
import json
import datetime as dt

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
}
SCOPE_MAP = {0: "Track", 1: "Sector", 2: "Driver"}


def clean_rc(raw_bytes: bytes, t0: dt.datetime) -> dict:
    """Return a readable dict from compressed RaceControl payload."""
    data = json.loads(gzip.decompress(raw_bytes))
    return {
        "category": CATEGORY_MAP.get(data["m"]),
        "flag": FLAG_MAP.get(data.get("f")),
        "scope": SCOPE_MAP.get(data["s"]),
        "sector": data.get("sc"),
        "lap_number": data.get("lap"),
        "driver_number": data.get("drv"),
        "message": data.get("mes"),
        "date": (t0 + dt.timedelta(milliseconds=data["utc"])).isoformat() + "Z",
    }
