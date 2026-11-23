"""Event-specific rules for interpreting Race Control's grip declarations."""

from __future__ import annotations

from datetime import date

from .const import STRAIGHT_MODE_DISABLED, STRAIGHT_MODE_LOW, STRAIGHT_MODE_NORMAL

# F1 meeting -> circuit. The 2026 FIA event maps cited in
# track_map_annotation_catalog.json contain both normal- and low-grip
# activation points for these meetings. Only the existence of a zone matters.
_ZONE_CIRCUITS_2026 = {
    "1279": "10",  # Melbourne
    "1280": "49",  # Shanghai
    "1281": "46",  # Suzuka
    "1284": "151",  # Miami
    "1285": "23",  # Montréal
    "1287": "15",  # Barcelona
    "1288": "19",  # Spielberg
    "1289": "2",  # Silverstone
    "1290": "7",  # Spa
    "1291": "4",  # Budapest
    "1292": "55",  # Zandvoort
    "1293": "39",  # Monza
    "1294": "153",  # Madrid
    "1295": "144",  # Baku
    "1308": "12",  # Bahrain GP in Sepang
    "1296": "61",  # Singapore
    # The following three maps have verified zones in both grip conditions.
    # https://www.fia.com/system/files/decision-document/2026_united_states_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf
    "1297": "9",
    # https://www.fia.com/system/files/decision-document/2026_mexico_city_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_and_emergency_exits_map.pdf
    "1298": "65",
    # https://www.fia.com/system/files/decision-document/2026_sao_paulo_grand_prix_-_competition_notes_-_circuit_map_pit_lane_drawing_emergency_exits_map_and_red_zone.pdf
    "1299": "14",
}

# Explicit zero-zone decision for this event only. A missing map is different.
# https://www.formula1.com/en/latest/article/the-risk-perspective-how-f1-drivers-engineers-and-strategists-tackle-the-monaco-grand-prix.2GImf5MWJqGNRgUx7ZhNh8
_MONACO_2026 = ("1286", "22")

# First published in Section B Issue 07, B7.2.2(d). Austria was the next GP.
# https://www.fia.com/system/files/documents/fia_2026_f1_regulations_-_section_b_sporting_-_iss_07_-_2026-06-25.pdf
_LOW_GRIP_RULE_PUBLISHED = date(2026, 6, 25)


def _session_date(session_info: dict | None) -> date | None:
    if not session_info:
        return None
    start = session_info.get("StartDate")
    if not start:
        # SessionInfo deltas may initially have only the archive path,
        # <year>/<meeting date>_<meeting>/<session date>_<session>/.
        path = str(session_info.get("Path") or "").strip("/").split("/")
        if len(path) != 3:
            return None
        start = path[2].partition("_")[0]
    try:
        return date.fromisoformat(str(start).partition("T")[0])
    except ValueError:
        return None


def low_grip_disables_overtake(session_info: dict | None) -> bool:
    """Whether low grip itself forbids Overtake under this session's rules."""
    day = _session_date(session_info)
    return day is not None and day.year == 2026 and day >= _LOW_GRIP_RULE_PUBLISHED


def safety_car_disables_overtake(session_info: dict | None) -> bool:
    """Apply the 2026 full Safety Car rule during a race or sprint (B7.2.2c)."""
    day = _session_date(session_info)
    if session_info is None or day is None or day.year != 2026:
        return False
    # Formula 1 classifies a sprint as Type=Race. Prefer the more precise name
    # when present so qualifying or a practice session cannot be misclassified.
    name = str(session_info.get("Name") or session_info.get("Type") or "")
    return name.strip().casefold() in {"race", "sprint", "sprint race"}


def straight_mode_for_grip(session_info: dict | None, grip: str | None) -> str | None:
    """Resolve track-wide aero permission in a verified meeting and grip regime."""
    day = _session_date(session_info)
    if day is None or day.year != 2026:
        return None
    meeting = session_info.get("Meeting") if session_info else None
    if not isinstance(meeting, dict) or not isinstance(meeting.get("Circuit"), dict):
        return None
    meeting_key = str(meeting.get("Key"))
    circuit_key = str(meeting["Circuit"].get("Key"))
    if (meeting_key, circuit_key) == _MONACO_2026:
        return STRAIGHT_MODE_DISABLED
    if _ZONE_CIRCUITS_2026.get(meeting_key) != circuit_key:
        return None
    return {"normal": STRAIGHT_MODE_NORMAL, "low": STRAIGHT_MODE_LOW}.get(grip)
