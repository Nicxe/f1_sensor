"""Frontend resource support for F1 Sensor bundled cards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import logging
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlsplit

from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    CONF_URL,
    LOVELACE_DATA,
)
from homeassistant.const import CONF_ID, CONF_TYPE
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

BUNDLED_LIVE_DATA_CARD_DIR = (
    Path(__file__).resolve().parent / "www" / "f1-sensor-live-data-card"
)
LIVE_DATA_CARD_ASSET_FILENAMES = (
    "f1-sensor-live-data-card.js",
    "hard_tyre.png",
    "intermediate_tyre.png",
    "medium_tyre.png",
    "soft_tyre.png",
    "wet_tyre.png",
)
MANAGED_LIVE_DATA_CARD_RESOURCE_URL = (
    "/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js"
)
OLD_LIVE_DATA_CARD_RESOURCE_URL_PATHS = frozenset(
    {
        "/hacsfiles/f1-sensor-live-data-card/f1-sensor-live-data-card.js",
        "/local/community/f1-sensor-live-data-card/f1-sensor-live-data-card.js",
        "/local/f1-sensor-live-data-card.js",
    }
)
RUNTIME_LIVE_DATA_CARD_DIR_PARTS = ("www", "f1-sensor-live-data-card")
_RESOURCE_TYPE_MODULE = "module"


@dataclass(frozen=True, slots=True)
class LiveDataCardFrontendSync:
    """Result from copying bundled frontend assets to Home Assistant www."""

    cache_key: str
    copied_files: int


async def async_ensure_live_data_card_frontend(hass: HomeAssistant) -> None:
    """Copy bundled card assets and register the Lovelace resource if possible."""
    try:
        sync = await hass.async_add_executor_job(
            _sync_bundled_live_data_card_assets,
            hass.config.path(*RUNTIME_LIVE_DATA_CARD_DIR_PARTS),
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not sync bundled F1 Sensor live data card assets: %s",
            err,
        )
        return

    try:
        await _async_ensure_lovelace_resource(hass, sync.cache_key)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not update the F1 Sensor live data card Lovelace resource: %s",
            err,
        )


def _sync_bundled_live_data_card_assets(
    runtime_dir: str | Path,
) -> LiveDataCardFrontendSync:
    """Copy bundled card assets to the Home Assistant runtime www directory."""
    source_dir = BUNDLED_LIVE_DATA_CARD_DIR
    target_dir = Path(runtime_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Bundled card directory missing: {source_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)
    copied_files = 0
    for filename in LIVE_DATA_CARD_ASSET_FILENAMES:
        source = source_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Bundled card asset missing: {source}")
        target = target_dir / filename
        if not target.is_file() or source.read_bytes() != target.read_bytes():
            shutil.copy2(source, target)
            copied_files += 1

    js_source = source_dir / "f1-sensor-live-data-card.js"
    cache_key = sha256(js_source.read_bytes()).hexdigest()[:12]
    return LiveDataCardFrontendSync(cache_key=cache_key, copied_files=copied_files)


async def _async_ensure_lovelace_resource(
    hass: HomeAssistant,
    cache_key: str,
) -> None:
    """Create or update the Lovelace module resource for the bundled card."""
    resources = _get_lovelace_resources(hass)
    if resources is None:
        _LOGGER.debug("Lovelace resources are not available during F1 Sensor setup")
        return

    async_load = getattr(resources, "async_load", None)
    if not bool(getattr(resources, "loaded", True)) and callable(async_load):
        await async_load()
        try:
            resources.loaded = True
        except AttributeError:
            pass

    async_items = getattr(resources, "async_items", None)
    if not callable(async_items):
        _LOGGER.debug("Lovelace resource collection cannot list resources")
        return

    items = list(async_items() or [])
    desired_url = _managed_resource_url(cache_key)
    managed_item = _find_first_resource(items, _is_managed_resource_url)
    if managed_item is not None:
        await _async_update_resource_if_needed(resources, managed_item, desired_url)
        return

    old_items = [
        item
        for item in items
        if _is_old_live_data_card_resource_url(str(item.get(CONF_URL, "")))
    ]
    if old_items:
        if len(old_items) > 1:
            _LOGGER.info(
                "Found multiple old F1 Sensor live data card resources; updating one and leaving the rest for manual cleanup"
            )
        await _async_update_resource_if_needed(resources, old_items[0], desired_url)
        return

    async_create_item = getattr(resources, "async_create_item", None)
    if not callable(async_create_item):
        _LOGGER.debug("Lovelace resource collection is read-only")
        return
    await async_create_item(_resource_payload(desired_url))


def _find_first_resource(
    items: list[dict[str, Any]],
    matcher: Callable[[str], bool],
) -> dict[str, Any] | None:
    """Return the first resource that matches a URL predicate."""
    for item in items:
        if matcher(str(item.get(CONF_URL, ""))):
            return item
    return None


def _get_lovelace_resources(hass: HomeAssistant) -> Any | None:
    """Return the active Lovelace resource collection if it exists."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        return None
    resources = getattr(lovelace_data, "resources", None)
    if resources is not None:
        return resources
    if isinstance(lovelace_data, dict):
        return lovelace_data.get("resources")
    return None


async def _async_update_resource_if_needed(
    resources: Any,
    item: dict[str, Any],
    desired_url: str,
) -> None:
    """Update a Lovelace resource only when URL or type needs changing."""
    if (
        item.get(CONF_URL) == desired_url
        and item.get(CONF_TYPE) == _RESOURCE_TYPE_MODULE
    ):
        return

    item_id = item.get(CONF_ID)
    async_update_item = getattr(resources, "async_update_item", None)
    if not isinstance(item_id, str) or not callable(async_update_item):
        _LOGGER.debug("Lovelace resource collection is read-only")
        return
    await async_update_item(item_id, _resource_payload(desired_url))


def _is_managed_resource_url(url: str) -> bool:
    """Return True if a Lovelace resource points at the managed card URL."""
    return _normalize_resource_path(url) == MANAGED_LIVE_DATA_CARD_RESOURCE_URL


def _is_old_live_data_card_resource_url(url: str) -> bool:
    """Return True if a Lovelace resource matches a known standalone card URL."""
    return _normalize_resource_path(url) in OLD_LIVE_DATA_CARD_RESOURCE_URL_PATHS


def _managed_resource_url(cache_key: str) -> str:
    """Build the cache-busted Lovelace resource URL."""
    return f"{MANAGED_LIVE_DATA_CARD_RESOURCE_URL}?v={cache_key}"


def _normalize_resource_path(url: str) -> str:
    """Normalize a Lovelace resource URL to a lowercase path without query."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    path = parsed.path or raw.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    return path.lower()


def _resource_payload(url: str) -> dict[str, str]:
    """Return payload accepted by Lovelace resource storage APIs."""
    return {
        CONF_RESOURCE_TYPE_WS: _RESOURCE_TYPE_MODULE,
        CONF_URL: url,
    }
