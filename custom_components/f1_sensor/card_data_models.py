"""Entity-independent projections for shared dashboard and sensor data."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DataSnapshot:
    """One projection; consumers receive their own mutable attribute copy."""

    value: Any
    attributes: dict[str, Any]


def standings_snapshot(payload: dict | None, kind: str) -> DataSnapshot:
    """Preserve the public standings contract without constructing an entity."""
    source_key, attribute_key = (
        ("DriverStandings", "driver_standings")
        if kind == "drivers"
        else ("ConstructorStandings", "constructor_standings")
    )
    lists = (
        (payload or {})
        .get("MRData", {})
        .get("StandingsTable", {})
        .get("StandingsLists", [])
    )
    if not lists:
        return DataSnapshot(0, {})
    first = lists[0]
    rows = first.get(source_key, [])
    return DataSnapshot(
        len(rows),
        {
            "season": first.get("season"),
            "round": first.get("round"),
            attribute_key: deepcopy(rows),
        },
    )
