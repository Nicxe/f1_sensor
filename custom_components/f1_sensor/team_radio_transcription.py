"""Experimental AI transcription for published F1 team radio clips."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from functools import partial
import hashlib
import logging
import mimetypes
from pathlib import Path
import tempfile
from typing import Any, Protocol
from urllib.parse import urlparse

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_TRANSCRIBE_TEAM_RADIO = "transcribe_team_radio"
TRANSCRIPTION_MANAGER_KEY = "team_radio_transcription_manager"

ATTR_ENTITY_ID = "entity_id"
ATTR_AI_TASK_ENTITY_ID = "ai_task_entity_id"
ATTR_FORCE = "force"

MAX_AUDIO_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 30
ALLOWED_AUDIO_HOSTS = frozenset({"livetiming.formula1.com"})

TRANSCRIPTION_SCHEMA = vol.Schema(
    {
        vol.Required("segments"): [
            {
                vol.Required("speaker"): cv.string,
                vol.Required("text"): cv.string,
            }
        ]
    }
)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_AI_TASK_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_FORCE, default=False): cv.boolean,
    }
)

# Register this at runtime as well as in services.yaml. Home Assistant's Actions
# editor needs the live description cache to render fields for this custom action.
SERVICE_DESCRIPTION = {
    "name": "Experimental: Transcribe team radio",
    "description": (
        "Experimental feature. Transcribe the latest published team radio clip "
        "in English and separate distinct voices as anonymous speakers A and B. "
        "Audio is sent only when you run this action and may incur provider charges."
    ),
    "fields": {
        ATTR_ENTITY_ID: {
            "name": "Team radio entity",
            "description": "The F1 Sensor team radio entity whose latest clip is used.",
            "required": True,
            "selector": {
                "entity": {"filter": [{"integration": DOMAIN, "domain": "sensor"}]}
            },
        },
        ATTR_AI_TASK_ENTITY_ID: {
            "name": "AI Task entity",
            "description": (
                "The AI Task entity used for audio transcription. This "
                "experimental feature is tested with Google Gemini."
            ),
            "required": True,
            "selector": {"entity": {"filter": [{"domain": "ai_task"}]}},
        },
        ATTR_FORCE: {
            "name": "Force new transcription",
            "description": (
                "Run a new paid AI request even if this clip already has a "
                "cached transcription."
            ),
            "required": False,
            "default": False,
            "selector": {"boolean": {}},
        },
    },
}

_INSTRUCTIONS = """Transcribe the spoken English in this Formula 1 team radio clip.
Return every spoken turn in chronological order. Keep the wording faithful to the
audio and do not summarize, paraphrase, translate, identify people, or infer their
roles. Use one stable speaker label for each distinct voice within this clip. There
are usually one or two voices. If a voice cannot be assigned reliably, use
\"unknown\". Return only the requested structured data."""


class TeamRadioCoordinatorProtocol(Protocol):
    """Runtime contract required by the transcription manager."""

    data: Any

    def set_transcription(self, clip_id: str, result: dict[str, Any]) -> bool:
        """Attach a transcription result to one known capture."""


