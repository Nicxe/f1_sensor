"""Tests for bundled frontend resource management."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from homeassistant.components.lovelace.const import LOVELACE_DATA
import pytest

from custom_components.f1_sensor import frontend


class DummyLovelaceResources:
    """Minimal Lovelace resource collection for resource manager tests."""

    def __init__(self, items: list[dict[str, Any]] | None = None) -> None:
        self.created = 0
        self.items = items or []
        self.loaded = False
        self.updated = 0

    async def async_load(self) -> None:
        self.loaded = True

    def async_items(self) -> list[dict[str, Any]]:
        return self.items

    async def async_create_item(self, data: dict[str, str]) -> dict[str, str]:
        self.created += 1
        item = {
            "id": f"resource-{self.created}",
            "type": data["res_type"],
            "url": data["url"],
        }
        self.items.append(item)
        return item

    async def async_update_item(
        self,
        item_id: str,
        updates: dict[str, str],
    ) -> dict[str, str]:
        self.updated += 1
        for item in self.items:
            if item["id"] == item_id:
                item["type"] = updates["res_type"]
                item["url"] = updates["url"]
                return item
        raise KeyError(item_id)


class FailingCreateLovelaceResources(DummyLovelaceResources):
    """Lovelace resource collection that fails when creating a resource."""

    async def async_create_item(self, data: dict[str, str]) -> dict[str, str]:
        raise RuntimeError("resource storage unavailable")


def _write_bundled_assets(source_dir: Path, js_source: str) -> None:
    source_dir.mkdir(parents=True)
    for filename in frontend.LIVE_DATA_CARD_ASSET_FILENAMES:
        path = source_dir / filename
        if filename.endswith(".js"):
            path.write_text(js_source, encoding="utf-8")
        else:
            path.write_bytes(filename.encode())


def test_sync_bundled_assets_copies_card_files_and_changes_cache_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "bundled"
    runtime_dir = tmp_path / "runtime"
    _write_bundled_assets(source_dir, "console.log('v1');")
    monkeypatch.setattr(frontend, "BUNDLED_LIVE_DATA_CARD_DIR", source_dir)

    first = frontend._sync_bundled_live_data_card_assets(runtime_dir)

    assert first.copied_files == len(frontend.LIVE_DATA_CARD_ASSET_FILENAMES)
    for filename in frontend.LIVE_DATA_CARD_ASSET_FILENAMES:
        assert (runtime_dir / filename).is_file()

    (source_dir / "f1-sensor-live-data-card.js").write_text(
        "console.log('v2');",
        encoding="utf-8",
    )
    second = frontend._sync_bundled_live_data_card_assets(runtime_dir)

    assert second.cache_key != first.cache_key
    assert second.copied_files == 1


@pytest.mark.asyncio
async def test_lovelace_resource_creation_is_idempotent(hass) -> None:
    resources = DummyLovelaceResources()
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    await frontend._async_ensure_lovelace_resource(hass, "abc123")
    await frontend._async_ensure_lovelace_resource(hass, "abc123")

    assert resources.created == 1
    assert resources.updated == 0
    assert resources.items == [
        {
            "id": "resource-1",
            "type": "module",
            "url": "/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=abc123",
        }
    ]


@pytest.mark.asyncio
async def test_lovelace_resource_updates_existing_old_hacs_resource(hass) -> None:
    resources = DummyLovelaceResources(
        [
            {
                "id": "old-resource",
                "type": "js",
                "url": "/hacsfiles/f1-sensor-live-data-card/f1-sensor-live-data-card.js?hacstag=old",
            }
        ]
    )
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    await frontend._async_ensure_lovelace_resource(hass, "newkey")

    assert resources.created == 0
    assert resources.updated == 1
    assert resources.items == [
        {
            "id": "old-resource",
            "type": "module",
            "url": "/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=newkey",
        }
    ]


@pytest.mark.asyncio
async def test_lovelace_resource_leaves_extra_old_resources_for_cleanup(hass) -> None:
    resources = DummyLovelaceResources(
        [
            {
                "id": "old-hacs",
                "type": "js",
                "url": "/hacsfiles/f1-sensor-live-data-card/f1-sensor-live-data-card.js",
            },
            {
                "id": "old-local",
                "type": "js",
                "url": "/local/f1-sensor-live-data-card.js",
            },
        ]
    )
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    await frontend._async_ensure_lovelace_resource(hass, "cachekey")

    assert resources.created == 0
    assert resources.updated == 1
    assert resources.items[0] == {
        "id": "old-hacs",
        "type": "module",
        "url": "/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=cachekey",
    }
    assert resources.items[1] == {
        "id": "old-local",
        "type": "js",
        "url": "/local/f1-sensor-live-data-card.js",
    }


@pytest.mark.asyncio
async def test_lovelace_resource_updates_when_cache_key_changes(hass) -> None:
    resources = DummyLovelaceResources(
        [
            {
                "id": "managed",
                "type": "module",
                "url": "/local/f1-sensor-live-data-card/f1-sensor-live-data-card.js?v=oldkey",
            }
        ]
    )
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)

    await frontend._async_ensure_lovelace_resource(hass, "newkey")

    assert resources.created == 0
    assert resources.updated == 1
    assert resources.items[0]["url"].endswith("?v=newkey")


@pytest.mark.asyncio
async def test_frontend_setup_continues_without_lovelace(
    hass,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "bundled"
    _write_bundled_assets(source_dir, "console.log('available');")
    monkeypatch.setattr(frontend, "BUNDLED_LIVE_DATA_CARD_DIR", source_dir)

    await frontend.async_ensure_live_data_card_frontend(hass)

    runtime_dir = Path(hass.config.path("www", "f1-sensor-live-data-card"))
    assert (runtime_dir / "f1-sensor-live-data-card.js").is_file()


@pytest.mark.asyncio
async def test_frontend_setup_continues_when_resource_manager_fails(
    hass,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_dir = tmp_path / "bundled"
    _write_bundled_assets(source_dir, "console.log('available');")
    monkeypatch.setattr(frontend, "BUNDLED_LIVE_DATA_CARD_DIR", source_dir)
    hass.data[LOVELACE_DATA] = SimpleNamespace(
        resources=FailingCreateLovelaceResources()
    )

    await frontend.async_ensure_live_data_card_frontend(hass)

    runtime_dir = Path(hass.config.path("www", "f1-sensor-live-data-card"))
    assert (runtime_dir / "f1-sensor-live-data-card.js").is_file()
