"""Association evidence for the existing driver lap-history accumulator."""

import math
from typing import Any

from .data_helpers import _parse_lap_time_to_secs

LAP_HISTORY_VERSION = 1
MAX_TYRE_STINTS_PER_DRIVER = 32


def confirmed_race_trace_lap(number: Any, value: Any) -> int | None:
    """Validate an explicit pair before it can anchor a plotted observation."""
    lap = _explicit_lap_number(number)
    if lap is None or lap > 500 or not isinstance(value, str) or not value.strip():
        return None
    try:
        seconds = _parse_lap_time_to_secs(value.strip())
    except (ValueError, TypeError, OverflowError):
        return None
    return lap if math.isfinite(seconds) and 0.0005 <= seconds < 9007199254740 else None


def record_lap_time(
    history: dict[str, Any],
    lap_time: str,
    lap_number: Any = None,
    *,
    explicit_number: Any = None,
    snapshot: bool = False,
) -> tuple[int, bool]:
    """Update the existing history with its legacy numbering and new evidence."""
    last_lap = history.get("last_recorded_lap", 0)
    try:
        number = int(lap_number) if lap_number is not None else None
    except (TypeError, ValueError):
        number = None
    retained = bool(number and number > 0)
    if not retained:
        number = last_lap + 1
    laps = history.setdefault("laps", {})
    key = str(number)
    changed = update_lap_metadata(
        history,
        number,
        lap_time,
        explicit_number=explicit_number,
        retained_number=retained,
        snapshot=snapshot,
    )
    if laps.get(key) == lap_time and last_lap >= number:
        return number, changed
    laps[key] = lap_time
    if last_lap < number:
        history["last_recorded_lap"] = number
    completed = history.get("completed_laps", 0) or 0
    if isinstance(completed, int) and completed < number:
        history["completed_laps"] = number
    return number, True


def _explicit_lap_number(value: Any) -> int | None:
    """Accept a positive provider integer without coercing flags or fractions."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value.isdecimal():
            return None
        value = int(value)
    return value if isinstance(value, int) and value > 0 else None


def update_lap_metadata(
    history: dict[str, Any],
    lap_number: int,
    lap_time: str,
    *,
    explicit_number: Any = None,
    retained_number: bool = False,
    snapshot: bool = False,
) -> bool:
    """Bind evidence to the value about to be stored, without inferring a lap.

    Call before replacing ``history["laps"][lap_number]``. A matching restored
    value keeps its previous explicit evidence; a changed value never inherits
    that evidence from an older time. Merged snapshots do not establish a pair.
    """
    key = str(lap_number)
    metadata = history.setdefault("lap_metadata", {})
    previous = metadata.get(key)
    previous_time = history.get("laps", {}).get(key)
    if (
        previous_time == lap_time
        and isinstance(previous, dict)
        and (
            previous.get("association") == "confirmed"
            or snapshot
            or _explicit_lap_number(explicit_number) != lap_number
        )
    ):
        return False
    if snapshot:
        value = {"association": "ambiguous", "reason": "snapshot_unverified"}
    elif _explicit_lap_number(explicit_number) == lap_number:
        value = {"association": "confirmed", "reason": None}
    elif previous_time is not None and previous_time != lap_time:
        value = {"association": "ambiguous", "reason": "ambiguous_correction"}
    else:
        value = {
            "association": "inferred",
            "reason": "retained_lap_number"
            if retained_number
            else "missing_lap_number",
        }
    if previous == value:
        return False
    metadata[key] = value
    return True
