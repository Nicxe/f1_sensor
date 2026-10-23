"""Add planned race and sprint laps from Jolpica's alpha session schedule."""

from __future__ import annotations

from typing import Any


def validate_session_page(payload: Any) -> None:
    """Reject incomplete alpha responses before caching them."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid session response")
    metadata = payload.get("metadata")
    sessions = payload.get("data")
    if not isinstance(metadata, dict) or not isinstance(sessions, list):
        raise ValueError("Invalid session response")
    if metadata.get("total_pages") != 1:
        raise ValueError("Incomplete session response")


def add_scheduled_laps(
    schedule: dict[str, Any], session_pages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return a schedule with matched lap counts, leaving source data untouched."""
    table = schedule.get("MRData", {}).get("RaceTable", {})
    races = table.get("Races")
    if not isinstance(races, list):
        return schedule

    laps: dict[tuple[int, str], int] = {}
    for page in session_pages:
        for session in page["data"]:
            if not isinstance(session, dict) or session.get("is_cancelled"):
                continue
            round_data = session.get("round")
            if not isinstance(round_data, dict):
                continue
            try:
                round_number = int(round_data["number"])
                count = int(session["scheduled_laps"])
            except (KeyError, TypeError, ValueError):
                continue
            kind = session.get("type")
            if kind in ("R", "SR") and count > 0:
                laps[round_number, kind] = count

    enriched_races = []
    for race in races:
        if not isinstance(race, dict):
            enriched_races.append(race)
            continue
        enriched = dict(race)
        try:
            round_number = int(race["round"])
        except (KeyError, TypeError, ValueError):
            enriched_races.append(enriched)
            continue
        if (round_number, "R") in laps:
            enriched["scheduled_laps"] = laps[round_number, "R"]
        sprint = race.get("Sprint")
        if isinstance(sprint, dict) and (round_number, "SR") in laps:
            enriched["Sprint"] = {
                **sprint,
                "scheduled_laps": laps[round_number, "SR"],
            }
        enriched_races.append(enriched)

    return {
        **schedule,
        "MRData": {
            **schedule["MRData"],
            "RaceTable": {**table, "Races": enriched_races},
        },
    }
