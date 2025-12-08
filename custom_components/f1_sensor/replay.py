import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Sequence

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

KNOWN_STREAMS = {
    "RaceControlMessages",
    "TrackStatus",
    "SessionStatus",
    "WeatherData",
    "LapCount",
    "SessionInfo",
    "TimingData",
    "DriverList",
    "TimingAppData",
}


@dataclass(slots=True)
class ReplayFrame:
    delay: float
    stream: str
    payload: dict


class ReplaySignalRClient:
    """Replay SignalR feed frames from a recorded dump file."""

    def __init__(
        self,
        hass: HomeAssistant,
        source: Path,
        *,
        stream_hint: str | None = None,
        loop_forever: bool = True,
        speed_multiplier: float = 1.0,
    ) -> None:
        self._hass = hass
        self._path = source.expanduser()
        self._stream_hint = stream_hint or self._guess_stream_from_name(self._path)
        self._loop_forever = loop_forever
        self._speed = max(0.01, float(speed_multiplier or 1.0))
        self._frames: List[ReplayFrame] = []
        self._closed = False
        self._loaded = False

    async def ensure_connection(self) -> None:
        """Load frames from disk."""
        if self._loaded:
            return
        self._frames = await self._hass.async_add_executor_job(self._load_frames)
        if not self._frames:
            raise RuntimeError(
                f"Replay dump {self._path} did not contain any valid frames"
            )
        self._loaded = True

    async def messages(self) -> AsyncGenerator[dict, None]:
        """Yield fake SignalR frames matching the recorded dump."""
        if not self._loaded:
            await self.ensure_connection()
        if not self._frames:
            return

        while not self._closed:
            for frame in self._frames:
                if self._closed:
                    return
                delay = frame.delay / self._speed
                if delay > 0:
                    await asyncio.sleep(delay)
                yield {
                    "M": [
                        {
                            "H": "Streaming",
                            "M": "feed",
                            "A": [frame.stream, frame.payload],
                        }
                    ]
                }
            if not self._loop_forever:
                break

    async def close(self) -> None:
        self._closed = True

    def _load_frames(self) -> List[ReplayFrame]:
        if not self._path.exists():
            raise FileNotFoundError(f"Replay dump not found: {self._path}")
        frames: List[ReplayFrame] = []
        prev_ts: float | None = None
        stream_hint = self._stream_hint
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.upper().startswith("URL:"):
                        stream_hint = self._extract_stream_from_url(line) or stream_hint
                        continue
                    ts_part, json_part = self._split_line(line)
                    if not json_part:
                        continue
                    payload_obj = self._parse_json(json_part)
                    if payload_obj is None:
                        continue
                    stream_name, payload = self._extract_stream(payload_obj)
                    if payload is None:
                        continue
                    stream_name = stream_name or stream_hint
                    if not stream_name:
                        _LOGGER.debug(
                            "Skipping replay line without stream hint in %s", self._path
                        )
                        continue
                    current_ts = self._parse_timestamp(ts_part)
                    delay = self._compute_delay(current_ts, prev_ts)
                    prev_ts = current_ts
                    frames.append(ReplayFrame(delay=delay, stream=stream_name, payload=payload))
        except FileNotFoundError:
            raise
        except Exception as err:  # noqa: BLE001
            raise RuntimeError(f"Failed to parse replay dump {self._path}: {err}") from err
        return frames

    def _compute_delay(self, current: float | None, prev_ts: float | None) -> float:
        if current is None:
            return 0.0
        if prev_ts is None:
            return max(0.0, current)
        return max(0.0, current - prev_ts)

    @staticmethod
    def _parse_timestamp(value: str) -> float | None:
        """Return seconds since start for HH:MM:SS.mmm strings."""
        text = value.strip()
        fmt = "%H:%M:%S.%f" if "." in text else "%H:%M:%S"
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            return None
        return parsed.hour * 3600 + parsed.minute * 60 + parsed.second + (parsed.microsecond / 1_000_000)

    @staticmethod
    def _split_line(line: str) -> tuple[str, str]:
        idx = line.find("{")
        if idx == -1:
            return line, ""
        return line[:idx].strip(), line[idx:]

    @staticmethod
    def _parse_json(fragment: str) -> dict | None:
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _guess_stream_from_name(path: Path) -> str | None:
        base = path.stem
        for token in reversed(base.split("_")):
            if token in KNOWN_STREAMS:
                return token
        return None

    @staticmethod
    def _extract_stream_from_url(line: str) -> str | None:
        try:
            _, url = line.split(":", 1)
        except ValueError:
            return None
        tail = url.strip().rstrip("/")
        if not tail:
            return None
        tail = tail.split("/")[-1]
        if tail.endswith(".jsonStream"):
            tail = tail[: -len(".jsonStream")]
        return tail if tail in KNOWN_STREAMS else None

    @staticmethod
    def _extract_stream(obj: dict) -> tuple[str | None, dict | None]:
        if not isinstance(obj, dict):
            return None, None
        if "payload" in obj and isinstance(obj["payload"], dict):
            stream = obj.get("stream")
            if not stream and isinstance(obj["payload"], dict):
                stream = obj["payload"].get("_stream")
            payload = obj["payload"]
            return str(stream) if stream else None, payload
        stream = obj.get("_stream")
        if stream:
            payload = {k: v for k, v in obj.items() if k != "_stream"}
            return str(stream), payload
        return None, obj

