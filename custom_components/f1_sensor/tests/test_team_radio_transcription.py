"""Tests for experimental team radio transcription."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_get_cached_service_description
import pytest

from custom_components.f1_sensor import TeamRadioCoordinator
from custom_components.f1_sensor.team_radio_transcription import (
    ATTR_AI_TASK_ENTITY_ID,
    ATTR_ENTITY_ID,
    ATTR_FORCE,
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
    async def iter_chunked(self, _size: int):
        yield b"ID3"
        yield b"radio"


class _Response:
    status = 200
    content_length = 8
    headers = {"Content-Type": "audio/mpeg"}
    content = _Content()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Session:
    def get(self, *_args, **_kwargs):
        return _Response()


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
