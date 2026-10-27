"""Tests for the authenticated team radio media proxy."""

from __future__ import annotations

from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.components.http import KEY_HASS
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import team_radio_media
from custom_components.f1_sensor.archive import (
    F1ArchiveAuthenticationRequired,
    F1ArchiveClient,
    F1ArchiveResponseError,
)
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.team_radio_common import (
    resolve_team_radio_source_url,
    team_radio_clip_id,
)
from custom_components.f1_sensor.team_radio_media import (
    TEAM_RADIO_MEDIA_VIEW_REGISTERED,
    TeamRadioMediaView,
    async_register_team_radio_media_view,
    team_radio_media_url,
)


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


def test_team_radio_source_url_resolution() -> None:
    capture = {
        "Utc": "2026-10-11T13:10:20.123Z",
        "RacingNumber": "44",
        "Path": " /TeamRadio/HAM_44.mp3 ",
    }

    assert team_radio_clip_id(capture) == team_radio_clip_id(dict(capture))
    assert resolve_team_radio_source_url({}) is None
    assert resolve_team_radio_source_url(capture, session_path=None, year=2026) is None
    assert (
        resolve_team_radio_source_url(
            {**capture, "static_root": "https://livetiming.formula1.com/static/root/"}
        )
        == "https://livetiming.formula1.com/static/root/TeamRadio/HAM_44.mp3"
    )
    assert resolve_team_radio_source_url(
        capture,
        session_path="race/session/",
        year=2026,
    ) == (
        "https://livetiming.formula1.com/static/2026/race/session/TeamRadio/HAM_44.mp3"
    )
    assert resolve_team_radio_source_url(
        capture,
        session_path="2026/race/session",
        year=2026,
    ) == (
        "https://livetiming.formula1.com/static/2026/race/session/TeamRadio/HAM_44.mp3"
    )


def test_team_radio_media_url_requires_path_and_signs_locally(
    hass, monkeypatch
) -> None:
    capture = {"Utc": "now", "RacingNumber": "44", "Path": "clip.mp3"}
    assert team_radio_media_url(hass, "entry", {}) is None

    sign = Mock(return_value="/signed")
    monkeypatch.setattr(team_radio_media, "async_sign_path", sign)
    assert team_radio_media_url(hass, "entry", capture) == "/signed"
    sign.assert_called_once()

    sign.side_effect = KeyError
    assert team_radio_media_url(hass, "entry", capture).startswith(
        "/api/f1_sensor/team-radio/entry/"
    )


def _request(hass):
    return SimpleNamespace(app={KEY_HASS: hass})


@pytest.mark.asyncio
async def test_team_radio_media_proxy_rejects_unknown_entry_and_runtime(hass) -> None:
    view = TeamRadioMediaView()

    response = await view.get(_request(hass), "missing", "clip")
    assert response.status == HTTPStatus.NOT_FOUND

    wrong_entry = MockConfigEntry(domain="demo", entry_id="wrong")
    wrong_entry.add_to_hass(hass)
    response = await view.get(_request(hass), wrong_entry.entry_id, "clip")
    assert response.status == HTTPStatus.NOT_FOUND

    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-errors")
    entry.add_to_hass(hass)
    response = await view.get(_request(hass), entry.entry_id, "clip")
    assert response.status == HTTPStatus.SERVICE_UNAVAILABLE

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    response = await view.get(_request(hass), entry.entry_id, "clip")
    assert response.status == HTTPStatus.FORBIDDEN


@pytest.mark.asyncio
async def test_team_radio_media_proxy_rejects_unknown_or_unresolvable_clip(
    hass,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-clips")
    entry.add_to_hass(hass)
    client = F1ArchiveClient(_Session(), "Bearer secret")
    coordinator = SimpleNamespace(data=[])
    runtime = {
        "archive_client": client,
        "team_radio_coordinator": coordinator,
        "live_supervisor": None,
        "session_coordinator": SimpleNamespace(year=2026),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    view = TeamRadioMediaView()

    response = await view.get(_request(hass), entry.entry_id, "missing")
    assert response.status == HTTPStatus.NOT_FOUND

    capture = {"Utc": "now", "RacingNumber": "44", "Path": "clip.mp3"}
    coordinator.data = {"latest": None, "history": [capture]}
    response = await view.get(
        _request(hass), entry.entry_id, team_radio_clip_id(capture)
    )
    assert response.status == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (F1ArchiveAuthenticationRequired("auth"), HTTPStatus.FORBIDDEN),
        (F1ArchiveResponseError("upstream"), HTTPStatus.BAD_GATEWAY),
        (TimeoutError(), HTTPStatus.BAD_GATEWAY),
        (ValueError("large"), HTTPStatus.BAD_GATEWAY),
    ],
)
async def test_team_radio_media_proxy_handles_archive_failures(
    hass, monkeypatch, error, expected_status
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, entry_id=f"entry-{type(error).__name__}")
    entry.add_to_hass(hass)
    capture = {
        "Utc": "now",
        "RacingNumber": "44",
        "Path": "TeamRadio/HAM_44.mp3",
        "_static_root": "https://livetiming.formula1.com/static/2026/race",
    }
    client = F1ArchiveClient(_Session(), "Bearer secret")
    monkeypatch.setattr(client, "async_get_bytes", AsyncMock(side_effect=error))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "archive_client": client,
        "team_radio_coordinator": SimpleNamespace(
            data={"latest": capture, "history": []}
        ),
        "live_supervisor": None,
        "session_coordinator": SimpleNamespace(year=2026),
    }

    response = await TeamRadioMediaView().get(
        _request(hass), entry.entry_id, team_radio_clip_id(capture)
    )

    assert response.status == expected_status


