"""Behavior matrix for Jolpica pagination validation failures."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.f1_sensor.jolpica_pagination import (
    JolpicaPage,
    JolpicaPaginationError,
    JolpicaPaginationResult,
    _metadata,
    _validate_page,
    async_paginate_jolpica,
    lap_leaf_keys,
    merge_result_pages,
    race_leaf_keys,
    result_leaf_keys,
    standings_leaf_keys,
    validate_single_page_jolpica,
)


def _payload(*, total=1, limit=1, offset=0, table=None) -> dict[str, Any]:
    return {
        "MRData": {
            "total": str(total),
            "limit": str(limit),
            "offset": str(offset),
            **(table or {}),
        }
    }


def test_single_page_and_race_identity_validation() -> None:
    good = _payload(table={"RaceTable": {"Races": [{"season": "2026", "round": "1"}]}})
    assert validate_single_page_jolpica(good, race_leaf_keys) is good
    with pytest.raises(JolpicaPaginationError, match="advertises"):
        validate_single_page_jolpica(_payload(total=2), lambda _payload: [1])
    with pytest.raises(JolpicaPaginationError, match="incomplete"):
        validate_single_page_jolpica(_payload(total=1), lambda _payload: [])
    with pytest.raises(JolpicaPaginationError, match="Races is not a list"):
        race_leaf_keys(_payload(table={"RaceTable": {"Races": {}}}))
    with pytest.raises(JolpicaPaginationError, match="entry is not an object"):
        race_leaf_keys(_payload(table={"RaceTable": {"Races": ["bad"]}}))
    with pytest.raises(JolpicaPaginationError, match="missing its identity"):
        race_leaf_keys(_payload(table={"RaceTable": {"Races": [{}]}}))


def test_standings_result_and_lap_identity_validation() -> None:
    with pytest.raises(JolpicaPaginationError, match="StandingsLists is not a list"):
        standings_leaf_keys(
            _payload(table={"StandingsTable": {"StandingsLists": {}}}),
            "DriverStandings",
        )
    with pytest.raises(JolpicaPaginationError, match="entry is not an object"):
        standings_leaf_keys(
            _payload(table={"StandingsTable": {"StandingsLists": ["bad"]}}),
            "DriverStandings",
        )
    with pytest.raises(JolpicaPaginationError, match="collection is not a list"):
        standings_leaf_keys(
            _payload(
                table={
                    "StandingsTable": {
                        "StandingsLists": [
                            {"season": "2026", "round": "1", "DriverStandings": {}}
                        ]
                    }
                }
            ),
            "DriverStandings",
        )
    with pytest.raises(JolpicaPaginationError, match="missing its identity"):
        standings_leaf_keys(
            _payload(
                table={
                    "StandingsTable": {
                        "StandingsLists": [
                            {"season": "2026", "round": "1", "DriverStandings": [{}]}
                        ]
                    }
                }
            ),
            "DriverStandings",
        )

    race_table = lambda rows: {  # noqa: E731
        "RaceTable": {"Races": [{"season": "2026", "round": "1", **rows}]}
    }
    with pytest.raises(JolpicaPaginationError, match="collection is not a list"):
        result_leaf_keys(_payload(table=race_table({"Results": {}})), "Results")
    with pytest.raises(JolpicaPaginationError, match="entry is not an object"):
        result_leaf_keys(_payload(table=race_table({"Results": ["bad"]})), "Results")
    with pytest.raises(JolpicaPaginationError, match="missing its identity"):
        result_leaf_keys(_payload(table=race_table({"Results": [{}]})), "Results")
    with pytest.raises(JolpicaPaginationError, match="Laps collection"):
        lap_leaf_keys(_payload(table=race_table({"Laps": {}})))
    with pytest.raises(JolpicaPaginationError, match="lap entry"):
        lap_leaf_keys(_payload(table=race_table({"Laps": ["bad"]})))
    with pytest.raises(JolpicaPaginationError, match="Timings collection"):
        lap_leaf_keys(
            _payload(table=race_table({"Laps": [{"number": "1", "Timings": {}}]}))
        )
    with pytest.raises(JolpicaPaginationError, match="missing its identity"):
        lap_leaf_keys(
            _payload(table=race_table({"Laps": [{"number": "1", "Timings": [{}]}]}))
        )
    assert standings_leaf_keys(
        _payload(
            table={
                "StandingsTable": {
                    "StandingsLists": [
                        {
                            "season": "2026",
                            "round": "1",
                            "ConstructorStandings": [
                                {"Constructor": {"constructorId": "mclaren"}}
                            ],
                        }
                    ]
                }
            }
        ),
        "ConstructorStandings",
    ) == [("2026", "1", "mclaren")]
    with pytest.raises(JolpicaPaginationError, match="Races is not a list"):
        result_leaf_keys(_payload(table={"RaceTable": {"Races": {}}}), "Results")
    with pytest.raises(JolpicaPaginationError, match="entry is not an object"):
        result_leaf_keys(_payload(table={"RaceTable": {"Races": ["bad"]}}), "Results")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "not an object"),
        ({}, "missing MRData"),
        (_payload(total=True), "not numeric"),
        (_payload(total="1.0"), "not numeric"),
        (_payload(total="01"), "not an integer"),
        (_payload(total=-1), "cannot be negative"),
        (_payload(limit=0), "outside the supported range"),
        (_payload(offset=1), "returned offset"),
    ],
)
def test_metadata_rejects_invalid_pagination_contracts(payload, message) -> None:
    with pytest.raises(JolpicaPaginationError, match=message):
        _metadata(payload, expected_offset=0)


def test_page_validator_and_merge_defensive_paths() -> None:
    payload = _payload()
    with pytest.raises(JolpicaPaginationError, match="extractor returned invalid"):
        _validate_page(
            payload,
            expected_offset=0,
            authoritative_total=1,
            leaf_keys=lambda _payload: "bad",
        )

    invalid_page = JolpicaPage(
        _payload(table={"RaceTable": []}), 1, 1, 0, (("2026", "1"),)
    )
    with pytest.raises(JolpicaPaginationError, match="RaceTable is not an object"):
        merge_result_pages(JolpicaPaginationResult(1, (invalid_page,)), "Results")

    page = JolpicaPage(
        _payload(
            table={
                "RaceTable": {
                    "Races": [
                        {
                            "season": "bad",
                            "round": "bad",
                            "Results": [
                                {"position": "bad", "Driver": {"driverId": "x"}}
                            ],
                        }
                    ]
                }
            }
        ),
        1,
        1,
        0,
        (("bad", "bad", "x"),),
    )
    merged = merge_result_pages(JolpicaPaginationResult(1, (page,)), "Results")
    assert merged["MRData"]["RaceTable"]["Races"][0]["Results"][0]["position"] == "bad"

    with pytest.raises(JolpicaPaginationError, match="cannot be negative"):
        _metadata(_payload(offset=-1), expected_offset=-1)
    with pytest.raises(JolpicaPaginationError, match="contains 0 leaves"):
        _validate_page(
            _payload(total=1),
            expected_offset=0,
            authoritative_total=1,
            leaf_keys=lambda _payload: [],
        )
    with pytest.raises(JolpicaPaginationError, match="duplicate leaves"):
        _validate_page(
            _payload(total=2, limit=2),
            expected_offset=0,
            authoritative_total=2,
            leaf_keys=lambda _payload: ["x", "x"],
        )


@pytest.mark.asyncio
async def test_pagination_rejects_non_positive_page_cap() -> None:
    async def _fetch(*_args):
        return _payload(total=0)

    with pytest.raises(JolpicaPaginationError, match="page cap must be positive"):
        await async_paginate_jolpica(
            _fetch,
            lambda _payload: [],
            ttl_stable=3,
            ttl_recent=2,
            ttl_latest=1,
            page_cap=0,
        )


async def test_pagination_uses_all_ttl_bands_and_rejects_repeated_total_change() -> (
    None
):
    calls = []

    async def fetch(limit, offset, ttl, force, validator):
        calls.append((limit, offset, ttl, force))
        total = 250
        count = 1 if limit == 1 else min(limit, total - offset)
        payload = _payload(total=total, limit=limit, offset=offset)
        payload["keys"] = list(range(offset, offset + count))
        validator(payload)
        return payload

    result = await async_paginate_jolpica(
        fetch,
        lambda payload: payload["keys"],
        ttl_stable=30,
        ttl_recent=20,
        ttl_latest=10,
    )
    assert result.total == 250
    assert [call[2] for call in calls[1:]] == [30, 20, 10]

    probe_totals = iter((2, 4))

    async def changing(limit, offset, _ttl, _force, _validator):
        if limit == 1:
            total = next(probe_totals)
            payload = _payload(total=total, limit=1, offset=0)
            payload["keys"] = [0]
            return payload
        payload = _payload(total=99, limit=limit, offset=offset)
        payload["keys"] = list(range(min(limit, 99 - offset)))
        return payload

    with pytest.raises(JolpicaPaginationError, match="total changed"):
        await async_paginate_jolpica(
            changing,
            lambda payload: payload["keys"],
            ttl_stable=3,
            ttl_recent=2,
            ttl_latest=1,
        )
