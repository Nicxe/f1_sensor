import json
from json import JSONDecodeError

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.loader import async_get_integration

from .const import DOMAIN


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
