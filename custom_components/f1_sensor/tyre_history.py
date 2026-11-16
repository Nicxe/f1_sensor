"""Session-scoped tyre history with explicit unknown ages and lap boundaries."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .lap_history import MAX_TYRE_STINTS_PER_DRIVER

_BOUNDARY_CONTEXT = (
    "timing_completed_laps",
    "observed_in_pit",
    "pit_visit_stint_index",
    "pit_exit_completed_lap",
    "pit_exit_stint_index",
    "current_tyres_stint_index",
)


def lap_count(value: Any) -> int | None:
    """Parse a non-negative source count without turning missing data into zero."""
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text.isascii() or not text.isdecimal():
        return None
    try:
        return int(text)
    except ValueError:
        return None


def normalize_compound(value: Any) -> str | None:
    """Normalize source aliases consistently for live and replay counters."""
    if not isinstance(value, str):
        return value if value is None else str(value)
    comp = value.strip().upper()
    if not comp:
        return None
    if comp in {"INTER", "INTERS", "INTERMEDIATES"}:
        return "INTERMEDIATE"
    if comp in {"WETS", "FULLWET", "FULL WET", "FULL_WET"}:
        return "WET"
    return comp


def current_physical_stint(tyre_history: dict) -> int | None:
    """Return the highest received row representing a physical tyre set."""
    stints = tyre_history.get("stints")
    if not isinstance(stints, list):
        return None
    for stint_idx in range(len(stints) - 1, -1, -1):
        stint = stints[stint_idx]
        if not isinstance(stint, dict):
            continue
        if stint.get("source_seen") is False:
            continue
        if stint.get("tyres_not_changed") is True:
            continue
        return stint_idx
    return None


def current_tyre_counter(
    tyre_history: dict, progressing_stints: set[int]
) -> int | None:
    """Follow an observed counting row through continuations and corrections."""
    confirmed_index = current_physical_stint(tyre_history)
    if confirmed_index is None:
        return None
    stints = tyre_history["stints"]
    current_index = tyre_history.get("current_tyres_stint_index")
    initializing = (
        not isinstance(current_index, int)
        or current_index < confirmed_index
        or current_index >= len(stints)
    )
    if initializing:
        current_index = confirmed_index

    compound = normalize_compound(stints[confirmed_index].get("compound"))
    for stint_index in range(confirmed_index, len(stints)):
        if stint_index == current_index:
            continue
        stint = stints[stint_index]
        if stint.get("source_seen") is False:
            continue
        if not initializing and stint_index not in progressing_stints:
            continue
        candidate_compound = normalize_compound(stint.get("compound"))
        if compound not in (None, "UNKNOWN") and candidate_compound not in (
            None,
            "UNKNOWN",
            compound,
        ):
            continue
        # Same-set rows use cumulative tyre age. Equal counters can be a
        # mirrored phantom; only independent progress establishes a switch.
        # Keep an established row through its own downward corrections.
        total_laps = stint.get("total_laps") or 0
        if total_laps > (stints[current_index].get("total_laps") or 0):
            current_index = stint_index
    return current_index


def observe_tyre_boundaries(
    entry: dict,
    *,
    previous_index: int | None = None,
    snapshot: bool = False,
    session_lap: int | None = None,
) -> bool:
    """Keep lap anchors only for an observed start or physical pit change."""
    session_lap = lap_count(session_lap)
    history = entry.get("tyre_history", {})
    stints = history.get("stints", [])
    current_index = history.get("current_stint_index")
    completed = lap_count(history.get("timing_completed_laps"))
    changed = False
    in_pit = entry.get("timing", {}).get("in_pit")
    if isinstance(in_pit, bool) and not snapshot:
        before = history.get("observed_in_pit")
        if in_pit and before is not True:
            history["pit_visit_stint_index"] = current_index
            history.pop("pit_exit_completed_lap", None)
            history.pop("pit_exit_stint_index", None)
        elif not in_pit and before is True:
            visit_index = history.pop("pit_visit_stint_index", None)
            if visit_index is not None and completed is not None:
                history["pit_exit_completed_lap"] = completed
                history["pit_exit_stint_index"] = visit_index
        if before is not in_pit:
            history["observed_in_pit"] = in_pit
            changed = True
    if not isinstance(current_index, int) or not 0 <= current_index < len(stints):
        return changed
    current = stints[current_index]
    counting_index = history.get("current_tyres_stint_index", current_index)
    if current.get("counting_stint_index") != counting_index:
        current["counting_stint_index"] = counting_index
        changed = True
    if (
        previous_index is not None
        and previous_index != current_index
        and current.get("tyres_not_changed") is False
        and not snapshot
        and completed is not None
    ):
        current["transition_completed_lap"] = completed
        changed = True
    if current.get("first_lap") is not None:
        return changed
    # The race archive normally omits NumberOfLaps=0. LapCount=1 together
    # with an untouched initial set proves lap one without inventing its age.
    at_start = current_index == 0 and (
        completed == 0
        or completed is None
        and session_lap == 1
        and current.get("total_laps_seen") is True
        and lap_count(current.get("total_laps")) == lap_count(current.get("start_laps"))
        and lap_count(current.get("start_laps")) is not None
    )
    at_change = (
        completed is not None
        and current.get("transition_completed_lap") == completed
        and in_pit is True
    )
    after_exit = (
        completed is not None
        and history.get("pit_exit_completed_lap") == completed
        and history.get("pit_exit_stint_index") == previous_index
        and previous_index is not None
        and previous_index != current_index
    )
    if current.get("tyres_not_changed") is False and (
        at_start or at_change or after_exit
    ):
        current["first_lap"] = 1 if at_start else completed + 1
        changed = True
    return changed


def accumulate_tyre_boundaries(
    drivers: dict, stream: str, payload: dict, *, session_lap: int | None
) -> None:
    """Observe the same chronological anchors while indexing recorded frames.

    This bounded replay summary stores boundary evidence only. Live tyre
    compounds and counters still come from the ordinary TimingAppData snapshot.
    """
    if stream == "LapCount":
        for entry in drivers.values():
            observe_tyre_boundaries(entry, session_lap=session_lap)
        return
    if stream not in {"TimingData", "TimingAppData"}:
        return
    if not isinstance(payload, dict):
        return
    lines = payload.get("Lines", {})
    if not isinstance(lines, dict):
        return
    for number, row in lines.items():
        if not isinstance(row, dict):
            continue
        entry = drivers.setdefault(
            str(number), {"timing": {}, "tyre_history": {"stints": []}}
        )
        history = entry["tyre_history"]
        previous = history.get("current_stint_index")
        if stream == "TimingData":
            if (count := lap_count(row.get("NumberOfLaps"))) is not None:
                history["timing_completed_laps"] = count
            if isinstance(row.get("InPit"), bool):
                entry["timing"]["in_pit"] = row["InPit"]
        else:
            progressing: set[int] = set()
            incoming = row.get("Stints")
            items = (
                enumerate(incoming)
                if isinstance(incoming, list)
                else incoming.items()
                if isinstance(incoming, dict)
                else ()
            )
            for key, values in items:
                index = lap_count(key)
                if (
                    index is None
                    or index >= MAX_TYRE_STINTS_PER_DRIVER
                    or not isinstance(values, dict)
                ):
                    continue
                stints = history["stints"]
                while len(stints) <= index:
                    stints.append({"stint_index": len(stints), "source_seen": False})
                target = stints[index]
                before_laps = target.get("total_laps") or 0
                target["source_seen"] = True
                if "Compound" in values:
                    target["compound"] = normalize_compound(values["Compound"])
                if "TyresNotChanged" in values:
                    marker = str(values["TyresNotChanged"]).strip().lower()
                    if marker in {"true", "1", "false", "0"}:
                        target["tyres_not_changed"] = marker in {"true", "1"}
                for source, dest in (
                    ("StartLaps", "start_laps"),
                    ("TotalLaps", "total_laps"),
                ):
                    if source in values:
                        target[dest] = lap_count(values[source])
                        if source == "TotalLaps":
                            target["total_laps_seen"] = target[dest] is not None
                if (
                    "TotalLaps" in values
                    and (target.get("total_laps") or 0) > before_laps
                ):
                    progressing.add(index)
            history["current_stint_index"] = current_physical_stint(history)
            history["current_tyres_stint_index"] = current_tyre_counter(
                history, progressing
            )
        observe_tyre_boundaries(entry, previous_index=previous, session_lap=session_lap)


def export_tyre_boundaries(drivers: dict, lap_history: dict) -> None:
    """Attach observed replay anchors to the existing internal LapHistory data."""
    for number, entry in drivers.items():
        history = entry["tyre_history"]
        metadata = {
            key: deepcopy(history[key]) for key in _BOUNDARY_CONTEXT if key in history
        }
        metadata["stints"] = {
            str(stint["stint_index"]): {
                key: stint[key]
                for key in (
                    "first_lap",
                    "transition_completed_lap",
                    "counting_stint_index",
                )
                if key in stint
            }
            for stint in history["stints"]
            if stint.get("source_seen") is True
        }
        lap_history.setdefault(number, {})["tyre_boundaries"] = metadata


def restore_tyre_boundaries(entry: dict, metadata: Any) -> bool:
    """Restore a checkpoint's past evidence without borrowing later frames."""
    if not isinstance(metadata, dict):
        return False
    history = entry["tyre_history"]
    for key in _BOUNDARY_CONTEXT:
        if key in metadata:
            history[key] = deepcopy(metadata[key])
    summaries = metadata.get("stints", {})
    if isinstance(summaries, dict):
        for key, values in summaries.items():
            index = lap_count(key)
            if (
                index is None
                or index >= MAX_TYRE_STINTS_PER_DRIVER
                or not isinstance(values, dict)
            ):
                continue
            stints = history["stints"]
            while len(stints) <= index:
                stints.append({"stint_index": len(stints), "source_seen": False})
            for name in (
                "first_lap",
                "transition_completed_lap",
                "counting_stint_index",
            ):
                value = lap_count(values.get(name))
                if value is not None and (name != "first_lap" or value > 0):
                    stints[index][name] = value
    if history.get("current_tyres_stint_index") is not None:
        history["replay_counter_restored"] = True
    return True


