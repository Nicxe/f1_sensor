from __future__ import annotations

from typing import Any

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.entity_map_websocket import (
    ENTITY_MAP_WS_MARKER,
    _ws_get_entity_map,
    async_register_entity_map_websocket,
)


class _Connection:
    def __init__(self) -> None:
        self.results: list[tuple[int, Any]] = []

    def send_result(self, msg_id: int, result: Any) -> None:
        self.results.append((msg_id, result))


async def test_entity_map_groups_registry_entities_by_config_entry(hass) -> None:
    first = MockConfigEntry(domain=DOMAIN, title="Living room F1", entry_id="first")
    second = MockConfigEntry(domain=DOMAIN, title="Office F1", entry_id="second")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    registry = er.async_get(hass)
    first_driver = registry.async_get_or_create(
        "sensor", DOMAIN, "first_driver_list", config_entry=first
    )
    second_driver = registry.async_get_or_create(
        "sensor", DOMAIN, "second_driver_list", config_entry=second
    )
    registry.async_get_or_create("sensor", DOMAIN, "unrelated", config_entry=first)
    connection = _Connection()

    _ws_get_entity_map(hass, connection, {"id": 7, "type": "f1_sensor/entities"})
    await hass.async_block_till_done()

    assert connection.results == [
        (
            7,
            [
                {
                    "entry_id": "first",
                    "title": "Living room F1",
                    "entities": {"driver_list": first_driver.entity_id},
                },
                {
                    "entry_id": "second",
                    "title": "Office F1",
                    "entities": {"driver_list": second_driver.entity_id},
                },
            ],
        )
    ]


def test_entity_map_websocket_registration_is_idempotent(hass, monkeypatch) -> None:
    registered = []
    monkeypatch.setattr(
        "custom_components.f1_sensor.entity_map_websocket.websocket_api.async_register_command",
        lambda _hass, handler: registered.append(handler),
    )

    async_register_entity_map_websocket(hass)
    async_register_entity_map_websocket(hass)

    assert registered == [_ws_get_entity_map]
    assert hass.data[DOMAIN][ENTITY_MAP_WS_MARKER] is True
