from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.const import (
    LIVE_DELAY_REFERENCE_FORMATION,
    LIVE_DELAY_REFERENCE_LAP_SYNC,
    LIVE_DELAY_REFERENCE_SESSION,
)
from custom_components.f1_sensor.live_delay import LiveDelayReferenceController
from custom_components.f1_sensor.select import F1LiveDelayReferenceSelect


@pytest.mark.asyncio
async def test_live_delay_reference_controller_migrates_legacy_formation_value(
    hass,
) -> None:
    controller = LiveDelayReferenceController(hass, "entry-id")
    await controller._store.async_save({"reference": LIVE_DELAY_REFERENCE_FORMATION})

    value = await controller.async_initialize(LIVE_DELAY_REFERENCE_FORMATION)
    await hass.async_block_till_done()

    assert value == LIVE_DELAY_REFERENCE_SESSION
    assert controller.current == LIVE_DELAY_REFERENCE_SESSION
    assert await controller._store.async_load() == {
        "reference": LIVE_DELAY_REFERENCE_SESSION
    }


def test_live_delay_reference_select_exposes_supported_options_only() -> None:
    entity = F1LiveDelayReferenceSelect(
        SimpleNamespace(current=LIVE_DELAY_REFERENCE_SESSION),
        "unique-id",
        "entry-id",
        "F1",
    )

    assert entity.options == [
        "Session live",
        "Lap sync (race/sprint)",
    ]


def test_live_delay_reference_select_falls_back_from_legacy_formation_value() -> None:
    entity = F1LiveDelayReferenceSelect(
        SimpleNamespace(current=LIVE_DELAY_REFERENCE_FORMATION),
        "unique-id",
        "entry-id",
        "F1",
    )

    assert entity.current_option == "Session live"
    assert LIVE_DELAY_REFERENCE_LAP_SYNC in entity._value_to_option
