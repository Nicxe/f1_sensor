"""Contract tests for strict Jolpica pagination."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import pytest

from custom_components.f1_sensor.jolpica_pagination import (
    JolpicaPaginationError,
    async_paginate_jolpica,
    lap_leaf_keys,
    merge_result_pages,
    result_leaf_keys,
)


def _result_payload(
    *,
    total: int,
    limit: int,
    offset: int,
    driver_ids: list[str],
    collection: str = "Results",
) -> dict[str, Any]:
    return {
        "MRData": {
            "total": str(total),
            "limit": str(limit),
            "offset": str(offset),
            "RaceTable": {
                "season": "2025",
                "Races": [
                    {
                        "season": "2025",
                        "round": "6",
                        "raceName": "Miami Grand Prix",
                        collection: [
                            {
                                "position": str(index + offset + 1),
                                "Driver": {"driverId": driver_id},
                            }
                            for index, driver_id in enumerate(driver_ids)
                        ],
                    }
                ]
                if driver_ids
                else [],
            },
        }
    }


def _result_fetcher(
    driver_ids: list[str],
    *,
    server_limit: int = 100,
    collection: str = "Results",
):
    calls: list[tuple[int, int, int, bool]] = []

    async def _fetch(
        limit: int,
        offset: int,
        ttl: int,
        force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        calls.append((limit, offset, ttl, force_refresh))
        response_limit = min(limit, server_limit)
        rows = driver_ids[offset : offset + response_limit]
        payload = _result_payload(
            total=len(driver_ids),
            limit=response_limit,
            offset=offset,
            driver_ids=rows,
            collection=collection,
        )
        validator(payload)
        return payload

    return _fetch, calls


@pytest.mark.asyncio
async def test_results_over_100_merge_one_race_split_between_pages() -> None:
    drivers = [f"driver_{index}" for index in range(120)]
    fetch, calls = _result_fetcher(drivers)

    paginated = await async_paginate_jolpica(
        fetch,
        lambda payload: result_leaf_keys(payload, "Results"),
        ttl_stable=300,
        ttl_recent=200,
        ttl_latest=100,
    )
    payload = merge_result_pages(paginated, "Results")

    races = payload["MRData"]["RaceTable"]["Races"]
    assert paginated.total == 120
    assert len(races) == 1
    assert len(races[0]["Results"]) == 120
    assert [(limit, offset) for limit, offset, _, _ in calls] == [
        (1, 0),
        (100, 0),
        (100, 100),
    ]


@pytest.mark.asyncio
async def test_server_limit_below_100_advances_by_returned_limit() -> None:
    drivers = [f"driver_{index}" for index in range(5)]
    fetch, calls = _result_fetcher(drivers, server_limit=2)

    result = await async_paginate_jolpica(
        fetch,
        lambda payload: result_leaf_keys(payload, "Results"),
        ttl_stable=300,
        ttl_recent=200,
        ttl_latest=100,
    )

    assert result.total == 5
    assert [(limit, offset) for limit, offset, _, _ in calls] == [
        (1, 0),
        (100, 0),
        (100, 2),
        (100, 4),
    ]


@pytest.mark.asyncio
async def test_sprint_120_rows_are_complete() -> None:
    drivers = [f"sprint_driver_{index}" for index in range(120)]
    fetch, _ = _result_fetcher(drivers, collection="SprintResults")

    paginated = await async_paginate_jolpica(
        fetch,
        lambda payload: result_leaf_keys(payload, "SprintResults"),
        ttl_stable=300,
        ttl_recent=200,
        ttl_latest=100,
    )
    payload = merge_result_pages(paginated, "SprintResults")

    assert len(payload["MRData"]["RaceTable"]["Races"][0]["SprintResults"]) == 120


@pytest.mark.asyncio
async def test_lap_split_between_pages_merges_unique_timings() -> None:
    timings = [
        ("1", "driver_a"),
        ("1", "driver_b"),
        ("2", "driver_a"),
        ("2", "driver_b"),
    ]

    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        _force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        response_limit = min(limit, 3)
        selected = timings[offset : offset + response_limit]
        laps: dict[str, list[dict[str, str]]] = {}
        for lap_number, driver_id in selected:
            laps.setdefault(lap_number, []).append(
                {"driverId": driver_id, "position": "1"}
            )
        payload = {
            "MRData": {
                "total": "4",
                "limit": str(response_limit),
                "offset": str(offset),
                "RaceTable": {
                    "Races": [
                        {
                            "season": "2025",
                            "round": "1",
                            "Laps": [
                                {"number": number, "Timings": values}
                                for number, values in laps.items()
                            ],
                        }
                    ]
                },
            }
        }
        validator(payload)
        return payload

    result = await async_paginate_jolpica(
        _fetch,
        lap_leaf_keys,
        ttl_stable=300,
        ttl_recent=200,
        ttl_latest=100,
    )

    assert [key for page in result.pages for key in page.leaf_keys] == timings


@pytest.mark.asyncio
async def test_total_change_forces_one_full_restart() -> None:
    calls = 0

    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        total = 3 if force_refresh or calls > 1 else 2
        ids = [f"driver_{index}" for index in range(total)][offset : offset + limit]
        payload = _result_payload(
            total=total,
            limit=limit,
            offset=offset,
            driver_ids=ids,
        )
        validator(payload)
        return payload

    result = await async_paginate_jolpica(
        _fetch,
        lambda payload: result_leaf_keys(payload, "Results"),
        ttl_stable=300,
        ttl_recent=200,
        ttl_latest=100,
    )

    assert result.total == 3
    assert calls == 4


@pytest.mark.asyncio
async def test_second_total_change_fails_closed() -> None:
    calls = 0

    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        _force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        total = (2, 3, 3, 4)[calls - 1]
        ids = [f"driver_{index}" for index in range(total)][offset : offset + limit]
        payload = _result_payload(
            total=total,
            limit=limit,
            offset=offset,
            driver_ids=ids,
        )
        validator(payload)
        return payload

    with pytest.raises(JolpicaPaginationError, match="total changed"):
        await async_paginate_jolpica(
            _fetch,
            lambda payload: result_leaf_keys(payload, "Results"),
            ttl_stable=300,
            ttl_recent=200,
            ttl_latest=100,
        )

    assert calls == 4


@pytest.mark.asyncio
async def test_empty_intermediate_page_fails_closed() -> None:
    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        _force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        ids = ["driver_0"] if limit == 1 else []
        payload = _result_payload(
            total=150,
            limit=limit,
            offset=offset,
            driver_ids=ids,
        )
        validator(payload)
        return payload

    with pytest.raises(JolpicaPaginationError, match="contains 0 leaves"):
        await async_paginate_jolpica(
            _fetch,
            lambda payload: result_leaf_keys(payload, "Results"),
            ttl_stable=300,
            ttl_recent=200,
            ttl_latest=100,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("limit", "0"),
        ("limit", "101"),
        ("offset", "7"),
        ("total", "invalid"),
    ],
)
async def test_invalid_metadata_fails_closed_after_one_forced_refetch(
    field: str,
    value: str,
) -> None:
    calls: list[bool] = []

    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        calls.append(force_refresh)
        payload = _result_payload(
            total=1,
            limit=limit,
            offset=offset,
            driver_ids=["driver_0"],
        )
        payload["MRData"][field] = value
        validator(payload)
        return payload

    with pytest.raises(JolpicaPaginationError):
        await async_paginate_jolpica(
            _fetch,
            lambda payload: result_leaf_keys(payload, "Results"),
            ttl_stable=300,
            ttl_recent=200,
            ttl_latest=100,
        )

    assert calls == [False]


@pytest.mark.asyncio
async def test_invalid_cached_page_is_refetched_once() -> None:
    calls: list[tuple[int, bool]] = []

    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        calls.append((offset, force_refresh))
        ids = ["driver_0"] if limit == 1 else ["driver_0", "driver_1"]
        if limit != 1 and not force_refresh:
            stale = _result_payload(
                total=2,
                limit=limit,
                offset=offset,
                driver_ids=["driver_0"],
            )
            with pytest.raises(JolpicaPaginationError):
                validator(stale)
            calls.append((offset, True))
        payload = _result_payload(
            total=2,
            limit=limit,
            offset=offset,
            driver_ids=ids,
        )
        validator(payload)
        return payload

    result = await async_paginate_jolpica(
        _fetch,
        lambda payload: result_leaf_keys(payload, "Results"),
        ttl_stable=300,
        ttl_recent=200,
        ttl_latest=100,
    )

    assert result.total == 2
    assert calls == [(0, False), (0, False), (0, True)]


@pytest.mark.asyncio
async def test_duplicate_or_gap_never_returns_collected_partial_data() -> None:
    keys: list[Hashable] = [
        ("2025", "1", "driver_a"),
        ("2025", "1", "driver_a"),
    ]

    async def _fetch(
        limit: int,
        offset: int,
        _ttl: int,
        _force_refresh: bool,
        validator,
    ) -> dict[str, Any]:
        selected = keys[offset : offset + limit]
        payload = _result_payload(
            total=2,
            limit=limit,
            offset=offset,
            driver_ids=[str(key[2]) for key in selected],
        )
        validator(payload)
        return payload

    with pytest.raises(JolpicaPaginationError, match="duplicate|incomplete"):
        await async_paginate_jolpica(
            _fetch,
            lambda payload: result_leaf_keys(payload, "Results"),
            ttl_stable=300,
            ttl_recent=200,
            ttl_latest=100,
        )


@pytest.mark.asyncio
async def test_page_cap_fails_closed() -> None:
    fetch, _ = _result_fetcher(
        [f"driver_{index}" for index in range(3)],
        server_limit=1,
    )

    with pytest.raises(JolpicaPaginationError, match="page cap"):
        await async_paginate_jolpica(
            fetch,
            lambda payload: result_leaf_keys(payload, "Results"),
            ttl_stable=300,
            ttl_recent=200,
            ttl_latest=100,
            page_cap=2,
        )
