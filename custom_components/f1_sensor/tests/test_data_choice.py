"""Automatic card data informs once without pausing or changing sensor choices."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.data_choice import (
    CONF_CARD_DATA_NOTICE_VERSION,
    async_dismiss_card_data_notice,
    async_notify_card_data,
    notification_id,
)

TEXTS = {
    "component.f1_sensor.exceptions.card_data_notification_title.message": "Automatic card data",
    "component.f1_sensor.exceptions.card_data_notification.message": "{name}: no configuration required. {integration_url}",
}


@pytest.fixture
def entry(hass, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=4,
        minor_version=4,
        data={"sensor_name": "F1", "enabled_sensors": ["race_week"]},
        options={"disabled_sensors": ["driver_standings"]},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize("old_version", [None, False, "1", 0, -1])
async def test_information_is_once_and_never_repeats_after_dismissal(
    entry, hass, old_version
):
    old_data = {**entry.data, CONF_CARD_DATA_NOTICE_VERSION: old_version}
    options = dict(entry.options)
    hass.config_entries.async_update_entry(entry, data=old_data)
    with (
        patch(
            "custom_components.f1_sensor.data_choice.async_get_translations",
            AsyncMock(return_value=TEXTS),
        ),
        patch(
            "custom_components.f1_sensor.data_choice.persistent_notification.async_create"
        ) as create,
    ):
        await async_notify_card_data(hass, entry)
        assert create.call_count == 1
        assert create.call_args.kwargs["notification_id"] == notification_id(
            entry.entry_id
        )
        persistent_notification.async_dismiss_all(hass)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(days=2))
        await hass.async_block_till_done()
        await async_notify_card_data(hass, entry)
        assert create.call_count == 1
    assert entry.options == options
    assert dict(entry.data) == {**old_data, CONF_CARD_DATA_NOTICE_VERSION: 1}
    assert "data_choice_version" not in entry.data


async def test_disabled_entry_does_not_show_information(entry, hass):
    await hass.config_entries.async_set_disabled_by(
        entry.entry_id, ConfigEntryDisabler.USER
    )
    with patch(
        "custom_components.f1_sensor.data_choice.persistent_notification.async_create"
    ) as create:
        await async_notify_card_data(hass, entry)
        create.assert_not_called()
    assert CONF_CARD_DATA_NOTICE_VERSION not in entry.data


@pytest.mark.parametrize("change", ["informed", "disabled", "removed"])
async def test_translation_race_rechecks_entry(entry, hass, change):
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def translate(*args):
        waiting.set()
        await release.wait()
        return TEXTS

    with (
        patch(
            "custom_components.f1_sensor.data_choice.async_get_translations", translate
        ),
        patch(
            "custom_components.f1_sensor.data_choice.persistent_notification.async_create"
        ) as create,
    ):
        task = hass.async_create_task(async_notify_card_data(hass, entry))
        await waiting.wait()
        if change == "informed":
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_CARD_DATA_NOTICE_VERSION: 1}
            )
        elif change == "disabled":
            await hass.config_entries.async_set_disabled_by(
                entry.entry_id, ConfigEntryDisabler.USER
            )
        else:
            await hass.config_entries.async_remove(entry.entry_id)
        release.set()
        await task
        create.assert_not_called()


async def test_english_fallback_and_removal_clear_obsolete_notice(entry, hass):
    with (
        patch(
            "custom_components.f1_sensor.data_choice.async_get_translations",
            AsyncMock(side_effect=[{}, TEXTS]),
        ) as translate,
        patch(
            "custom_components.f1_sensor.data_choice.persistent_notification.async_create"
        ) as create,
        patch(
            "custom_components.f1_sensor.data_choice.persistent_notification.async_dismiss"
        ) as dismiss,
    ):
        await async_notify_card_data(hass, entry)
        assert translate.call_args.args[1] == "en"
        create.assert_called_once()
        async_dismiss_card_data_notice(hass, entry.entry_id)
        assert any(
            call.args[1] == notification_id(entry.entry_id)
            for call in dismiss.call_args_list
        )
        assert any(
            call.args[1] == f"f1_sensor_data_choice_{entry.entry_id}_v1"
            for call in dismiss.call_args_list
        )


async def test_unavailable_translation_never_blocks_or_acknowledges_information(
    entry, hass
):
    with (
        patch(
            "custom_components.f1_sensor.data_choice.async_get_translations",
            AsyncMock(return_value={}),
        ),
        patch(
            "custom_components.f1_sensor.data_choice.persistent_notification.async_create"
        ) as create,
    ):
        await async_notify_card_data(hass, entry)
        create.assert_not_called()
    assert CONF_CARD_DATA_NOTICE_VERSION not in entry.data
