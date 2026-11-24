"""Lazy source demand shares reads, releases parents and cancels on unload."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from custom_components.f1_sensor.card_data_sources import CardDataSources


def source(data=None, success=True):
    item = SimpleNamespace(
        data=data, last_update_success=success, async_start=Mock(), async_stop=Mock()
    )

    async def refresh():
        item.data = {"loaded": True}

    item.async_refresh = AsyncMock(side_effect=refresh)
    return item


async def test_shared_first_read_and_parent_order(hass):
    race, weather, standings = source(), source(), source({"cached": True})
    calls = []

    async def read_race():
        weather.async_start.assert_not_called()
        calls.append("race")
        race.data = {"ready": True}

    async def read_weather():
        weather.async_start.assert_called_once()
        assert race.data
        calls.append("weather")
        weather.data = {"ready": True}

    race.async_refresh.side_effect = read_race
    weather.async_refresh.side_effect = read_weather
    owner = CardDataSources(
        hass,
        {
            "race_coordinator": race,
            "race_weather_coordinator": weather,
            "driver_coordinator": standings,
            "unused": None,
        },
        set(),
    )
    assert not owner.required
    owner.reconcile(
        {"race_coordinator", "race_weather_coordinator", "driver_coordinator"}
    )
    owner.reconcile(
        {"race_coordinator", "race_weather_coordinator", "driver_coordinator"}
    )
    await hass.async_block_till_done()
    assert calls == ["race", "weather"]
    standings.async_refresh.assert_not_called()
    owner.reconcile(set())
    weather.async_stop.assert_called_once()
    assert not owner.required
    assert not owner.is_needed(race)
    assert not owner.is_needed(object())
    await owner.async_close()
    owner.reconcile({"race_coordinator"})
    assert not owner.required


async def test_removed_demand_is_skipped_before_fetch(hass):
    race = source()
    owner = CardDataSources(hass, {"race_coordinator": race}, set())
    owner.reconcile({"race_coordinator"})
    owner.reconcile(set())
    await hass.async_block_till_done()
    race.async_refresh.assert_not_called()
    await owner.async_close()


async def test_new_demand_during_fetch_and_failed_source_retry(hass):
    race, driver = source(), source({"old": True}, False)
    waiting, release = asyncio.Event(), asyncio.Event()

    async def read():
        waiting.set()
        await release.wait()
        race.data = {"ready": True}

    race.async_refresh.side_effect = read
    owner = CardDataSources(
        hass, {"race_coordinator": race, "driver_coordinator": driver}, set()
    )
    owner.reconcile({"race_coordinator"})
    await waiting.wait()
    owner.reconcile({"race_coordinator", "driver_coordinator"})
    release.set()
    await hass.async_block_till_done()
    driver.async_refresh.assert_awaited_once()
    await owner.async_close()


async def test_unload_cancels_first_read_before_source_teardown(hass):
    race = source()
    waiting = asyncio.Event()
    cancelled = asyncio.Event()

    async def read():
        waiting.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    race.async_refresh.side_effect = read
    owner = CardDataSources(hass, {"race_coordinator": race}, set())
    owner.reconcile({"race_coordinator"})
    await waiting.wait()
    await owner.async_close()
    await owner.async_close()
    assert cancelled.is_set()
    assert owner._task is None


async def test_sensor_demand_retains_parent_and_first_data(hass):
    history = source({"cached": True})
    owner = CardDataSources(
        hass,
        {"next_race_history_coordinator": history},
        {"next_race_history_coordinator"},
    )
    owner.reconcile(set())
    owner.reconcile(set())
    assert owner.is_needed(history)
    history.async_refresh.assert_not_called()
    history.async_stop.assert_not_called()
    await owner.async_close()


async def test_later_client_can_request_another_source_after_fast_cached_read(hass):
    race, driver = source(), source()
    owner = CardDataSources(
        hass, {"race_coordinator": race, "driver_coordinator": driver}, set()
    )
    owner.reconcile({"race_coordinator"})
    await hass.async_block_till_done()
    owner.reconcile({"driver_coordinator"})
    await hass.async_block_till_done()
    driver.async_refresh.assert_awaited_once()
    await owner.async_close()


async def test_reopening_after_source_interval_refreshes_but_recent_cache_is_reused(
    hass, monkeypatch
):
    now = 100.0
    monkeypatch.setattr(
        "custom_components.f1_sensor.card_data_sources.monotonic", lambda: now
    )
    driver = source({"cached": True})
    owner = CardDataSources(hass, {"driver_coordinator": driver}, set())
    owner.reconcile({"driver_coordinator"})
    await hass.async_block_till_done()
    driver.async_refresh.assert_not_called()
    owner.reconcile(set())
    now += 3601
    owner.reconcile({"driver_coordinator"})
    await hass.async_block_till_done()
    driver.async_refresh.assert_awaited_once()
    owner.mark_updated("unknown")
    owner.reconcile(set())
    now += 1
    owner.reconcile({"driver_coordinator"})
    await hass.async_block_till_done()
    driver.async_refresh.assert_awaited_once()
    await owner.async_close()


async def test_independent_sources_load_concurrently_after_parent_stage(hass):
    driver, constructor = source(), source()
    driver_started, constructor_started = asyncio.Event(), asyncio.Event()

    async def read_driver():
        driver_started.set()
        await constructor_started.wait()
        driver.data = {"loaded": True}

    async def read_constructor():
        constructor_started.set()
        await driver_started.wait()
        constructor.data = {"loaded": True}

    driver.async_refresh.side_effect = read_driver
    constructor.async_refresh.side_effect = read_constructor
    owner = CardDataSources(
        hass,
        {"driver_coordinator": driver, "constructor_coordinator": constructor},
        set(),
    )
    owner.reconcile({"driver_coordinator", "constructor_coordinator"})
    await asyncio.wait_for(hass.async_block_till_done(), 3)
    driver.async_refresh.assert_awaited_once()
    constructor.async_refresh.assert_awaited_once()
    await owner.async_close()


async def test_slow_sprint_does_not_block_weather_first_read(hass):
    race, sprint, weather, laps = source(), source(), source(), source()
    weather_ready, release_sprint = asyncio.Event(), asyncio.Event()

    async def read_sprint():
        await release_sprint.wait()
        sprint.data = {"loaded": True}

    async def read_weather():
        assert race.data is not None
        weather.data = {"loaded": True}
        weather_ready.set()

    sprint.async_refresh.side_effect = read_sprint
    weather.async_refresh.side_effect = read_weather
    sources = {
        "race_coordinator": race,
        "sprint_results_coordinator": sprint,
        "race_weather_coordinator": weather,
        "lap_position_progression_coordinator": laps,
    }
    owner = CardDataSources(hass, sources, set(sources))
    try:
        owner.reconcile(set())
        await asyncio.wait_for(weather_ready.wait(), timeout=1)
        laps.async_refresh.assert_not_awaited()
        release_sprint.set()
        await hass.async_block_till_done()
        laps.async_refresh.assert_awaited_once()
    finally:
        await owner.async_close()
