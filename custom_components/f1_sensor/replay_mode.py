"""Replay mode for playing back historical F1 sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import async_timeout
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import REPLAY_CACHE_DIR, REPLAY_CACHE_RETENTION_DAYS

_LOGGER = logging.getLogger(__name__)

# Streams to download (matches SUBSCRIBE_MSG in signalr.py)
REPLAY_STREAMS = [
    "RaceControlMessages",
    "TrackStatus",
    "SessionStatus",
    "WeatherData",
    "LapCount",
    "SessionInfo",
    "Heartbeat",
    "ExtrapolatedClock",
    "TimingData",
    "DriverList",
    "TimingAppData",
    "TopThree",
    "TyreStintSeries",
    "TeamRadio",
    "PitStopSeries",
    "ChampionshipPrediction",
]

STATIC_BASE = "https://livetiming.formula1.com/static"
MAX_SESSIONS_TO_SHOW = 150  # ~24 race weekends * 5 sessions + testing
# Cache version - bump this when changing initial_state format to invalidate old caches
CACHE_VERSION = 2


class ReplayState(Enum):
    """State machine for replay mode."""

    IDLE = "idle"
    SELECTED = "selected"
    LOADING = "loading"
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass
class ReplaySession:
    """Metadata for a downloadable/playable session."""

    year: int
    meeting_key: int
    meeting_name: str
    session_key: int
    session_name: str
    session_type: str  # Practice, Qualifying, Sprint, Race
    path: str
    start_utc: datetime
    end_utc: datetime
    available: bool = False  # Set after HEAD check

    @property
    def label(self) -> str:
        """Human-readable label for UI."""
        return f"{self.meeting_name} - {self.session_name}"

    @property
    def unique_id(self) -> str:
        """Unique identifier for this session."""
        return f"{self.year}_{self.meeting_key}_{self.session_key}"


@dataclass
class ReplayFrame:
    """A single frame of replay data."""

    timestamp_ms: int  # Milliseconds from file start
    stream: str
    payload: dict


@dataclass
class ReplayIndex:
    """Index metadata for quick seeking."""

    session_id: str
    total_frames: int
    duration_ms: int
    session_started_at_ms: int  # When SessionStatus:Started occurs
    frames_file: Path
    index_file: Path
    # Snapshot of all streams at session_started_at_ms for initial state
    initial_state: Dict[str, Any] | None = None


class ReplaySessionManager:
    """Manages discovery, download, caching and indexing of replay sessions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        http_session: ClientSession,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._http = http_session
        self._cache_dir = Path(hass.config.path(REPLAY_CACHE_DIR))
        self._state = ReplayState.IDLE
        self._selected_session: ReplaySession | None = None
        self._loaded_index: ReplayIndex | None = None
        self._available_sessions: List[ReplaySession] = []
        self._listeners: List[Callable[[dict], None]] = []
        self._download_progress: float = 0.0
        self._download_error: str | None = None

    @property
    def state(self) -> ReplayState:
        """Current state of the replay manager."""
        return self._state

    @property
    def selected_session(self) -> ReplaySession | None:
        """Currently selected session."""
        return self._selected_session

    @property
    def available_sessions(self) -> List[ReplaySession]:
        """List of available sessions for replay."""
        return self._available_sessions

    @property
    def download_progress(self) -> float:
        """Download progress 0.0 to 1.0."""
        return self._download_progress

    @property
    def download_error(self) -> str | None:
        """Last download error message."""
        return self._download_error

    async def async_initialize(self) -> None:
        """Initialize the manager, create cache dir and cleanup old files."""
        await self._hass.async_add_executor_job(self._ensure_cache_dir)
        await self._cleanup_old_cache()
        # Fetch sessions at startup so the list is populated immediately
        # Run in background to avoid blocking integration startup
        self._hass.async_create_task(self._fetch_sessions_background())

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist (called via executor)."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def _fetch_sessions_background(self) -> None:
        """Fetch sessions in background at startup."""
        try:
            await asyncio.sleep(2)  # Small delay to let integration finish loading
            await self.async_fetch_sessions()
            _LOGGER.info("Loaded %d replay sessions at startup", len(self._available_sessions))
        except Exception as err:
            _LOGGER.warning("Failed to fetch replay sessions at startup: %s", err)

    async def async_fetch_sessions(self, year: int | None = None) -> List[ReplaySession]:
        """Fetch available sessions from F1 Live Timing Index."""
        if year is None:
            year = dt_util.utcnow().year

        sessions: List[ReplaySession] = []

        # Try current year, fall back to previous year if not available
        years_to_try = [year, year - 1] if year == dt_util.utcnow().year else [year]

        data = None
        used_year = None
        for try_year in years_to_try:
            url = f"{STATIC_BASE}/{try_year}/Index.json"
            try:
                async with async_timeout.timeout(15):
                    async with self._http.get(url) as resp:
                        if resp.status in (403, 404):
                            _LOGGER.debug(
                                "Index for %s not available (HTTP %s), trying previous year",
                                try_year, resp.status
                            )
                            continue
                        if resp.status != 200:
                            _LOGGER.warning(
                                "Failed to fetch index for %s: HTTP %s", try_year, resp.status
                            )
                            continue
                        text = await resp.text()
                        data = json.loads(text.lstrip("\ufeff"))
                        used_year = try_year
                        break
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout fetching session index for year %s", try_year)
                continue
            except Exception as err:
                _LOGGER.warning("Error fetching session index for %s: %s", try_year, err)
                continue

        if data is None:
            _LOGGER.warning("Could not fetch session index for any year")
            return sessions

        _LOGGER.info("Fetching replay sessions from year %s", used_year)

        # Parse meetings and sessions
        meetings = data.get("Meetings", [])
        if isinstance(meetings, dict):
            meetings = list(meetings.values())

        for meeting in meetings:
            meeting_key = meeting.get("Key")
            meeting_name = meeting.get("Name") or meeting.get("OfficialName", "Unknown")

            meeting_sessions = meeting.get("Sessions", [])
            if isinstance(meeting_sessions, dict):
                meeting_sessions = list(meeting_sessions.values())

            for sess in meeting_sessions:
                session_key = sess.get("Key")
                session_name = sess.get("Name", "Session")
                session_type = sess.get("Type", "Unknown")
                path = sess.get("Path", "").strip("/")

                start_str = sess.get("StartDate")
                end_str = sess.get("EndDate")
                gmt_offset = sess.get("GmtOffset")

                start_utc = self._parse_datetime(start_str, gmt_offset)
                end_utc = self._parse_datetime(end_str, gmt_offset)

                if start_utc and path:
                    sessions.append(
                        ReplaySession(
                            year=used_year,
                            meeting_key=meeting_key,
                            meeting_name=meeting_name,
                            session_key=session_key,
                            session_name=session_name,
                            session_type=session_type,
                            path=path,
                            start_utc=start_utc,
                            end_utc=end_utc or start_utc,
                        )
                    )

        # Filter to only past sessions (skip availability validation at fetch time
        # to avoid slow HEAD requests blocking the list - validate on demand when loading)
        now = dt_util.utcnow()
        past_sessions = [s for s in sessions if s.end_utc < now]
        past_sessions.sort(key=lambda s: s.start_utc, reverse=True)

        # Mark all as available initially - will be validated when loading
        for s in past_sessions:
            s.available = True

        self._available_sessions = past_sessions[:MAX_SESSIONS_TO_SHOW]
        self._notify_listeners()
        _LOGGER.info(
            "Fetched %d available replay sessions for %s", len(self._available_sessions), year
        )
        return self._available_sessions

    async def async_select_session(self, session_id: str) -> None:
        """Select a session for loading."""
        session = next(
            (s for s in self._available_sessions if s.unique_id == session_id), None
        )
        if not session:
            raise ValueError(f"Session {session_id} not found")

        self._selected_session = session
        self._state = ReplayState.SELECTED
        self._loaded_index = None
        self._download_error = None
        self._notify_listeners()
        _LOGGER.info("Selected replay session: %s", session.label)

    async def async_load_session(self) -> None:
        """Download and index the selected session."""
        if not self._selected_session:
            raise RuntimeError("No session selected")

        self._state = ReplayState.LOADING
        self._download_progress = 0.0
        self._download_error = None
        self._notify_listeners()

        try:
            index = await self._download_and_index_session(self._selected_session)
            self._loaded_index = index
            self._state = ReplayState.READY
            _LOGGER.info(
                "Session loaded: %d frames, starts at %dms",
                index.total_frames,
                index.session_started_at_ms,
            )
        except Exception as err:
            _LOGGER.error("Failed to load session: %s", err)
            self._download_error = str(err)
            self._state = ReplayState.SELECTED
        finally:
            self._notify_listeners()

    async def async_unload(self) -> None:
        """Return to idle state and clean up session cache."""
        # Delete the session cache to save disk space (replay is typically one-time use)
        if self._loaded_index is not None:
            await self._delete_session_cache(self._loaded_index.session_id)

        self._state = ReplayState.IDLE
        self._selected_session = None
        self._loaded_index = None
        self._download_progress = 0.0
        self._download_error = None
        self._notify_listeners()

    async def _delete_session_cache(self, session_id: str) -> None:
        """Delete cached data for a specific session."""
        session_dir = self._cache_dir / session_id
        if session_dir.exists():
            try:
                await self._hass.async_add_executor_job(shutil.rmtree, session_dir)
                _LOGGER.info("Deleted replay cache for session %s", session_id)
            except Exception as err:
                _LOGGER.warning("Failed to delete replay cache for %s: %s", session_id, err)

    def get_loaded_index(self) -> ReplayIndex | None:
        """Return the loaded replay index for the transport."""
        return self._loaded_index

    def add_listener(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        """Subscribe to state changes. Returns unsubscribe function."""
        self._listeners.append(callback)
        # Immediately notify with current state
        try:
            callback(self._get_snapshot())
        except Exception:
            pass

        def _unsub():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _unsub

    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        snapshot = self._get_snapshot()
        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception:
                pass

    def _get_snapshot(self) -> dict:
        """Get current state snapshot."""
        return {
            "state": self._state.value,
            "selected_session": self._selected_session.label if self._selected_session else None,
            "selected_session_id": self._selected_session.unique_id if self._selected_session else None,
            "download_progress": self._download_progress,
            "download_error": self._download_error,
            "sessions_count": len(self._available_sessions),
        }

    async def _download_and_index_session(self, session: ReplaySession) -> ReplayIndex:
        """Download all stream files and create a merged, indexed cache file."""
        session_dir = self._cache_dir / session.unique_id
        session_dir.mkdir(parents=True, exist_ok=True)

        frames_file = session_dir / "frames.jsonl"
        index_file = session_dir / "index.json"

        # Check if already cached with valid version
        if frames_file.exists() and index_file.exists():
            try:
                index_data = await self._hass.async_add_executor_job(
                    self._read_json_file, index_file
                )
                cached_version = index_data.get("cache_version", 1)
                if cached_version >= CACHE_VERSION:
                    _LOGGER.debug("Using cached session data for %s (v%d)", session.unique_id, cached_version)
                    return ReplayIndex(
                        session_id=session.unique_id,
                        total_frames=index_data["total_frames"],
                        duration_ms=index_data["duration_ms"],
                        session_started_at_ms=index_data["session_started_at_ms"],
                        frames_file=frames_file,
                        index_file=index_file,
                        initial_state=index_data.get("initial_state"),
                    )
                else:
                    _LOGGER.info(
                        "Cache version mismatch for %s (cached=%d, current=%d), re-downloading",
                        session.unique_id, cached_version, CACHE_VERSION
                    )
            except Exception as err:
                _LOGGER.warning("Failed to load cached index, re-downloading: %s", err)

        # Download all streams
        all_frames: List[ReplayFrame] = []
        total_streams = len(REPLAY_STREAMS)
        static_root = f"{STATIC_BASE}/{session.path}"

        for i, stream in enumerate(REPLAY_STREAMS):
            self._download_progress = (i / total_streams) * 0.9
            self._notify_listeners()

            stream_url = f"{STATIC_BASE}/{session.path}/{stream}.jsonStream"
            frames = await self._download_stream(stream_url, stream, static_root)
            all_frames.extend(frames)

        if not all_frames:
            raise RuntimeError("No frames downloaded - session data may not be available yet")

        # Sort by timestamp
        all_frames.sort(key=lambda f: f.timestamp_ms)

        # Find SessionStatus:Started
        session_started_at_ms = 0
        for frame in all_frames:
            if frame.stream == "SessionStatus":
                status = frame.payload.get("Status", "")
                if status == "Started":
                    session_started_at_ms = frame.timestamp_ms
                    break

        # Build initial state snapshot - last value of each stream at session start
        # This ensures sensors have their correct initial values when replay starts
        initial_state: Dict[str, Any] = {}
        # Special handling for TopThree which uses delta updates after initial snapshot
        topthree_state: Dict[str, Any] = {"lines": [None, None, None], "withheld": False}

        for frame in all_frames:
            if frame.timestamp_ms > session_started_at_ms:
                break

            # TopThree needs special merge logic because it uses delta updates
            if frame.stream == "TopThree" and isinstance(frame.payload, dict):
                self._merge_topthree_state(topthree_state, frame.payload)
            else:
                # For other streams, just store latest value
                initial_state[frame.stream] = frame.payload

        # Convert TopThree state back to payload format
        if topthree_state["lines"] != [None, None, None]:
            initial_state["TopThree"] = {
                "Withheld": topthree_state.get("withheld", False),
                "Lines": topthree_state["lines"],
            }
            _LOGGER.debug(
                "Built merged TopThree initial state: %s",
                [(l.get("Tla") if isinstance(l, dict) else None) for l in topthree_state["lines"]]
            )

        # For streams that don't have data before session start, capture their first frame(s)
        # This is important for streams like TopThree that may only start at session begin
        streams_needing_first = set(REPLAY_STREAMS) - set(initial_state.keys())
        if streams_needing_first:
            for frame in all_frames:
                if frame.stream in streams_needing_first:
                    # For TopThree, merge multiple frames until we have all 3 positions
                    if frame.stream == "TopThree" and isinstance(frame.payload, dict):
                        self._merge_topthree_state(topthree_state, frame.payload)
                        # Only mark complete when all 3 positions are filled
                        lines = topthree_state.get("lines", [None, None, None])
                        all_filled = all(isinstance(l, dict) for l in lines)
                        if all_filled:
                            initial_state["TopThree"] = {
                                "Withheld": topthree_state.get("withheld", False),
                                "Lines": lines,
                            }
                            streams_needing_first.discard("TopThree")
                    else:
                        initial_state[frame.stream] = frame.payload
                        streams_needing_first.discard(frame.stream)
                if not streams_needing_first:
                    break
            # If TopThree still incomplete but has some data, include what we have
            if "TopThree" not in initial_state and topthree_state["lines"] != [None, None, None]:
                initial_state["TopThree"] = {
                    "Withheld": topthree_state.get("withheld", False),
                    "Lines": topthree_state["lines"],
                }

        _LOGGER.debug(
            "Built initial state snapshot with %d streams: %s",
            len(initial_state), list(initial_state.keys())
        )

        # Write frames file
        self._download_progress = 0.95
        self._notify_listeners()

        # Prepare frames data for writing
        frames_lines = []
        for frame in all_frames:
            line = json.dumps(
                {
                    "t": frame.timestamp_ms,
                    "s": frame.stream,
                    "p": frame.payload,
                },
                separators=(",", ":"),
            )
            frames_lines.append(line)

        await self._hass.async_add_executor_job(
            self._write_lines_file, frames_file, frames_lines
        )

        # Write index
        duration_ms = all_frames[-1].timestamp_ms if all_frames else 0
        index_data = {
            "cache_version": CACHE_VERSION,
            "session_id": session.unique_id,
            "total_frames": len(all_frames),
            "duration_ms": duration_ms,
            "session_started_at_ms": session_started_at_ms,
            "initial_state": initial_state,
            "created_at": dt_util.utcnow().isoformat(),
        }

        await self._hass.async_add_executor_job(
            self._write_json_file, index_file, index_data
        )

        self._download_progress = 1.0
        self._notify_listeners()

        return ReplayIndex(
            session_id=session.unique_id,
            total_frames=len(all_frames),
            duration_ms=duration_ms,
            session_started_at_ms=session_started_at_ms,
            frames_file=frames_file,
            index_file=index_file,
            initial_state=initial_state,
        )

    async def _download_stream(
        self, url: str, stream_name: str, static_root: str
    ) -> List[ReplayFrame]:
        """Download a single .jsonStream file and parse into frames."""
        frames: List[ReplayFrame] = []

        try:
            async with async_timeout.timeout(60):
                async with self._http.get(url) as resp:
                    if resp.status == 404:
                        _LOGGER.debug("Stream %s not found (404)", stream_name)
                        return frames
                    if resp.status != 200:
                        _LOGGER.debug("Stream %s returned %s", stream_name, resp.status)
                        return frames
                    text = await resp.text()
        except asyncio.TimeoutError:
            _LOGGER.debug("Timeout downloading %s", stream_name)
            return frames
        except Exception as err:
            _LOGGER.debug("Error downloading %s: %s", stream_name, err)
            return frames

        # Parse jsonStream format: each line is timestamp + JSON
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Find the JSON start
            json_start = line.find("{")
            if json_start == -1:
                continue

            timestamp_str = line[:json_start].strip()
            json_str = line[json_start:]

            try:
                timestamp_ms = self._parse_timestamp_to_ms(timestamp_str)
                payload = json.loads(json_str)

                # Annotate TeamRadio payloads with static_root for clip URL construction
                if stream_name == "TeamRadio" and isinstance(payload, dict):
                    payload["_static_root"] = static_root

                frames.append(
                    ReplayFrame(
                        timestamp_ms=timestamp_ms,
                        stream=stream_name,
                        payload=payload,
                    )
                )
            except (json.JSONDecodeError, ValueError):
                continue

        _LOGGER.debug("Downloaded %d frames from %s", len(frames), stream_name)
        return frames

    def _merge_topthree_state(self, state: Dict[str, Any], payload: dict) -> None:
        """Merge a TopThree payload into accumulated state.

        TopThree sends an initial full snapshot with Lines as a list,
        followed by delta updates with Lines as a dict {"0": {...}, "1": {...}}.
        This method handles both formats to build up the complete state.
        """
        if not isinstance(payload, dict):
            return

        # Handle Withheld flag
        if "Withheld" in payload:
            state["withheld"] = bool(payload.get("Withheld"))

        lines = payload.get("Lines")
        cur_lines = state.get("lines") or [None, None, None]

        # Full snapshot: Lines as list [P1, P2, P3]
        if isinstance(lines, list):
            new_lines = [None, None, None]
            for idx in range(min(3, len(lines))):
                item = lines[idx]
                new_lines[idx] = item if isinstance(item, dict) else None
            state["lines"] = new_lines
        # Delta: Lines as dict {"0": {...}, "1": {...}, "2": {...}}
        elif isinstance(lines, dict):
            for key, delta in lines.items():
                try:
                    idx = int(key)
                except (ValueError, TypeError):
                    continue
                if idx < 0 or idx > 2:
                    continue
                if not isinstance(delta, dict):
                    continue
                base = cur_lines[idx]
                if not isinstance(base, dict):
                    base = {}
                base.update(delta)
                cur_lines[idx] = base
            state["lines"] = cur_lines

    @staticmethod
    def _parse_timestamp_to_ms(ts: str) -> int:
        """Parse HH:MM:SS.mmm to milliseconds."""
        parts = ts.split(":")
        if len(parts) != 3:
            return 0

        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            sec_parts = parts[2].split(".")
            seconds = int(sec_parts[0])
            millis = int(sec_parts[1]) if len(sec_parts) > 1 else 0

            return (hours * 3600 + minutes * 60 + seconds) * 1000 + millis
        except ValueError:
            return 0

    async def _validate_session_availability(self, sessions: List[ReplaySession]) -> None:
        """Check which sessions have data available via HEAD requests."""
        # Batch validation - check SessionStatus.jsonStream existence
        tasks = []
        for session in sessions:
            url = f"{STATIC_BASE}/{session.path}/SessionStatus.jsonStream"
            tasks.append(self._check_url_exists(url, session))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_url_exists(self, url: str, session: ReplaySession) -> None:
        """HEAD request to check if URL exists."""
        try:
            async with async_timeout.timeout(5):
                async with self._http.head(url) as resp:
                    session.available = resp.status == 200
        except Exception:
            session.available = False

    async def _cleanup_old_cache(self) -> None:
        """Remove cache entries older than retention period."""
        cleaned = await self._hass.async_add_executor_job(
            self._cleanup_old_cache_sync
        )
        if cleaned > 0:
            _LOGGER.info("Cleaned %d old replay cache entries", cleaned)

    def _cleanup_old_cache_sync(self) -> int:
        """Synchronous cache cleanup (called via executor)."""
        if not self._cache_dir.exists():
            return 0

        cutoff = time.time() - (REPLAY_CACHE_RETENTION_DAYS * 24 * 3600)
        cleaned = 0

        for session_dir in self._cache_dir.iterdir():
            if not session_dir.is_dir():
                continue

            index_file = session_dir / "index.json"
            if not index_file.exists():
                continue

            try:
                stat = index_file.stat()
                if stat.st_mtime < cutoff:
                    shutil.rmtree(session_dir)
                    cleaned += 1
                    _LOGGER.debug("Cleaned old replay cache: %s", session_dir.name)
            except Exception:
                pass

        return cleaned

    @staticmethod
    def _read_json_file(file_path: Path) -> dict:
        """Read and parse a JSON file (called via executor)."""
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _write_json_file(file_path: Path, data: dict) -> None:
        """Write data to a JSON file (called via executor)."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def _write_lines_file(file_path: Path, lines: List[str]) -> None:
        """Write lines to a file (called via executor)."""
        with open(file_path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")

    def _parse_datetime(
        self, date_str: str | None, gmt_offset: str | None
    ) -> datetime | None:
        """Parse datetime with GMT offset."""
        if not date_str:
            return None
        try:
            # Handle various formats
            if date_str.endswith("Z"):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            elif "+" in date_str or (date_str.count("-") > 2):
                dt = datetime.fromisoformat(date_str)
            else:
                dt = datetime.fromisoformat(date_str)

            # Apply GMT offset if no timezone and offset provided
            if dt.tzinfo is None and gmt_offset:
                try:
                    # Parse offset like "04:00:00" -> +4 hours
                    offset_parts = gmt_offset.split(":")
                    offset_hours = int(offset_parts[0])
                    offset_mins = int(offset_parts[1]) if len(offset_parts) > 1 else 0
                    from datetime import timedelta

                    offset = timedelta(hours=offset_hours, minutes=offset_mins)
                    dt = dt.replace(tzinfo=timezone.utc) - offset
                except Exception:
                    dt = dt.replace(tzinfo=timezone.utc)
            elif dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(timezone.utc)
        except ValueError:
            return None


class ReplayTransport:
    """Transport that plays back cached replay data, implementing LiveTransport protocol."""

    def __init__(
        self,
        hass: HomeAssistant,
        replay_index: ReplayIndex,
        *,
        start_from_session_start: bool = True,
        speed_multiplier: float = 1.0,
    ) -> None:
        self._hass = hass
        self._index = replay_index
        self._start_from_session_start = start_from_session_start
        self._speed = max(0.1, min(10.0, speed_multiplier))
        self._closed = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._current_position_ms = 0
        self._playback_started_at: float | None = None
        self._pause_started_at: float | None = None
        self._total_paused_duration: float = 0.0
        self._listeners: List[Callable[[dict], None]] = []

    async def ensure_connection(self) -> None:
        """No-op for replay transport - data is already local."""
        pass

    async def messages(self) -> AsyncGenerator[dict, None]:
        """Yield replay frames as SignalR-compatible messages."""
        start_ms = self._index.session_started_at_ms if self._start_from_session_start else 0
        self._current_position_ms = start_ms
        self._playback_started_at = time.monotonic()
        self._total_paused_duration = 0.0

        _LOGGER.info(
            "Starting replay from %dms (session start: %dms)",
            start_ms,
            self._index.session_started_at_ms,
        )

        try:
            # Read file content in executor (sync I/O off event loop)
            def _read_frames():
                with open(self._index.frames_file, "r", encoding="utf-8") as f:
                    return f.readlines()

            lines = await self._hass.async_add_executor_job(_read_frames)
            _LOGGER.debug("Replay: loaded %d lines from cache file", len(lines))

            yielded_count = 0
            for line in lines:
                if self._closed:
                    return

                # Handle pause
                await self._pause_event.wait()
                if self._closed:
                    return

                try:
                    frame = json.loads(line.strip())
                    frame_ms = frame["t"]
                    stream = frame["s"]
                    payload = frame["p"]
                except (json.JSONDecodeError, KeyError):
                    continue

                # Skip frames before start point
                if frame_ms < start_ms:
                    continue

                # Calculate delay based on elapsed time
                target_elapsed_ms = (frame_ms - start_ms) / self._speed
                actual_elapsed = self._get_elapsed_playback_time()
                actual_elapsed_ms = actual_elapsed * 1000

                delay_ms = target_elapsed_ms - actual_elapsed_ms
                if delay_ms > 10:  # Only sleep if > 10ms
                    await asyncio.sleep(delay_ms / 1000)

                self._current_position_ms = frame_ms
                self._notify_listeners()

                yielded_count += 1
                # Log progress every 1000 frames
                if yielded_count == 1:
                    _LOGGER.info("Replay: first frame yielded (stream=%s)", stream)
                elif yielded_count % 1000 == 0:
                    _LOGGER.debug(
                        "Replay progress: %d frames yielded, position=%dms",
                        yielded_count, frame_ms
                    )

                # Yield in SignalR format
                yield {
                    "M": [
                        {
                            "H": "Streaming",
                            "M": "feed",
                            "A": [stream, payload],
                        }
                    ]
                }
        except asyncio.CancelledError:
            _LOGGER.debug("Replay transport cancelled")
            raise

        # All frames exhausted - mark as closed so playback stops (don't restart)
        _LOGGER.info("Replay playback completed - all frames played")
        self._closed = True

    async def close(self) -> None:
        """Close the transport."""
        self._closed = True
        self._pause_event.set()  # Unblock if paused

    def pause(self) -> None:
        """Pause playback."""
        if not self._paused:
            self._paused = True
            self._pause_started_at = time.monotonic()
            self._pause_event.clear()
            self._notify_listeners()
            _LOGGER.debug("Replay paused at %dms", self._current_position_ms)

    def resume(self) -> None:
        """Resume playback."""
        if self._paused:
            if self._pause_started_at:
                self._total_paused_duration += time.monotonic() - self._pause_started_at
            self._paused = False
            self._pause_started_at = None
            self._pause_event.set()
            self._notify_listeners()
            _LOGGER.debug("Replay resumed at %dms", self._current_position_ms)

    def _get_elapsed_playback_time(self) -> float:
        """Get actual elapsed playback time in seconds, excluding pauses."""
        if self._playback_started_at is None:
            return 0.0

        total_elapsed = time.monotonic() - self._playback_started_at
        paused_now = 0.0
        if self._paused and self._pause_started_at:
            paused_now = time.monotonic() - self._pause_started_at

        return total_elapsed - self._total_paused_duration - paused_now

    def get_playback_position_ms(self) -> int:
        """Get current playback position in milliseconds."""
        return self._current_position_ms

    def get_session_start_offset_ms(self) -> int:
        """Get the offset where session actually starts."""
        return self._index.session_started_at_ms

    def get_total_duration_ms(self) -> int:
        """Get total duration of the replay in milliseconds."""
        return self._index.duration_ms

    def is_paused(self) -> bool:
        """Check if playback is paused."""
        return self._paused

    def add_listener(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        """Subscribe to playback state changes."""
        self._listeners.append(callback)

        def _unsub():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _unsub

    def _notify_listeners(self) -> None:
        """Notify listeners of playback state change."""
        snapshot = {
            "position_ms": self._current_position_ms,
            "duration_ms": self._index.duration_ms,
            "paused": self._paused,
            "elapsed_s": self._get_elapsed_playback_time(),
        }
        for listener in list(self._listeners):
            try:
                listener(snapshot)
            except Exception:
                pass


class ReplayController:
    """High-level controller coordinating session manager and playback."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        http_session: ClientSession,
        live_bus: Any,
        live_state: Any = None,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._http_session = http_session
        self._live_bus = live_bus
        self._live_state = live_state  # LiveAvailabilityTracker to signal coordinators
        self._session_manager = ReplaySessionManager(hass, entry_id, http_session)
        self._transport: ReplayTransport | None = None
        self._original_transport_factory: Callable | None = None
        self._replay_active = False  # Track if replay transport is active
        self._playback_task: asyncio.Task | None = None
        self._listeners: List[Callable[[dict], None]] = []

    @property
    def session_manager(self) -> ReplaySessionManager:
        """Get the session manager."""
        return self._session_manager

    @property
    def state(self) -> ReplayState:
        """Get current replay state."""
        return self._session_manager.state

    @property
    def transport(self) -> ReplayTransport | None:
        """Get the current transport (for playback status)."""
        return self._transport

    async def async_initialize(self) -> None:
        """Initialize the controller."""
        await self._session_manager.async_initialize()

    async def async_play(self) -> None:
        """Start playback of loaded session."""
        if self._session_manager.state != ReplayState.READY:
            raise RuntimeError("Session not ready for playback")

        index = self._session_manager.get_loaded_index()
        if not index:
            raise RuntimeError("No replay index loaded")

        # Create transport
        self._transport = ReplayTransport(
            self._hass,
            index,
            start_from_session_start=True,
        )

        # Signal coordinators that we're "live" for replay mode
        # This makes them accept incoming data even outside real live window
        if self._live_state is not None:
            _LOGGER.info("Setting live_state to True for replay mode")
            self._live_state.set_state(True, "replay")

        # Save original transport factory and swap to replay
        self._original_transport_factory = self._live_bus._transport_factory
        self._replay_active = True

        def _replay_transport_factory():
            if not self._replay_active or self._transport is None:
                _LOGGER.warning("Replay transport factory called but replay is not active")
                raise RuntimeError("Replay transport is not available")
            # Check if transport is closed (playback complete) - deactivate to stop reconnects
            if self._transport._closed:
                _LOGGER.info("Replay transport is closed - stopping reconnect attempts")
                self._replay_active = False
                raise RuntimeError("Replay transport is closed - playback complete")
            _LOGGER.debug("Replay transport factory called, returning transport")
            return self._transport

        _LOGGER.debug("Calling swap_transport with replay factory")
        await self._live_bus.swap_transport(_replay_transport_factory)
        _LOGGER.debug("swap_transport completed, LiveBus running=%s", self._live_bus._running)

        # Inject initial state for all streams so sensors have their correct values
        # before the replay transport starts yielding frames
        if index.initial_state:
            _LOGGER.info(
                "Injecting initial state for %d streams: %s",
                len(index.initial_state), list(index.initial_state.keys())
            )
            for stream, payload in index.initial_state.items():
                if isinstance(payload, dict):
                    self._live_bus.inject_message(stream, payload)

        # Start playback in background
        self._playback_task = self._hass.async_create_task(self._run_playback())
        self._session_manager._state = ReplayState.PLAYING
        self._session_manager._notify_listeners()
        _LOGGER.info("Replay playback started")

    async def async_pause(self) -> None:
        """Pause playback."""
        if self._transport and self._session_manager.state == ReplayState.PLAYING:
            self._transport.pause()
            self._session_manager._state = ReplayState.PAUSED
            self._session_manager._notify_listeners()

    async def async_resume(self) -> None:
        """Resume playback."""
        if self._transport and self._session_manager.state == ReplayState.PAUSED:
            self._transport.resume()
            self._session_manager._state = ReplayState.PLAYING
            self._session_manager._notify_listeners()

    async def async_stop(self) -> None:
        """Stop playback and return to idle."""
        _LOGGER.info("Stopping replay playback")

        # IMPORTANT: Restore factory FIRST, then close bus to avoid race condition
        # where LiveSessionSupervisor restarts bus with old replay factory
        if self._replay_active:
            self._replay_active = False
            _LOGGER.debug("Restoring original transport factory and stopping LiveBus")
            # Restore factory BEFORE closing - prevents supervisor race condition
            if self._original_transport_factory is not None:
                self._live_bus._transport_factory = self._original_transport_factory
                self._original_transport_factory = None
            else:
                self._live_bus._transport_factory = None
            # Now safe to close the bus
            await self._live_bus.async_close()

        # Now safe to close the transport since LiveBus is stopped
        if self._transport:
            await self._transport.close()
            self._transport = None

        if self._playback_task:
            self._playback_task.cancel()
            try:
                await self._playback_task
            except asyncio.CancelledError:
                pass
            self._playback_task = None

        # Restore live state to idle - let LiveSessionSupervisor control it
        if self._live_state is not None:
            _LOGGER.info("Restoring live_state to idle after replay stop")
            self._live_state.set_state(False, "replay-stopped")

        await self._session_manager.async_unload()

    async def _run_playback(self) -> None:
        """Background task - the LiveBus is already running with our transport."""
        try:
            # Just wait until the transport is closed (playback complete or stopped)
            # Use short interval to detect completion quickly and stop reconnect loop
            while self._transport and not self._transport._closed:
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("Replay playback error: %s", err)
        finally:
            # If playback ended naturally (not stopped by user), clean up properly
            if self._session_manager.state in (ReplayState.PLAYING, ReplayState.PAUSED):
                _LOGGER.info("Replay playback ended naturally - cleaning up")

                # IMPORTANT: Restore factory FIRST, then close bus to avoid race condition
                # where LiveSessionSupervisor restarts bus with old replay factory
                self._replay_active = False

                # Restore original transport factory (or None for SignalR fallback)
                # Do this BEFORE closing to prevent supervisor from restarting with replay factory
                if self._original_transport_factory is not None:
                    self._live_bus._transport_factory = self._original_transport_factory
                    self._original_transport_factory = None
                else:
                    # Explicitly set to None so SignalRClient is used on reconnect
                    self._live_bus._transport_factory = None

                # Now safe to close the bus - supervisor will use restored factory on restart
                await self._live_bus.async_close()

                # Clean up transport
                if self._transport:
                    self._transport = None

                # Restore live state
                if self._live_state is not None:
                    self._live_state.set_state(False, "replay-completed")

                # Update session state to IDLE (not READY - session is done)
                self._session_manager._state = ReplayState.IDLE
                self._session_manager._notify_listeners()

                # Clean up cache
                await self._session_manager.async_unload()

    def get_playback_status(self) -> dict:
        """Get current playback position and status."""
        if not self._transport:
            return {"position_ms": 0, "duration_ms": 0, "paused": False, "elapsed_s": 0}

        return {
            "position_ms": self._transport.get_playback_position_ms(),
            "session_start_ms": self._transport.get_session_start_offset_ms(),
            "duration_ms": self._transport.get_total_duration_ms(),
            "paused": self._transport.is_paused(),
            "elapsed_s": self._transport._get_elapsed_playback_time(),
        }
