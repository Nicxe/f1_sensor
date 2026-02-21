"""Device triggers for F1 Sensor."""

from __future__ import annotations

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import CONF_ENTITY_ID, CONF_FOR, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import DOMAIN

# Maps trigger_type → (unique_id_suffix, entity_domain, to_state or None)
# to_state=None means "any state change" (fires on every update)
_TRIGGER_MAP: dict[str, tuple[str, str, str | None]] = {
    # Race device
    "race_week_started": ("race_week", "binary_sensor", "on"),
    "race_week_ended": ("race_week", "binary_sensor", "off"),
    # Session device
    "safety_car_deployed": ("safety_car", "binary_sensor", "on"),
    "safety_car_cleared": ("safety_car", "binary_sensor", "off"),
    "formation_start_ready": ("formation_start", "binary_sensor", "on"),
    "overtake_mode_enabled": ("overtake_mode", "binary_sensor", "on"),
    "overtake_mode_disabled": ("overtake_mode", "binary_sensor", "off"),
    "session_live": ("session_status", "sensor", None),
    "track_status_clear": ("track_status", "sensor", "CLEAR"),
    "track_status_yellow": ("track_status", "sensor", "YELLOW"),
    "track_status_safety_car": ("track_status", "sensor", "SC"),
    "track_status_vsc": ("track_status", "sensor", "VSC"),
    "track_status_red_flag": ("track_status", "sensor", "RED"),
    # Officials device
    "new_race_control_message": ("race_control", "sensor", None),
    "new_fia_document": ("fia_documents", "sensor", None),
    "investigation_changed": ("investigations", "sensor", None),
    # Drivers device
    "new_team_radio": ("team_radio", "sensor", None),
    # System device
    "live_timing_online": ("live_timing_online", "binary_sensor", "on"),
    "live_timing_offline": ("live_timing_online", "binary_sensor", "off"),
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(_TRIGGER_MAP),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


def _find_entity(
    entity_registry: er.EntityRegistry,
    device_id: str,
    suffix: str,
    domain: str,
) -> er.RegistryEntry | None:
    """Return the entity registry entry whose unique_id ends with _{suffix}."""
    for entry in er.async_entries_for_device(entity_registry, device_id):
        if entry.domain == domain and entry.unique_id.endswith(f"_{suffix}"):
            return entry
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """Return all device triggers available for this device.

    Only triggers whose backing entity exists on the device are included,
    so disabled sensors will simply not show the associated trigger.
    """
    entity_registry = er.async_get(hass)
    triggers: list[dict[str, str]] = []
    for trigger_type, (suffix, domain, _to_state) in _TRIGGER_MAP.items():
        entry = _find_entity(entity_registry, device_id, suffix, domain)
        if entry is not None:
            triggers.append(
                {
                    "platform": "device",
                    "device_id": device_id,
                    "domain": DOMAIN,
                    "entity_id": entry.id,
                    "type": trigger_type,
                }
            )
    return triggers


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """All triggers support the optional 'for' clause."""
    return {
        "extra_fields": vol.Schema(
            {vol.Optional(CONF_FOR): cv.positive_time_period_dict}
        )
    }


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a device trigger by delegating to the HA state trigger."""
    trigger_type = config[CONF_TYPE]
    _suffix, _domain, to_state = _TRIGGER_MAP[trigger_type]

    state_config: dict = {
        "platform": "state",
        "entity_id": config[CONF_ENTITY_ID],
    }
    if to_state is not None:
        state_config["to"] = to_state
    if CONF_FOR in config:
        state_config[CONF_FOR] = config[CONF_FOR]

    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )
