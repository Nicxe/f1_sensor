"""One-time information about automatic card data, independent of operation."""

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN

CONF_CARD_DATA_NOTICE_VERSION = "card_data_notice_version"
CARD_DATA_NOTICE_VERSION = 1


def notification_id(entry_id: str) -> str:
    """Replace one informational notification for each installation."""
    return f"{DOMAIN}_card_data_{entry_id}_v{CARD_DATA_NOTICE_VERSION}"


@callback
def async_dismiss_card_data_notice(hass: HomeAssistant, entry_id: str) -> None:
    """Clear current information and any obsolete upgrade reminder."""
    persistent_notification.async_dismiss(hass, notification_id(entry_id))
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_data_choice_{entry_id}_v1")


def _needs_notice(entry: ConfigEntry) -> bool:
    version = entry.data.get(CONF_CARD_DATA_NOTICE_VERSION)
    return (
        (entry.version, entry.minor_version) >= (4, 4)
        and entry.disabled_by is None
        and (type(version) is not int or version < CARD_DATA_NOTICE_VERSION)
    )


async def async_notify_card_data(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Inform once; dismissing, reloading and restarting never require a choice."""
    persistent_notification.async_dismiss(
        hass, f"{DOMAIN}_data_choice_{entry.entry_id}_v1"
    )
    if not _needs_notice(entry):
        return
    translations = await async_get_translations(
        hass, hass.config.language or "en", "exceptions", {DOMAIN}
    )
    prefix = f"component.{DOMAIN}.exceptions."
    title_key = prefix + "card_data_notification_title.message"
    message_key = prefix + "card_data_notification.message"
    if title_key not in translations or message_key not in translations:
        translations = await async_get_translations(hass, "en", "exceptions", {DOMAIN})
    if not translations.get(title_key) or not translations.get(message_key):
        return
    # The entry can be removed, disabled or informed by another setup while
    # asynchronous translations load. Recheck before persisting and publishing.
    if hass.config_entries.async_get_entry(
        entry.entry_id
    ) is not entry or not _needs_notice(entry):
        return
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_CARD_DATA_NOTICE_VERSION: CARD_DATA_NOTICE_VERSION},
    )
    persistent_notification.async_create(
        hass,
        translations[message_key].format(
            name=entry.title,
            integration_url=f"/config/integrations/integration/{DOMAIN}",
        ),
        title=translations[title_key],
        notification_id=notification_id(entry.entry_id),
    )
