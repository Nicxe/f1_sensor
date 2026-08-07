"""Strict, atomic pagination helpers for Jolpica API payloads."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import Any

JOLPICA_PAGE_SIZE = 100
JOLPICA_PAGE_CAP = 100


class JolpicaPaginationError(RuntimeError):
    """Raised when a paginated Jolpica response is incomplete or inconsistent."""


class _JolpicaTotalChanged(JolpicaPaginationError):
    """Raised when the authoritative total changes during one collection."""


@dataclass(frozen=True, slots=True)
class JolpicaPage:
    """One validated data page."""

    payload: dict[str, Any]
    total: int
    limit: int
    offset: int
    leaf_keys: tuple[Hashable, ...]


@dataclass(frozen=True, slots=True)
class JolpicaPaginationResult:
    """A complete, validated Jolpica pagination result."""

    total: int
    pages: tuple[JolpicaPage, ...]


PageValidator = Callable[[dict[str, Any]], None]
FetchPage = Callable[
    [int, int, int, bool, PageValidator],
    Awaitable[dict[str, Any]],
]
LeafKeys = Callable[[dict[str, Any]], list[Hashable]]


def validate_single_page_jolpica(
    payload: dict[str, Any],
    leaf_keys: LeafKeys,
) -> dict[str, Any]:
    """Validate that one response contains its complete advertised result set."""
    _, total, limit, offset = _metadata(payload, expected_offset=0)
    keys = leaf_keys(payload)
    if total > limit:
        raise JolpicaPaginationError(
            f"Jolpica single-page response advertises {total} leaves "
            f"but its limit is {limit}"
        )
    if len(keys) != total or len(set(keys)) != total:
        raise JolpicaPaginationError(
            "Jolpica single-page response is incomplete: "
            f"raw={len(keys)}, unique={len(set(keys))}, total={total}"
        )
    return payload


def race_leaf_keys(payload: dict[str, Any]) -> list[Hashable]:
    """Return race identities from a Jolpica RaceTable payload."""
    races = payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not isinstance(races, list):
        raise JolpicaPaginationError("Jolpica RaceTable.Races is not a list")
    keys: list[Hashable] = []
    for race in races:
        if not isinstance(race, dict):
            raise JolpicaPaginationError("Jolpica race entry is not an object")
        season = str(race.get("season") or "").strip()
        round_number = str(race.get("round") or "").strip()
        if not season or not round_number:
            raise JolpicaPaginationError("Jolpica race is missing its identity")
        keys.append((season, round_number))
    return keys


def standings_leaf_keys(
    payload: dict[str, Any],
    collection: str,
) -> list[Hashable]:
    """Return driver or constructor identities from a standings payload."""
    lists = (
        payload.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    )
    if not isinstance(lists, list):
        raise JolpicaPaginationError(
            "Jolpica StandingsTable.StandingsLists is not a list"
        )
    identity_field = "Driver" if collection == "DriverStandings" else "Constructor"
    identity_key = "driverId" if collection == "DriverStandings" else "constructorId"
    keys: list[Hashable] = []
    for standings_list in lists:
        if not isinstance(standings_list, dict):
            raise JolpicaPaginationError("Jolpica standings entry is not an object")
        season = str(standings_list.get("season") or "").strip()
        round_number = str(standings_list.get("round") or "").strip()
        rows = standings_list.get(collection, [])
        if not isinstance(rows, list):
            raise JolpicaPaginationError(
                f"Jolpica {collection} collection is not a list"
            )
        for row in rows:
            identity = row.get(identity_field) if isinstance(row, dict) else None
            identity_value = (
                str(identity.get(identity_key) or "").strip()
                if isinstance(identity, dict)
                else ""
            )
            if not season or not round_number or not identity_value:
                raise JolpicaPaginationError(
                    f"Jolpica {collection} leaf is missing its identity"
                )
            keys.append((season, round_number, identity_value))
    return keys


def result_leaf_keys(
    payload: dict[str, Any],
    collection: str,
) -> list[Hashable]:
    """Return result-row identities from a Jolpica RaceTable payload."""
    keys: list[Hashable] = []
    races = (
        payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if isinstance(payload, dict)
        else []
    )
    if not isinstance(races, list):
        raise JolpicaPaginationError("Jolpica RaceTable.Races is not a list")
    for race in races:
        if not isinstance(race, dict):
            raise JolpicaPaginationError("Jolpica race entry is not an object")
        season = str(race.get("season") or "").strip()
        round_number = str(race.get("round") or "").strip()
        rows = race.get(collection, [])
        if not isinstance(rows, list):
            raise JolpicaPaginationError(
                f"Jolpica {collection} collection is not a list"
            )
        for row in rows:
            if not isinstance(row, dict):
                raise JolpicaPaginationError(
                    f"Jolpica {collection} entry is not an object"
                )
            driver = row.get("Driver")
            driver_id = (
                str(driver.get("driverId") or "").strip()
                if isinstance(driver, dict)
                else ""
            )
            if not season or not round_number or not driver_id:
                raise JolpicaPaginationError(
                    f"Jolpica {collection} leaf is missing its identity"
                )
            keys.append((season, round_number, driver_id))
    return keys


def lap_leaf_keys(payload: dict[str, Any]) -> list[Hashable]:
    """Return lap-timing identities from a Jolpica RaceTable payload."""
    keys: list[Hashable] = []
    races = (
        payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if isinstance(payload, dict)
        else []
    )
    if not isinstance(races, list):
        raise JolpicaPaginationError("Jolpica RaceTable.Races is not a list")
    for race in races:
        if not isinstance(race, dict):
            raise JolpicaPaginationError("Jolpica race entry is not an object")
        laps = race.get("Laps", [])
        if not isinstance(laps, list):
            raise JolpicaPaginationError("Jolpica Laps collection is not a list")
        for lap in laps:
            if not isinstance(lap, dict):
                raise JolpicaPaginationError("Jolpica lap entry is not an object")
            lap_number = str(lap.get("number") or "").strip()
            timings = lap.get("Timings", [])
            if not isinstance(timings, list):
                raise JolpicaPaginationError(
                    "Jolpica lap Timings collection is not a list"
                )
            for timing in timings:
                driver_id = (
                    str(timing.get("driverId") or "").strip()
                    if isinstance(timing, dict)
                    else ""
                )
                if not lap_number or not driver_id:
                    raise JolpicaPaginationError(
                        "Jolpica lap timing is missing its identity"
                    )
                keys.append((lap_number, driver_id))
    return keys


def merge_result_pages(
    result: JolpicaPaginationResult,
    collection: str,
) -> dict[str, Any]:
    """Merge result rows split across API pages into deterministic races."""
    races_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    race_table_metadata: dict[str, Any] = {}
    for page in result.pages:
        race_table = page.payload.get("MRData", {}).get("RaceTable", {})
        if not isinstance(race_table, dict):
            raise JolpicaPaginationError("Jolpica RaceTable is not an object")
        if not race_table_metadata:
            race_table_metadata = {
                key: value for key, value in race_table.items() if key != "Races"
            }
        for race in race_table.get("Races", []):
            key = (
                str(race.get("season") or "").strip(),
                str(race.get("round") or "").strip(),
            )
            existing = races_by_key.get(key)
            if existing is None:
                existing = dict(race)
                existing[collection] = []
                races_by_key[key] = existing
            existing[collection].extend(race.get(collection, []))

    def _number(value: Any) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return 2**31 - 1

    races = list(races_by_key.values())
    for race in races:
        race[collection].sort(
            key=lambda row: (
                _number(row.get("position")),
                str((row.get("Driver") or {}).get("driverId") or ""),
            )
        )
    races.sort(
        key=lambda race: (
            _number(race.get("season")),
            _number(race.get("round")),
        )
    )
    return {
        "MRData": {
            "total": str(result.total),
            "limit": str(min(JOLPICA_PAGE_SIZE, max(1, result.total))),
            "offset": "0",
            "RaceTable": {
                **race_table_metadata,
                "Races": races,
            },
        }
    }


def _metadata(
    payload: Any,
    *,
    expected_offset: int,
) -> tuple[dict[str, Any], int, int, int]:
    """Return validated MRData pagination metadata."""
    if not isinstance(payload, dict):
        raise JolpicaPaginationError("Jolpica response is not an object")
    mr_data = payload.get("MRData")
    if not isinstance(mr_data, dict):
        raise JolpicaPaginationError("Jolpica response is missing MRData")

    values: dict[str, int] = {}
    for field in ("total", "limit", "offset"):
        raw = mr_data.get(field)
        if isinstance(raw, bool):
            raise JolpicaPaginationError(
                f"Jolpica pagination field {field} is not numeric"
            )
        try:
            value = int(str(raw))
        except (TypeError, ValueError) as err:
            raise JolpicaPaginationError(
                f"Jolpica pagination field {field} is not numeric"
            ) from err
        if str(raw).strip() not in {str(value), f"+{value}"}:
            raise JolpicaPaginationError(
                f"Jolpica pagination field {field} is not an integer"
            )
        values[field] = value

    total = values["total"]
    limit = values["limit"]
    offset = values["offset"]
    if total < 0:
        raise JolpicaPaginationError("Jolpica total cannot be negative")
    if not 1 <= limit <= JOLPICA_PAGE_SIZE:
        raise JolpicaPaginationError(
            f"Jolpica page limit {limit} is outside the supported range"
        )
    if offset != expected_offset:
        raise JolpicaPaginationError(
            f"Jolpica returned offset {offset}, expected {expected_offset}"
        )
    if offset < 0:
        raise JolpicaPaginationError("Jolpica offset cannot be negative")
    return mr_data, total, limit, offset


def _validate_page(
    payload: dict[str, Any],
    *,
    expected_offset: int,
    authoritative_total: int | None,
    leaf_keys: LeafKeys,
) -> JolpicaPage:
    """Validate one probe or data page and return its leaf keys."""
    _, total, limit, offset = _metadata(payload, expected_offset=expected_offset)
    if authoritative_total is not None and total != authoritative_total:
        raise _JolpicaTotalChanged(
            f"Jolpica total changed from {authoritative_total} to {total}"
        )

    keys = leaf_keys(payload)
    if not isinstance(keys, list):
        raise JolpicaPaginationError("Jolpica leaf extractor returned invalid data")
    expected_count = min(limit, max(0, total - offset))
    if len(keys) != expected_count:
        raise JolpicaPaginationError(
            f"Jolpica page at offset {offset} contains {len(keys)} leaves, "
            f"expected {expected_count}"
        )
    if len(set(keys)) != len(keys):
        raise JolpicaPaginationError(
            f"Jolpica page at offset {offset} contains duplicate leaves"
        )
    if expected_count == 0 and offset < total:
        raise JolpicaPaginationError(
            f"Jolpica returned an empty intermediate page at offset {offset}"
        )
    return JolpicaPage(payload, total, limit, offset, tuple(keys))


async def _validated_fetch(
    fetch_page: FetchPage,
    *,
    limit: int,
    offset: int,
    ttl_seconds: int,
    authoritative_total: int | None,
    leaf_keys: LeafKeys,
    force_refresh: bool,
) -> JolpicaPage:
    """Fetch one page with validation applied before it can be cached."""

    def _validator(payload: dict[str, Any]) -> None:
        _validate_page(
            payload,
            expected_offset=offset,
            authoritative_total=authoritative_total,
            leaf_keys=leaf_keys,
        )

    payload = await fetch_page(
        limit,
        offset,
        ttl_seconds,
        force_refresh,
        _validator,
    )
    return _validate_page(
        payload,
        expected_offset=offset,
        authoritative_total=authoritative_total,
        leaf_keys=leaf_keys,
    )


async def async_paginate_jolpica(
    fetch_page: FetchPage,
    leaf_keys: LeafKeys,
    *,
    ttl_stable: int,
    ttl_recent: int,
    ttl_latest: int,
    ttl_probe: int | None = None,
    page_cap: int = JOLPICA_PAGE_CAP,
) -> JolpicaPaginationResult:
    """Fetch all leaves atomically using a probe and strict page validation.

    A total change causes one forced probe and one full restart. No page is
    returned unless the raw and unique leaf counts match the authoritative total.
    """
    if page_cap < 1:
        raise JolpicaPaginationError("Jolpica page cap must be positive")

    last_total_error: _JolpicaTotalChanged | None = None
    for collection_attempt in range(2):
        force_probe = collection_attempt > 0
        probe = await _validated_fetch(
            fetch_page,
            limit=1,
            offset=0,
            ttl_seconds=ttl_probe if ttl_probe is not None else ttl_latest,
            authoritative_total=None,
            leaf_keys=leaf_keys,
            force_refresh=force_probe,
        )
        authoritative_total = probe.total
        if authoritative_total == 0:
            return JolpicaPaginationResult(total=0, pages=())

        pages: list[JolpicaPage] = []
        all_keys: list[Hashable] = []
        offset = 0
        seen_offsets: set[int] = set()

        try:
            while offset < authoritative_total:
                if len(pages) >= page_cap:
                    raise JolpicaPaginationError(
                        f"Jolpica pagination exceeded the {page_cap}-page cap"
                    )
                if offset in seen_offsets:
                    raise JolpicaPaginationError(
                        f"Jolpica pagination repeated offset {offset}"
                    )
                seen_offsets.add(offset)

                expected_last_offset = (
                    (authoritative_total - 1) // JOLPICA_PAGE_SIZE
                ) * JOLPICA_PAGE_SIZE
                if offset >= expected_last_offset:
                    ttl_seconds = ttl_latest
                elif offset + (2 * JOLPICA_PAGE_SIZE) > authoritative_total:
                    ttl_seconds = ttl_recent
                else:
                    ttl_seconds = ttl_stable

                page = await _validated_fetch(
                    fetch_page,
                    limit=JOLPICA_PAGE_SIZE,
                    offset=offset,
                    ttl_seconds=ttl_seconds,
                    authoritative_total=authoritative_total,
                    leaf_keys=leaf_keys,
                    force_refresh=force_probe,
                )
                pages.append(page)
                all_keys.extend(page.leaf_keys)
                next_offset = page.offset + page.limit
                if next_offset <= offset:
                    raise JolpicaPaginationError("Jolpica pagination did not advance")
                offset = next_offset
        except _JolpicaTotalChanged as err:
            last_total_error = err
            continue

        raw_count = len(all_keys)
        unique_count = len(set(all_keys))
        if raw_count != authoritative_total or unique_count != authoritative_total:
            raise JolpicaPaginationError(
                "Jolpica pagination is incomplete: "
                f"raw={raw_count}, unique={unique_count}, "
                f"total={authoritative_total}"
            )
        return JolpicaPaginationResult(
            total=authoritative_total,
            pages=tuple(pages),
        )

    raise JolpicaPaginationError(
        str(last_total_error or "Jolpica total changed repeatedly")
    )
