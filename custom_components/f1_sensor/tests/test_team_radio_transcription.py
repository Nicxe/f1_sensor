"""Tests for experimental team radio transcription."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_get_cached_service_description
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.f1_sensor import TeamRadioCoordinator
from custom_components.f1_sensor.const import DOMAIN
from custom_components.f1_sensor.team_radio_transcription import (
    ATTR_AI_TASK_ENTITY_ID,
    ATTR_ENTITY_ID,
    ATTR_FORCE,
    MAX_AUDIO_BYTES,
    SERVICE_TRANSCRIBE_TEAM_RADIO,
    TRANSCRIPTION_MANAGER_KEY,
    TeamRadioTranscriptionManager,
    _normalize_segments,
    async_register_team_radio_transcription_service,
    team_radio_clip_id,
)


class _Coordinator:
    def __init__(self) -> None:
        capture = {
            "Utc": "2026-10-11T13:10:20.123Z",
            "RacingNumber": "44",
            "Path": "TeamRadio/HAM_44_20261011_131020.mp3",
            "clip_url": (
                "https://livetiming.formula1.com/static/2026/"
                "2026-10-09_Singapore_Grand_Prix/2026-10-11_Race/"
                "TeamRadio/HAM_44_20261011_131020.mp3"
            ),
        }
        self.data = {"latest": capture, "history": [dict(capture)]}
        self.results: list[dict] = []

    def set_transcription(self, clip_id: str, result: dict) -> bool:
        self.results.append(dict(result))
        changed = False
        for key in ("latest",):
            item = self.data[key]
            if team_radio_clip_id(item) == clip_id:
                item["Transcription"] = dict(result)
                changed = True
        for item in self.data["history"]:
            if team_radio_clip_id(item) == clip_id:
                item["Transcription"] = dict(result)
                changed = True
        return changed


class _CoordinatorState:
    def __init__(self, capture: dict) -> None:
        self._state = {"latest": capture, "history": [dict(capture)]}
        self.updates: list[dict] = []

    def async_set_updated_data(self, data: dict) -> None:
        self.updates.append(data)


class _Content:
    def __init__(self, chunks: tuple[bytes, ...] = (b"ID3", b"radio")) -> None:
        self._chunks = chunks

    async def iter_chunked(self, _size: int):
        for chunk in self._chunks:
            yield chunk


class _Response:
    def __init__(
        self,
        *,
        status: int = 200,
        content_length: int | None = 8,
        content_type: str = "audio/mpeg",
        chunks: tuple[bytes, ...] = (b"ID3", b"radio"),
    ) -> None:
        self.status = status
        self.content_length = content_length
        self.headers = {"Content-Type": content_type}
        self.content = _Content(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def __init__(self, response: _Response | None = None) -> None:
        self._response = response or _Response()

    def get(self, *_args, **_kwargs):
        return self._response


@dataclass
class _AIResult:
    data: dict


def test_normalize_segments_maps_two_provider_labels_and_merges_turns() -> None:
    assert _normalize_segments(
        {
            "segments": [
                {"speaker": "Speaker 2", "text": "Hamilton behind"},
                {"speaker": "Speaker 2", "text": "is faster."},
                {"speaker": "Speaker 1", "text": "Okay, thank you."},
                {"speaker": "third voice", "text": "Unclear background."},
            ]
        }
    ) == [
        {"speaker": "A", "text": "Hamilton behind is faster."},
        {"speaker": "B", "text": "Okay, thank you."},
        {"speaker": "unknown", "text": "Unclear background."},
    ]


def test_normalize_segments_rejects_invalid_or_empty_results() -> None:
    with pytest.raises(HomeAssistantError, match="invalid transcription"):
        _normalize_segments({"segments": "not a list"})

    with pytest.raises(HomeAssistantError, match="no spoken"):
        _normalize_segments(
            {
                "segments": [
                    "not a segment",
                    {"speaker": "engineer", "text": ""},
                    {"speaker": "unknown", "text": "   "},
                ]
            }
        )

    assert _normalize_segments(
        {"segments": [{"speaker": "unknown", "text": "Stay out."}]}
    ) == [{"speaker": "unknown", "text": "Stay out."}]


def test_transcription_resolves_source_behind_local_media_proxy(hass) -> None:
    coordinator = _Coordinator()
    source_url = coordinator.data["latest"]["clip_url"]
    coordinator.data["latest"].pop("clip_url")
    manager = TeamRadioTranscriptionManager(
        hass,
        coordinator,
        source_url_resolver=lambda _capture: source_url,
    )

    capture = manager._latest_capture(  # noqa: SLF001
        "/api/f1_sensor/team-radio/entry/signed"
    )

    assert capture["clip_url"] == source_url


def test_team_radio_coordinator_attaches_transcription_to_known_clip() -> None:
    capture = _Coordinator().data["latest"]
    coordinator = _CoordinatorState(capture)
    result = {
        "status": "completed",
        "segments": [{"speaker": "A", "text": "Box, box."}],
    }

    changed = TeamRadioCoordinator.set_transcription(
        coordinator, team_radio_clip_id(capture), result
    )

    assert changed is True
    assert coordinator._state["latest"]["Transcription"] == result
    assert coordinator._state["history"][0]["Transcription"] == result
    assert coordinator.updates == [coordinator._state]


def test_transcription_action_registers_fields_for_actions_editor(hass) -> None:
    async_register_team_radio_transcription_service(hass)

    description = async_get_cached_service_description(
        hass, "f1_sensor", "transcribe_team_radio"
    )

    assert description is not None
    assert description["name"] == "Experimental: Transcribe team radio"
    assert set(description["fields"]) == {
        ATTR_ENTITY_ID,
        ATTR_AI_TASK_ENTITY_ID,
        ATTR_FORCE,
    }
    assert description["fields"][ATTR_ENTITY_ID]["required"] is True
    assert description["fields"][ATTR_AI_TASK_ENTITY_ID]["required"] is True
    assert description["fields"][ATTR_FORCE]["default"] is False


@pytest.mark.asyncio
async def test_transcribe_latest_clip_uses_ai_task_and_caches_result(
    hass, tmp_path: Path
) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    coordinator = _Coordinator()
    manager = TeamRadioTranscriptionManager(hass, coordinator)
    ai_call = AsyncMock(
        return_value=_AIResult(
            {
                "segments": [
                    {"speaker": "engineer", "text": "Hamilton behind is faster."},
                    {"speaker": "driver", "text": "Okay, thank you."},
                ]
            }
        )
    )

    with (
        patch(
            "custom_components.f1_sensor.team_radio_transcription.async_get_clientsession",
            return_value=_Session(),
        ),
        patch(
            "custom_components.f1_sensor.team_radio_transcription._async_call_ai_task",
            ai_call,
        ),
    ):
        result = await manager.async_transcribe(
            ai_task_entity_id="ai_task.gemini_team_radio"
        )
        cached = await manager.async_transcribe(
            ai_task_entity_id="ai_task.gemini_team_radio"
        )

    assert result == cached
    assert result["status"] == "completed"
    assert result["segments"] == [
        {"speaker": "A", "text": "Hamilton behind is faster."},
        {"speaker": "B", "text": "Okay, thank you."},
    ]
    assert coordinator.results[0]["status"] == "processing"
    assert coordinator.results[-1] == result
    assert ai_call.await_count == 1
    media_id = ai_call.await_args.kwargs["media_content_id"]
    assert media_id.startswith(
        "media-source://media_source/local/f1_sensor/team_radio/"
    )
    assert list((tmp_path / "f1_sensor" / "team_radio").iterdir()) == []


@pytest.mark.asyncio
async def test_transcribe_rejects_non_f1_audio_host(hass, tmp_path: Path) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    coordinator = _Coordinator()
    coordinator.data["latest"]["clip_url"] = "https://example.com/radio.mp3"
    manager = TeamRadioTranscriptionManager(hass, coordinator)

    with pytest.raises(ServiceValidationError, match="not allowed"):
        await manager.async_transcribe(ai_task_entity_id="ai_task.gemini_team_radio")

    assert coordinator.results[-1]["status"] == "failed"


@pytest.mark.asyncio
async def test_transcribe_records_ai_task_failure(hass, tmp_path: Path) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    coordinator = _Coordinator()
    manager = TeamRadioTranscriptionManager(hass, coordinator)

    with (
        patch(
            "custom_components.f1_sensor.team_radio_transcription.async_get_clientsession",
            return_value=_Session(),
        ),
        patch(
            "custom_components.f1_sensor.team_radio_transcription._async_call_ai_task",
            AsyncMock(side_effect=HomeAssistantError("AI task unavailable")),
        ),
        pytest.raises(ServiceValidationError, match="AI task unavailable"),
    ):
        await manager.async_transcribe(ai_task_entity_id="ai_task.gemini_team_radio")

    assert coordinator.results[-1]["status"] == "failed"
    assert coordinator.results[-1]["error"] == "AI task unavailable"
    assert list((tmp_path / "f1_sensor" / "team_radio").iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (_Response(status=503), "status 503"),
        (_Response(content_length=MAX_AUDIO_BYTES + 1), "file is too large"),
        (_Response(content_type="audio/wav"), "not MP3 audio"),
        (
            _Response(
                content_length=None,
                chunks=(b"x" * (MAX_AUDIO_BYTES + 1),),
            ),
            "file is too large",
        ),
        (_Response(content_length=0, chunks=()), "file is empty"),
    ],
)
async def test_download_audio_rejects_invalid_provider_responses(
    hass, response: _Response, error: str
) -> None:
    manager = TeamRadioTranscriptionManager(hass, _Coordinator())

    with (
        patch(
            "custom_components.f1_sensor.team_radio_transcription.async_get_clientsession",
            return_value=_Session(response),
        ),
        pytest.raises(HomeAssistantError, match=error),
    ):
        await manager._async_download_audio(_Coordinator().data["latest"]["clip_url"])


@pytest.mark.asyncio
async def test_transcription_validates_lifecycle_and_uses_capture_cache(
    hass, tmp_path: Path
) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    coordinator = _Coordinator()
    manager = TeamRadioTranscriptionManager(hass, coordinator)

    with pytest.raises(ServiceValidationError, match="Select an AI Task"):
        await manager.async_transcribe(ai_task_entity_id="sensor.not_an_ai_task")

    coordinator.data = {"latest": None}
    with pytest.raises(ServiceValidationError, match="No team radio clip"):
        await manager.async_transcribe(ai_task_entity_id="ai_task.gemini_team_radio")

    coordinator = _Coordinator()
    coordinator.data["latest"].pop("clip_url")
    manager = TeamRadioTranscriptionManager(hass, coordinator)
    with pytest.raises(ServiceValidationError, match="no audio URL"):
        await manager.async_transcribe(ai_task_entity_id="ai_task.gemini_team_radio")

    coordinator = _Coordinator()
    cached = {"status": "completed", "segments": [{"speaker": "A", "text": "Box."}]}
    coordinator.data["latest"]["Transcription"] = cached
    manager = TeamRadioTranscriptionManager(hass, coordinator)
    assert (
        await manager.async_transcribe(ai_task_entity_id="ai_task.gemini_team_radio")
        == cached
    )

    orphan = tmp_path / "orphan.mp3"
    orphan.write_bytes(b"audio")
    manager._temporary_files.add(orphan)
    await manager.async_close()
    assert orphan.exists() is False
    with pytest.raises(ServiceValidationError, match="unavailable"):
        await manager.async_transcribe(ai_task_entity_id="ai_task.gemini_team_radio")


@pytest.mark.asyncio
async def test_write_media_file_requires_media_directory(hass) -> None:
    manager = TeamRadioTranscriptionManager(hass, _Coordinator())
    hass.config.media_dirs = {}

    with pytest.raises(HomeAssistantError, match="no local media directory"):
        await manager._async_write_media_file("clip", b"audio")


@pytest.mark.asyncio
async def test_transcription_action_resolves_registered_team_radio_entity(
    hass, tmp_path: Path
) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    entry = MockConfigEntry(domain=DOMAIN, entry_id="team-radio-entry")
    entry.add_to_hass(hass)
    coordinator = _Coordinator()
    manager = TeamRadioTranscriptionManager(hass, coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        TRANSCRIPTION_MANAGER_KEY: manager
    }
    entity = er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_team_radio", config_entry=entry
    )
    hass.states.async_set(
        entity.entity_id,
        "available",
        {"clip_url": coordinator.data["latest"]["clip_url"]},
    )
    async_register_team_radio_transcription_service(hass)
    ai_call = AsyncMock(
        return_value=_AIResult({"segments": [{"speaker": "driver", "text": "Copy."}]})
    )

    with (
        patch(
            "custom_components.f1_sensor.team_radio_transcription.async_get_clientsession",
            return_value=_Session(),
        ),
        patch(
            "custom_components.f1_sensor.team_radio_transcription._async_call_ai_task",
            ai_call,
        ),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_TRANSCRIBE_TEAM_RADIO,
            {
                ATTR_ENTITY_ID: entity.entity_id,
                ATTR_AI_TASK_ENTITY_ID: "ai_task.gemini_team_radio",
                ATTR_FORCE: False,
            },
            blocking=True,
            return_response=True,
        )

    assert response["entity_id"] == entity.entity_id
    assert response["transcription"]["segments"] == [{"speaker": "A", "text": "Copy."}]