def team_radio_clip_id(capture: dict[str, Any]) -> str:
    """Return a stable ID for one published team radio clip."""
    identity = "|".join(
        str(capture.get(key) or "").strip() for key in ("Utc", "RacingNumber", "Path")
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def _safe_error_message(err: Exception) -> str:
    """Return a bounded user-facing error without request details."""
    message = str(err).strip() or err.__class__.__name__
    return message[:240]


def _normalize_segments(data: Any) -> list[dict[str, str]]:
    """Normalize arbitrary provider labels to A/B within one clip."""
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise HomeAssistantError("AI task returned an invalid transcription result")

    labels: dict[str, str] = {}
    normalized: list[dict[str, str]] = []
    for raw_segment in data["segments"]:
        if not isinstance(raw_segment, dict):
            continue
        text = str(raw_segment.get("text") or "").strip()
        if not text:
            continue
        raw_speaker = str(raw_segment.get("speaker") or "unknown").strip()
        speaker_key = raw_speaker.casefold()
        if not speaker_key or speaker_key in {"unknown", "unclear", "unsure"}:
            speaker = "unknown"
        else:
            if speaker_key not in labels and len(labels) < 2:
                labels[speaker_key] = "A" if not labels else "B"
            speaker = labels.get(speaker_key, "unknown")
        if normalized and normalized[-1]["speaker"] == speaker:
            normalized[-1]["text"] = f"{normalized[-1]['text']} {text}"
        else:
            normalized.append({"speaker": speaker, "text": text})

    if not normalized:
        raise HomeAssistantError("AI task returned no spoken team radio text")
    return normalized


async def _async_call_ai_task(
    hass: HomeAssistant,
    *,
    entity_id: str,
    media_content_id: str,
) -> Any:
    """Call the public AI Task API lazily for older HA compatibility."""
    try:
        from homeassistant.components import ai_task
    except ImportError as err:
        raise HomeAssistantError(
            "This Home Assistant version does not provide AI Task"
        ) from err

    return await ai_task.async_generate_data(
        hass,
        task_name="F1 team radio transcription",
        entity_id=entity_id,
        instructions=_INSTRUCTIONS,
        structure=TRANSCRIPTION_SCHEMA,
        attachments=[
            {
                "media_content_id": media_content_id,
                "media_content_type": "audio/mpeg",
            }
        ],
    )


class TeamRadioTranscriptionManager:
    """Download and transcribe one team radio clip at a time."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: TeamRadioCoordinatorProtocol,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._lock = asyncio.Lock()
        self._closed = False
        self._temporary_files: set[Path] = set()
        self._completed_results: dict[str, dict[str, Any]] = {}

    async def async_close(self) -> None:
        """Stop accepting work and remove temporary audio files."""
        self._closed = True
        self._completed_results.clear()
        files = tuple(self._temporary_files)
        self._temporary_files.clear()
        if files:
            await self._hass.async_add_executor_job(self._remove_files, files)

    @staticmethod
    def _remove_files(files: tuple[Path, ...]) -> None:
        for path in files:
            with suppress(OSError):
                path.unlink(missing_ok=True)

    def _latest_capture(self, clip_url: str | None = None) -> dict[str, Any]:
        state = self._coordinator.data
        capture = state.get("latest") if isinstance(state, dict) else None
        if not isinstance(capture, dict):
            raise ServiceValidationError("No team radio clip is currently available")
        capture = dict(capture)
        if clip_url:
            capture["clip_url"] = clip_url
        if not str(capture.get("clip_url") or "").strip():
            raise ServiceValidationError("The latest team radio clip has no audio URL")
        return capture

    @staticmethod
    def _completed_result(capture: dict[str, Any]) -> dict[str, Any] | None:
        result = capture.get("Transcription")
        if isinstance(result, dict) and result.get("status") == "completed":
            return dict(result)
        return None

    async def async_transcribe(
        self,
        *,
        ai_task_entity_id: str,
        force: bool = False,
        clip_url: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe the latest clip and attach the result to its capture."""
        if self._closed:
            raise ServiceValidationError("Team radio transcription is unavailable")
        if not ai_task_entity_id.startswith("ai_task."):
            raise ServiceValidationError("Select an AI Task entity")

        async with self._lock:
            capture = self._latest_capture(clip_url)
            clip_id = team_radio_clip_id(capture)
            if not force:
                cached = self._completed_results.get(clip_id)
                if cached is None:
                    cached = self._completed_result(capture)
                if cached is not None:
                    return dict(cached)

            self._coordinator.set_transcription(
                clip_id,
                {
                    "status": "processing",
                    "ai_task_entity_id": ai_task_entity_id,
                    "requested_at": dt_util.utcnow().isoformat(timespec="seconds"),
                },
            )
            temp_path: Path | None = None
            try:
                audio = await self._async_download_audio(capture["clip_url"])
                temp_path, media_content_id = await self._async_write_media_file(
                    clip_id, audio
                )
                ai_result = await _async_call_ai_task(
                    self._hass,
                    entity_id=ai_task_entity_id,
                    media_content_id=media_content_id,
                )
                segments = _normalize_segments(getattr(ai_result, "data", None))
                result = {
                    "status": "completed",
                    "text": " ".join(segment["text"] for segment in segments),
                    "segments": segments,
                    "ai_task_entity_id": ai_task_entity_id,
                    "generated_at": dt_util.utcnow().isoformat(timespec="seconds"),
                }
                self._coordinator.set_transcription(clip_id, result)
                self._completed_results[clip_id] = dict(result)
                return result
            except Exception as err:
                error = _safe_error_message(err)
                self._coordinator.set_transcription(
                    clip_id,
                    {
                        "status": "failed",
                        "ai_task_entity_id": ai_task_entity_id,
                        "error": error,
                        "generated_at": dt_util.utcnow().isoformat(timespec="seconds"),
                    },
                )
                if isinstance(err, ServiceValidationError):
                    raise
                raise ServiceValidationError(error) from err
            finally:
                if temp_path is not None:
                    self._temporary_files.discard(temp_path)
                    await self._hass.async_add_executor_job(
                        self._remove_files, (temp_path,)
                    )

    async def _async_download_audio(self, clip_url: str) -> bytes:
        parsed = urlparse(clip_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_AUDIO_HOSTS:
            raise ServiceValidationError("Team radio audio URL is not allowed")

        session = async_get_clientsession(self._hass)
        async with asyncio.timeout(DOWNLOAD_TIMEOUT_SECONDS):
            async with session.get(clip_url, allow_redirects=False) as response:
                if response.status != 200:
                    raise HomeAssistantError(
                        f"Team radio audio download failed with status {response.status}"
                    )
                content_length = response.content_length
                if content_length is not None and content_length > MAX_AUDIO_BYTES:
                    raise HomeAssistantError("Team radio audio file is too large")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                if content_type and content_type not in {
                    "audio/mpeg",
                    "audio/mp3",
                    "application/octet-stream",
                }:
                    raise HomeAssistantError("Team radio response is not MP3 audio")
                audio = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    audio.extend(chunk)
                    if len(audio) > MAX_AUDIO_BYTES:
                        raise HomeAssistantError("Team radio audio file is too large")
        if not audio:
            raise HomeAssistantError("Team radio audio file is empty")
        return bytes(audio)

    async def _async_write_media_file(
        self, clip_id: str, audio: bytes
    ) -> tuple[Path, str]:
        media_dirs = dict(getattr(self._hass.config, "media_dirs", {}) or {})
        if not media_dirs:
            raise HomeAssistantError("Home Assistant has no local media directory")
        source_id = "local" if "local" in media_dirs else sorted(media_dirs)[0]
        target_dir = Path(media_dirs[source_id]) / DOMAIN / "team_radio"

        def _write() -> Path:
            target_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f"{clip_id}_",
                suffix=mimetypes.guess_extension("audio/mpeg", False) or ".mp3",
                dir=target_dir,
                delete=False,
            ) as temp_file:
                temp_file.write(audio)
                return Path(temp_file.name)

        path = await self._hass.async_add_executor_job(_write)
        self._temporary_files.add(path)
        relative = path.relative_to(media_dirs[source_id]).as_posix()
        return path, f"media-source://media_source/{source_id}/{relative}"


def _resolve_manager(
    hass: HomeAssistant, entity_id: str
) -> TeamRadioTranscriptionManager | None:
    registry_entry = er.async_get(hass).async_get(entity_id)
    if (
        registry_entry is None
        or registry_entry.platform != DOMAIN
        or registry_entry.unique_id != f"{registry_entry.config_entry_id}_team_radio"
    ):
        return None
    entry_data = hass.data.get(DOMAIN, {}).get(registry_entry.config_entry_id, {})
    manager = entry_data.get(TRANSCRIPTION_MANAGER_KEY)
    return manager if isinstance(manager, TeamRadioTranscriptionManager) else None


async def _async_handle_transcribe_team_radio(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    entity_id = call.data[ATTR_ENTITY_ID]
    manager = _resolve_manager(hass, entity_id)
    if manager is None:
        raise ServiceValidationError(
            f"Team radio transcription is not available for {entity_id}"
        )
    state = hass.states.get(entity_id)
    clip_url = str(state.attributes.get("clip_url", "") if state else "")
    result = await manager.async_transcribe(
        ai_task_entity_id=call.data[ATTR_AI_TASK_ENTITY_ID],
        force=call.data[ATTR_FORCE],
        clip_url=clip_url,
    )
    return {"entity_id": entity_id, "transcription": result}


def async_register_team_radio_transcription_service(hass: HomeAssistant) -> None:
    """Register the experimental manual transcription action once."""
    if hass.services.has_service(DOMAIN, SERVICE_TRANSCRIBE_TEAM_RADIO):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRANSCRIBE_TEAM_RADIO,
        partial(_async_handle_transcribe_team_radio, hass),
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_TRANSCRIBE_TEAM_RADIO,
        SERVICE_DESCRIPTION,
    )
