"""Tests for config-entry storage ownership."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.f1_sensor.storage import (
    async_remove_entry_storage,
    entry_storage_keys,
)


def test_entry_storage_keys_are_narrowly_scoped() -> None:
    keys = entry_storage_keys("entry-123")

    assert keys == (
        "f1_sensor_entry-123_http_cache_v1",
        "f1_sensor_entry-123_live_delay_v1",
        "f1_sensor_entry-123_live_delay_reference_v1",
        "f1_sensor_entry-123_replay_start_reference_v1",
        "f1_sensor_entry-123_race_control_log_v1",
        "f1_sensor_entry-123_favorite_driver_v1",
    )


@pytest.mark.asyncio
async def test_remove_entry_storage_removes_every_owned_store(hass) -> None:
    stores: list[tuple[str, AsyncMock]] = []

    def _store(_hass, _version, key):
        remove = AsyncMock()
        stores.append((key, remove))
        return type("FakeStore", (), {"async_remove": remove})()

    with patch("custom_components.f1_sensor.storage.Store", side_effect=_store):
        await async_remove_entry_storage(hass, "entry-123")

    assert [key for key, _remove in stores] == list(entry_storage_keys("entry-123"))
    assert all(remove.await_count == 1 for _key, remove in stores)