def tyre_strategy_history(entry: dict) -> tuple[list[dict], bool, int | None]:
    """Project physical sets, combining advancing same-set rows and phantoms.

    TotalLaps already includes StartLaps. Race lap anchors are never inferred
    from a first mid-session snapshot or a source stint index alone.
    """
    history = entry.get("tyre_history", {})
    completed = lap_count(history.get("timing_completed_laps"))
    groups: list[list[dict]] = []
    for raw in history.get("stints", []):
        if not isinstance(raw, dict) or raw.get("source_seen") is False:
            continue
        if raw.get("tyres_not_changed") is True:
            if groups:
                groups[-1].append(raw)
            continue
        if (
            raw.get("tyres_not_changed") is False
            or raw.get("compound") not in (None, "UNKNOWN")
            or raw.get("total_laps_seen") is True
        ):
            groups.append([raw])
    result: list[dict] = []
    current_index = history.get("current_stint_index")
    for group in groups:
        head = group[0]
        index = head.get("stint_index")
        counting_index = head.get("counting_stint_index")
        counter = next(
            (row for row in group if row.get("stint_index") == counting_index),
            None,
        )
        if counter is None:
            # A reconnect snapshot may contain older, already finished sets.
            # Like current-tyre snapshot selection, only a larger compatible
            # same-set counter proves progress beyond a mirrored head row.
            # An observed counting row above remains authoritative through its
            # own downward corrections.
            counter = head
            for candidate in group[1:]:
                if head.get("compound") not in (
                    None,
                    "UNKNOWN",
                ) and candidate.get("compound") not in (
                    None,
                    "UNKNOWN",
                    head.get("compound"),
                ):
                    continue
                candidate_age = (
                    lap_count(candidate.get("total_laps"))
                    if candidate.get("total_laps_seen") is True
                    else None
                )
                counter_age = (
                    lap_count(counter.get("total_laps"))
                    if counter.get("total_laps_seen") is True
                    else None
                )
                if candidate_age is not None and (
                    counter_age is None or candidate_age > counter_age
                ):
                    counter = candidate
        age = lap_count(head.get("start_laps"))
        total = (
            lap_count(counter.get("total_laps"))
            if counter.get("total_laps_seen") is True
            else None
        )
        distance = total - age if total is not None and age is not None else None
        if distance is not None and distance < 0:
            distance = None
        first = lap_count(head.get("first_lap"))
        if first == 0:
            first = None
        active = index == current_index
        last = completed if active and first is not None else None
        if active and first is not None and completed == first - 1:
            distance = 0
        if last is not None and last < first:
            last = None
        result.append(
            {
                "stint_index": index,
                "compound": head.get("compound"),
                "new": head.get("new") if isinstance(head.get("new"), bool) else None,
                "first_lap": first,
                "last_lap": last,
                "stint_laps": distance,
                "tyre_age_at_start": age,
                "total_laps": total,
                "is_current": active,
                "coverage": "partial",
            }
        )
    for position, stint in enumerate(result):
        first = stint["first_lap"]
        if position + 1 < len(result):
            next_start = result[position + 1]["first_lap"]
            if next_start is not None:
                stint["last_lap"] = next_start - 1
        last = stint["last_lap"]
        if first is not None and last is not None and last >= first:
            stint["stint_laps"] = last - first + 1
        # A known mount at zero distance is also complete before lap one ends.
        bounded = first is not None and (
            last is not None
            and last >= first
            or stint["is_current"]
            and completed == first - 1
        )
        if (
            bounded
            and stint["tyre_age_at_start"] is not None
            and stint["total_laps"] is not None
            and groups[position][0].get("tyres_not_changed") is False
            and stint["tyre_age_at_start"] + stint["stint_laps"] == stint["total_laps"]
        ):
            stint["coverage"] = "complete"
    complete = (
        bool(result)
        and result[0]["first_lap"] == 1
        and all(stint["coverage"] == "complete" for stint in result)
    )
    return result, complete, completed