def test_team_radio_media_view_registration_is_idempotent(hass) -> None:
    server = SimpleNamespace(register_view=Mock())
    hass.http = server

    async_register_team_radio_media_view(hass)
    async_register_team_radio_media_view(hass)

    server.register_view.assert_called_once()
    assert hass.data[DOMAIN][TEAM_RADIO_MEDIA_VIEW_REGISTERED] is True

    hass.data[DOMAIN].pop(TEAM_RADIO_MEDIA_VIEW_REGISTERED)
    hass.http = None
    async_register_team_radio_media_view(hass)
    assert TEAM_RADIO_MEDIA_VIEW_REGISTERED not in hass.data[DOMAIN]


_RADIO_FP1_PATH = "2026/2026-10-25_United_States_Grand_Prix/2026-10-23_Practice_1/"


def _pathless_radio_case(hass, *, window_key=11389, info_key=11389):
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entry-pathless-live-radio")
    entry.add_to_hass(hass)
    capture = {
        "Utc": "2026-10-23T17:38:17.032Z",
        "RacingNumber": "63",
        "Path": "TeamRadio/RUS_63_20261023_123745.mp3",
    }
    session = _Session()
    runtime = {
        "archive_client": F1ArchiveClient(session, "Bearer secret"),
        "team_radio_coordinator": SimpleNamespace(
            data={"latest": capture, "history": [capture]}
        ),
        "live_supervisor": SimpleNamespace(
            current_window=SimpleNamespace(path="", session_key=window_key)
        ),
        "session_coordinator": SimpleNamespace(year=2026),
        "session_info_coordinator": SimpleNamespace(
            data={"Key": info_key, "Path": _RADIO_FP1_PATH}
        ),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    return entry, capture, session, runtime


@pytest.mark.asyncio
async def test_team_radio_media_pathless_window_uses_matching_current_session_info(
    hass,
) -> None:
    entry, capture, session, _runtime = _pathless_radio_case(hass)
    view = TeamRadioMediaView()
    response = await view.get(
        _request(hass), entry.entry_id, team_radio_clip_id(capture)
    )
    assert view.requires_auth is True
    assert response.status == HTTPStatus.OK
    assert response.body == b"ID3radio"
    assert response.content_type == "audio/mpeg"
    assert (
        session.calls[0][0]
        == "https://livetiming.formula1.com/static/" + _RADIO_FP1_PATH + capture["Path"]
    )
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer secret"


@pytest.mark.asyncio
@pytest.mark.parametrize(("window_key", "info_key"), [(11389, 11388), (None, 11389)])
async def test_team_radio_media_pathless_window_rejects_unconfirmed_session_path(
    hass, window_key, info_key
) -> None:
    entry, capture, session, _runtime = _pathless_radio_case(
        hass, window_key=window_key, info_key=info_key
    )
    response = await TeamRadioMediaView().get(
        _request(hass), entry.entry_id, team_radio_clip_id(capture)
    )
    assert response.status == HTTPStatus.NOT_FOUND
    assert session.calls == []


def test_team_radio_media_existing_window_path_has_priority(hass) -> None:
    _entry, capture, _session, runtime = _pathless_radio_case(hass, info_key=11388)
    runtime["live_supervisor"].current_window.path = _RADIO_FP1_PATH
    assert (
        team_radio_media._source_url(runtime, capture)
        == "https://livetiming.formula1.com/static/" + _RADIO_FP1_PATH + capture["Path"]
    )


def test_team_radio_media_replay_root_does_not_require_live_session_info(hass) -> None:
    _entry, capture, _session, runtime = _pathless_radio_case(hass, info_key=11388)
    runtime["live_supervisor"] = None
    capture = {
        **capture,
        "_static_root": "https://livetiming.formula1.com/static/replay",
    }
    assert (
        team_radio_media._source_url(runtime, capture)
        == "https://livetiming.formula1.com/static/replay/" + capture["Path"]
    )
