"""Tests for the authenticated team radio media proxy."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.components.http import KEY_HASS
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor.archive import F1ArchiveClient
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.team_radio_common import team_radio_clip_id
from custom_components.f1_sensor.team_radio_media import TeamRadioMediaView


class _Content:
    async def iter_chunked(self, _size: int):
        yield b"ID3"
        yield b"radio"


class _Response:
    status = 200
    headers = {"Content-Type": "audio/mpeg"}
    content_length = 8
    content = _Content()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


@pytest.mark.asyncio
async def test_team_radio_media_proxy_fetches_known_clip_with_f1tv_auth(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry")
    entry.add_to_hass(hass)
    capture = {
        "Utc": "2026-10-11T13:10:20.123Z",
        "RacingNumber": "44",
        "Path": "TeamRadio/HAM_44.mp3",
        "_static_root": (
            "https://livetiming.formula1.com/static/2026/"
            "2026-10-09_Singapore_Grand_Prix/2026-10-11_Race"
        ),
    }
    session = _Session()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "archive_client": F1ArchiveClient(session, "Bearer secret"),
        "team_radio_coordinator": SimpleNamespace(
            data={"latest": capture, "history": [capture]}
        ),
        "live_supervisor": None,
        "session_coordinator": SimpleNamespace(year=2026),
    }

    response = await TeamRadioMediaView().get(
        SimpleNamespace(app={KEY_HASS: hass}),
        entry.entry_id,
        team_radio_clip_id(capture),
    )

    assert response.status == 200
    assert response.body == b"ID3radio"
    assert response.content_type == "audio/mpeg"
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer secret"
