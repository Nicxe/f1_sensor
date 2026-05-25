from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .helpers import fetch_text

_LOGGER = logging.getLogger(__name__)

_NO_SPOILER_MANAGER_KEY = "no_spoiler_manager"
STATIC_BASE = "https://livetiming.formula1.com/static"

CONTEXT_NONE = "none"
CONTEXT_RACE = "race"
CONTEXT_SPRINT = "sprint"

STATUS_WAITING_SPRINT_QUALIFYING = "waiting_for_sprint_qualifying"
STATUS_WAITING_QUALIFYING = "waiting_for_qualifying"
STATUS_COLLECTING = "collecting"
STATUS_PROVISIONAL = "provisional"
STATUS_CONFIRMED = "confirmed"
STATUS_COMPLETED = "completed"

SOURCE_LIVE_QUALIFYING = "live_timing_qualifying"
SOURCE_ARCHIVE = "live_timing_archive"
SOURCE_GRIDPOS = "live_timing_gridpos"

WEEKEND_FORMAT_NORMAL = "normal"
WEEKEND_FORMAT_SPRINT = "sprint"
WEEKEND_FORMAT_UNKNOWN = "unknown"

SESSION_KIND_PRACTICE = "practice"
SESSION_KIND_SPRINT_QUALIFYING = "sprint_qualifying"
SESSION_KIND_QUALIFYING = "qualifying"
SESSION_KIND_SPRINT = "sprint"
SESSION_KIND_RACE = "race"
SESSION_KIND_OTHER = "other"

STARTED_STATUSES = {"Started", "Resumed", "GreenFlag", "Green"}
FINISHED_STATUSES = {"Finished", "Finalised", "Ends"}
REPLAY_REASONS = {"replay", "replay-mode", "replay-preparing"}


class StartingGridCoordinator(DataUpdateCoordinator):
    """Build the currently relevant starting grid from Live Timing streams."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_coord: DataUpdateCoordinator,
        *,
        bus: Any | None = None,
        session=None,
        user_agent: str | None = None,
        cache: dict | None = None,
        inflight: dict | None = None,
        persist_map: dict | None = None,
        persist_save: Callable[[], None] | None = None,
        config_entry: ConfigEntry | None = None,
        live_state: Any | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="F1 Starting Grid Coordinator",
            update_interval=None,
            config_entry=config_entry,
        )
        self._session_coord = session_coord
        self._bus = bus
        self._session = session or async_get_clientsession(hass)
        self._headers = {"User-Agent": str(user_agent)} if user_agent else None
        self._cache = cache
        self._inflight = inflight
        self._persist = persist_map
        self._persist_save = persist_save
        self._live_state = live_state
        self._unsubs: list[Callable[[], None]] = []
        self._archive_task: asyncio.Task | None = None
        self._archive_fetch_keys: set[tuple[str, str]] = set()

        self._weekend_key: str | None = None
        self._weekend_format = WEEKEND_FORMAT_UNKNOWN
        self._current_session: dict[str, Any] = {}
        self._current_status: str | None = None
        self._driver_identities: dict[str, dict[str, Any]] = {}
        self._qualifying_entries: dict[str, dict[str, dict[str, Any]]] = {
            CONTEXT_SPRINT: {},
            CONTEXT_RACE: {},
        }
        self._confirmed_grid_positions: dict[str, dict[str, int]] = {
            CONTEXT_SPRINT: {},
            CONTEXT_RACE: {},
        }
        self._state = self._empty_state()

    async def async_close(self, *_: Any) -> None:
        for unsub in list(self._unsubs):
            with suppress(Exception):
                unsub()
        self._unsubs.clear()
        if self._archive_task is not None:
            self._archive_task.cancel()
            with suppress(Exception):
                await self._archive_task
            self._archive_task = None

    def reset_runtime_state(self, reason: str = "runtime_reset") -> None:
        """Clear runtime grid state while preserving the known weekend shell."""
        self._driver_identities.clear()
        self._qualifying_entries = {CONTEXT_SPRINT: {}, CONTEXT_RACE: {}}
        self._confirmed_grid_positions = {CONTEXT_SPRINT: {}, CONTEXT_RACE: {}}
        self._archive_fetch_keys.clear()
        if self._archive_task is not None:
            self._archive_task.cancel()
            self._archive_task = None
        status = (
            STATUS_WAITING_SPRINT_QUALIFYING
            if self._weekend_format == WEEKEND_FORMAT_SPRINT
            else STATUS_WAITING_QUALIFYING
        )
        context = (
            CONTEXT_SPRINT
            if self._weekend_format == WEEKEND_FORMAT_SPRINT
            else CONTEXT_RACE
        )
        self._state.update(
            {
                "status": status,
                "grid_context": context,
                "source": None,
                "source_updated_at": None,
                "cleared_at": self._now_iso(),
                "cleared_reason": reason,
                "grid": [],
                "grid_count": 0,
            }
        )
        self._publish()

    async def async_config_entry_first_refresh(self) -> None:
        self.async_set_updated_data(await self._async_update_data())
        bus = self._bus
        if bus is None:
            with suppress(Exception):
                bus = self.hass.data.get(DOMAIN, {}).get("live_bus")
        if bus is None:
            return

        subscriptions = (
            ("SessionInfo", self._on_session_info),
            ("SessionStatus", self._on_session_status),
            ("DriverList", self._on_driver_list),
            ("TimingData", self._on_timing_data),
            ("TimingAppData", self._on_timing_app_data),
        )
        for stream, handler in subscriptions:
            with suppress(Exception):
                self._unsubs.append(bus.subscribe(stream, handler))

    async def _async_update_data(self) -> dict[str, Any]:
        if self._is_no_spoiler_active():
            return self._state
        if self._is_replay_active():
            return self._state
        self._sync_from_index_if_idle()
        return self._state

    def _empty_state(self) -> dict[str, Any]:
        return {
            "status": None,
            "grid_context": CONTEXT_NONE,
            "weekend_key": None,
            "weekend_format": WEEKEND_FORMAT_UNKNOWN,
            "meeting_name": None,
            "session_key": None,
            "source_session_name": None,
            "target_session_name": None,
            "source": None,
            "source_updated_at": None,
            "cleared_at": None,
            "cleared_reason": None,
            "grid": [],
            "grid_count": 0,
        }

    @staticmethod
    def _now_iso() -> str:
        return dt_util.utcnow().isoformat(timespec="seconds")

    def _publish(self) -> None:
        if self._is_no_spoiler_active():
            return
        self.async_set_updated_data(dict(self._state))

    def _is_replay_active(self) -> bool:
        reason = getattr(self._live_state, "reason", None)
        return str(reason or "") in REPLAY_REASONS

    def _is_no_spoiler_active(self) -> bool:
        if self._is_replay_active():
            return False
        try:
            mgr = (self.hass.data.get(DOMAIN) or {}).get(_NO_SPOILER_MANAGER_KEY)
            return mgr is not None and bool(mgr.is_active)
        except Exception:  # noqa: BLE001
            return False

    def _set_state_fields(self, **updates: Any) -> None:
        changed = False
        for key, value in updates.items():
            if self._state.get(key) != value:
                self._state[key] = value
                changed = True
        if changed:
            self._publish()

    def _clear_active_grid(
        self,
        reason: str,
        *,
        next_status: str,
        next_context: str,
        clear_context_data: str | None = None,
    ) -> None:
        if clear_context_data in (CONTEXT_SPRINT, CONTEXT_RACE):
            self._confirmed_grid_positions[clear_context_data].clear()

        self._state.update(
            {
                "status": next_status,
                "grid_context": next_context,
                "source_session_name": self._current_session.get("name"),
                "target_session_name": self._target_session_name(next_context),
                "source": None,
                "source_updated_at": None,
                "cleared_at": self._now_iso(),
                "cleared_reason": reason,
                "grid": [],
                "grid_count": 0,
            }
        )
        self._publish()

    def _reset_for_new_weekend(
        self, weekend_key: str, session_info: dict[str, Any]
    ) -> None:
        self._weekend_key = weekend_key
        self._weekend_format = self._detect_weekend_format(weekend_key)
        inferred = self._infer_weekend_format_from_session(session_info)
        if inferred != WEEKEND_FORMAT_UNKNOWN:
            self._weekend_format = inferred
        self._driver_identities.clear()
        self._qualifying_entries = {CONTEXT_SPRINT: {}, CONTEXT_RACE: {}}
        self._confirmed_grid_positions = {CONTEXT_SPRINT: {}, CONTEXT_RACE: {}}
        self._archive_fetch_keys.clear()
        if self._archive_task is not None:
            self._archive_task.cancel()
            self._archive_task = None

        status = (
            STATUS_WAITING_SPRINT_QUALIFYING
            if self._weekend_format == WEEKEND_FORMAT_SPRINT
            else STATUS_WAITING_QUALIFYING
        )
        context = (
            CONTEXT_SPRINT
            if self._weekend_format == WEEKEND_FORMAT_SPRINT
            else CONTEXT_RACE
        )
        self._state = self._empty_state()
        self._state.update(
            {
                "status": status,
                "grid_context": context,
                "weekend_key": weekend_key,
                "weekend_format": self._weekend_format,
                "meeting_name": self._meeting_name(session_info),
                "session_key": self._session_key(session_info),
                "source_session_name": self._session_name(session_info),
                "target_session_name": self._target_session_name(context),
                "cleared_at": self._now_iso(),
                "cleared_reason": "new_weekend",
            }
        )
        self._publish()

    def _sync_from_index_if_idle(self) -> None:
        if self._weekend_key:
            return
        session = self._current_or_next_index_session()
        if not session:
            return
        weekend_key = self._weekend_key_from_index_session(session)
        if not weekend_key:
            return
        self._weekend_key = weekend_key
        self._weekend_format = self._detect_weekend_format(weekend_key)
        status, context = self._initial_status_from_index(
            weekend_key, self._weekend_format
        )
        self._state.update(
            {
                "status": status,
                "grid_context": context,
                "weekend_key": weekend_key,
                "weekend_format": self._weekend_format,
                "meeting_name": self._index_meeting_name(session),
                "target_session_name": self._target_session_name(context),
            }
        )
        if context in (CONTEXT_SPRINT, CONTEXT_RACE):
            self._maybe_schedule_archive_fetch(context)

    def _on_session_info(self, payload: dict[str, Any]) -> None:
        if self._is_no_spoiler_active():
            return
        if self._is_replay_active():
            return
        if not isinstance(payload, dict):
            return
        weekend_key = self._weekend_key_from_session_info(payload)
        if weekend_key and weekend_key != self._weekend_key:
            self._reset_for_new_weekend(weekend_key, payload)
        elif weekend_key and not self._weekend_key:
            self._reset_for_new_weekend(weekend_key, payload)

        inferred = self._infer_weekend_format_from_session(payload)
        if (
            inferred != WEEKEND_FORMAT_UNKNOWN
            and inferred != self._weekend_format
            and self._weekend_format == WEEKEND_FORMAT_UNKNOWN
        ):
            self._weekend_format = inferred

        self._current_session = {
            "key": self._session_key(payload),
            "name": self._session_name(payload),
            "type": str(payload.get("Type") or ""),
            "path": str(payload.get("Path") or ""),
            "meeting_name": self._meeting_name(payload),
        }
        self._current_status = self._status_from_payload(payload)
        self._state.update(
            {
                "weekend_key": self._weekend_key,
                "weekend_format": self._weekend_format,
                "meeting_name": self._current_session.get("meeting_name"),
                "session_key": self._current_session.get("key"),
            }
        )
        self._apply_session_lifecycle()

    def _on_session_status(self, payload: dict[str, Any]) -> None:
        if self._is_no_spoiler_active():
            return
        if self._is_replay_active():
            return
        if not isinstance(payload, dict):
            return
        status = self._status_from_payload(payload)
        if not status:
            return
        self._current_status = status
        self._apply_session_lifecycle()

    def _apply_session_lifecycle(self) -> None:
        kind = self._current_session_kind()
        status = self._current_status
        if not status:
            return

        if kind in (SESSION_KIND_SPRINT_QUALIFYING, SESSION_KIND_QUALIFYING):
            context = (
                CONTEXT_SPRINT
                if kind == SESSION_KIND_SPRINT_QUALIFYING
                else CONTEXT_RACE
            )
            if status in STARTED_STATUSES:
                self._set_state_fields(
                    status=STATUS_COLLECTING,
                    grid_context=context,
                    source_session_name=self._current_session.get("name"),
                    target_session_name=self._target_session_name(context),
                    grid=[],
                    grid_count=0,
                    source=None,
                    source_updated_at=None,
                )
                return
            if status in FINISHED_STATUSES:
                self._build_provisional_grid(context, source=SOURCE_LIVE_QUALIFYING)
                return

        if kind == SESSION_KIND_SPRINT:
            if status in STARTED_STATUSES:
                self._set_state_fields(
                    grid_context=CONTEXT_SPRINT,
                    target_session_name="Sprint",
                )
                self._maybe_schedule_archive_fetch(CONTEXT_SPRINT)
                return
            if status in FINISHED_STATUSES:
                self._clear_active_grid(
                    "sprint_completed",
                    next_status=STATUS_WAITING_QUALIFYING,
                    next_context=CONTEXT_RACE,
                    clear_context_data=CONTEXT_SPRINT,
                )
                return

        if kind == SESSION_KIND_RACE:
            if status in STARTED_STATUSES:
                self._set_state_fields(
                    grid_context=CONTEXT_RACE,
                    target_session_name="Race",
                )
                self._maybe_schedule_archive_fetch(CONTEXT_RACE)
                return
            if status in FINISHED_STATUSES:
                self._clear_active_grid(
                    "race_completed",
                    next_status=STATUS_COMPLETED,
                    next_context=CONTEXT_NONE,
                    clear_context_data=CONTEXT_RACE,
                )

    def _on_driver_list(self, payload: dict[str, Any]) -> None:
        if self._is_no_spoiler_active():
            return
        if self._is_replay_active():
            return
        if not isinstance(payload, dict):
            return
        changed = self._merge_driver_list(payload)
        if not changed:
            return
        context = self._state.get("grid_context")
        status = self._state.get("status")
        if context in (CONTEXT_SPRINT, CONTEXT_RACE):
            if status == STATUS_CONFIRMED:
                self._build_confirmed_grid(context)
            elif status == STATUS_PROVISIONAL:
                self._build_provisional_grid(
                    context,
                    source=str(self._state.get("source") or SOURCE_LIVE_QUALIFYING),
                )

    def _on_timing_data(self, payload: dict[str, Any]) -> None:
        if self._is_no_spoiler_active():
            return
        if self._is_replay_active():
            return
        if not isinstance(payload, dict):
            return
        kind = self._current_session_kind()
        if kind not in (SESSION_KIND_SPRINT_QUALIFYING, SESSION_KIND_QUALIFYING):
            return
        context = (
            CONTEXT_SPRINT if kind == SESSION_KIND_SPRINT_QUALIFYING else CONTEXT_RACE
        )
        if self._merge_timing_data(payload, context):
            if self._current_status in FINISHED_STATUSES:
                self._build_provisional_grid(context, source=SOURCE_LIVE_QUALIFYING)
            elif self._state.get("status") != STATUS_COLLECTING:
                self._set_state_fields(
                    status=STATUS_COLLECTING,
                    grid_context=context,
                    source_session_name=self._current_session.get("name"),
                    target_session_name=self._target_session_name(context),
                )

    def _on_timing_app_data(self, payload: dict[str, Any]) -> None:
        if self._is_no_spoiler_active():
            return
        if self._is_replay_active():
            return
        if not isinstance(payload, dict):
            return
        kind = self._current_session_kind()
        if kind not in (SESSION_KIND_SPRINT, SESSION_KIND_RACE):
            return
        context = CONTEXT_SPRINT if kind == SESSION_KIND_SPRINT else CONTEXT_RACE
        lines = payload.get("Lines")
        if not isinstance(lines, dict):
            return

        changed = False
        positions = self._confirmed_grid_positions[context]
        for rn, data in lines.items():
            if not isinstance(data, dict):
                continue
            grid_pos = self._parse_int(data.get("GridPos"))
            if grid_pos is None:
                continue
            rn_key = str(rn)
            if positions.get(rn_key) != grid_pos:
                positions[rn_key] = grid_pos
                changed = True
        if changed:
            self._build_confirmed_grid(context)

    def _merge_driver_list(self, payload: dict[str, Any]) -> bool:
        changed = False
        for rn, raw in payload.items():
            if not isinstance(raw, dict):
                continue
            rn_key = str(raw.get("RacingNumber") or rn)
            identity = self._driver_identities.setdefault(rn_key, {})
            updates = {
                "racing_number": rn_key,
                "tla": raw.get("Tla"),
                "driver_name": raw.get("FullName") or raw.get("BroadcastName"),
                "team_name": raw.get("TeamName"),
                "team_color": self._normalize_team_color(raw.get("TeamColour")),
            }
            for key, value in updates.items():
                if value is not None and identity.get(key) != value:
                    identity[key] = value
                    changed = True
        return changed

    def _merge_timing_data(self, payload: dict[str, Any], context: str) -> bool:
        lines = payload.get("Lines")
        if not isinstance(lines, dict):
            return False
        changed = False
        entries = self._qualifying_entries[context]
        for rn, raw in lines.items():
            if not isinstance(raw, dict):
                continue
            rn_key = str(rn)
            entry = entries.setdefault(rn_key, {"racing_number": rn_key})
            updates: dict[str, Any] = {}
            position = self._parse_int(raw.get("Position"))
            if position is not None:
                updates["qualifying_position"] = position

            segment_times = self._extract_segment_times(
                raw.get("BestLapTimes"), context
            )
            if segment_times:
                updates["segment_times"] = segment_times

            best_lap = self._lap_payload(raw.get("BestLapTime"))
            if best_lap is not None and segment_times:
                matching_segment = next(
                    (
                        segment
                        for segment in segment_times
                        if segment.get("time") == best_lap.get("time")
                    ),
                    segment_times[-1],
                )
                best_lap["segment"] = matching_segment.get("segment")
            if best_lap is None and segment_times:
                best_lap = segment_times[-1]
            if best_lap is not None:
                updates["qualifying_time"] = best_lap.get("time")
                updates["qualifying_time_secs"] = best_lap.get("time_secs")
                updates["qualifying_lap"] = best_lap.get("lap")
                updates["qualifying_segment"] = best_lap.get("segment")

            for key, value in updates.items():
                if entry.get(key) != value:
                    entry[key] = value
                    changed = True
        return changed

    def _build_provisional_grid(self, context: str, *, source: str) -> None:
        rows: list[dict[str, Any]] = []
        for rn, entry in self._qualifying_entries.get(context, {}).items():
            qual_pos = self._parse_int(entry.get("qualifying_position"))
            if qual_pos is None:
                continue
            rows.append(
                self._build_grid_row(
                    rn,
                    context,
                    grid_position=qual_pos,
                    source=source,
                    qualifying_entry=entry,
                )
            )
        if not rows:
            return
        rows.sort(key=lambda row: int(row["grid_position"]))
        self._state.update(
            {
                "status": STATUS_PROVISIONAL,
                "grid_context": context,
                "source_session_name": self._current_session.get("name")
                or self._source_session_name(context),
                "target_session_name": self._target_session_name(context),
                "source": source,
                "source_updated_at": self._now_iso(),
                "cleared_at": None,
                "cleared_reason": None,
                "grid": rows,
                "grid_count": len(rows),
            }
        )
        self._publish()

    def _build_confirmed_grid(self, context: str) -> None:
        positions = self._confirmed_grid_positions.get(context, {})
        if not positions:
            return
        rows = []
        entries = self._qualifying_entries.get(context, {})
        for rn, grid_pos in positions.items():
            rows.append(
                self._build_grid_row(
                    rn,
                    context,
                    grid_position=grid_pos,
                    source=SOURCE_GRIDPOS,
                    qualifying_entry=entries.get(rn, {}),
                )
            )
        rows.sort(key=lambda row: int(row["grid_position"]))
        self._state.update(
            {
                "status": STATUS_CONFIRMED,
                "grid_context": context,
                "source_session_name": self._current_session.get("name"),
                "target_session_name": self._target_session_name(context),
                "source": SOURCE_GRIDPOS,
                "source_updated_at": self._now_iso(),
                "cleared_at": None,
                "cleared_reason": None,
                "grid": rows,
                "grid_count": len(rows),
            }
        )
        self._publish()

    def _build_grid_row(
        self,
        rn: str,
        context: str,
        *,
        grid_position: int,
        source: str,
        qualifying_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        q_entry = qualifying_entry or {}
        identity = self._driver_identities.get(str(rn), {})
        qual_pos = self._parse_int(q_entry.get("qualifying_position"))
        grid_delta = (
            grid_position - qual_pos if grid_position is not None and qual_pos else None
        )
        return {
            "grid_position": grid_position,
            "qualifying_position": qual_pos,
            "racing_number": str(rn),
            "tla": identity.get("tla"),
            "driver_name": identity.get("driver_name"),
            "team_name": identity.get("team_name"),
            "team_color": identity.get("team_color"),
            "qualifying_time": q_entry.get("qualifying_time"),
            "qualifying_time_secs": q_entry.get("qualifying_time_secs"),
            "qualifying_segment": q_entry.get("qualifying_segment"),
            "qualifying_lap": q_entry.get("qualifying_lap"),
            "segment_times": q_entry.get("segment_times", []),
            "grid_delta": grid_delta,
            "changed_from_qualifying": grid_delta is not None and grid_delta != 0,
            "source": source,
            "grid_context": context,
        }

    def _maybe_schedule_archive_fetch(self, context: str) -> None:
        if self._is_no_spoiler_active():
            return
        if self._is_replay_active():
            return
        if self._qualifying_entries.get(context):
            return
        session = self._index_source_session(context)
        path = str((session or {}).get("Path") or "").strip("/")
        if not path:
            return
        key = (context, path)
        if key in self._archive_fetch_keys:
            return
        self._archive_fetch_keys.add(key)

        async def _runner() -> None:
            await self._fetch_archive_context(context, path)

        self._archive_task = self.hass.async_create_task(_runner())

    async def _fetch_archive_context(self, context: str, path: str) -> None:
        try:
            if self._is_no_spoiler_active():
                return
            if self._is_replay_active():
                return
            driver_list = await self._fetch_stream(path, "DriverList")
            if self._is_no_spoiler_active():
                return
            if self._is_replay_active():
                return
            if driver_list:
                for payload in self._iter_json_stream(driver_list):
                    self._merge_driver_list(payload)

            timing_data = await self._fetch_stream(path, "TimingData")
            if self._is_no_spoiler_active():
                return
            if self._is_replay_active():
                return
            if timing_data:
                for payload in self._iter_json_stream(timing_data):
                    self._merge_timing_data(payload, context)
                self._build_provisional_grid(context, source=SOURCE_ARCHIVE)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Starting grid archive fetch failed for %s: %s", path, err)

    async def _fetch_stream(self, path: str, stream: str) -> str | None:
        url = f"{STATIC_BASE}/{path.strip('/')}/{stream}.jsonStream"
        try:
            return await fetch_text(
                self.hass,
                self._session,
                url,
                headers=self._headers,
                ttl_seconds=3600,
                cache=self._cache,
                inflight=self._inflight,
                persist_map=self._persist,
                persist_save=self._persist_save,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Starting grid %s archive unavailable: %s", stream, err)
            return None

    @staticmethod
    def _iter_json_stream(text: str) -> Iterable[dict[str, Any]]:
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            json_start = line.find("{")
            if json_start < 0:
                continue
            try:
                payload = json.loads(line[json_start:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload

    def _index_source_session(self, context: str) -> dict[str, Any] | None:
        expected_kind = (
            SESSION_KIND_SPRINT_QUALIFYING
            if context == CONTEXT_SPRINT
            else SESSION_KIND_QUALIFYING
        )
        for session in self._index_sessions_for_weekend(self._weekend_key):
            if (
                self._session_kind_from_values(session.get("Name"), session.get("Type"))
                == expected_kind
            ):
                return session
        return None

    def _detect_weekend_format(self, weekend_key: str | None) -> str:
        if not weekend_key:
            return WEEKEND_FORMAT_UNKNOWN
        kinds = {
            self._session_kind_from_values(session.get("Name"), session.get("Type"))
            for session in self._index_sessions_for_weekend(weekend_key)
        }
        if SESSION_KIND_SPRINT_QUALIFYING in kinds and SESSION_KIND_SPRINT in kinds:
            return WEEKEND_FORMAT_SPRINT
        if SESSION_KIND_QUALIFYING in kinds and SESSION_KIND_RACE in kinds:
            return WEEKEND_FORMAT_NORMAL
        return WEEKEND_FORMAT_UNKNOWN

    def _infer_weekend_format_from_session(self, session_info: dict[str, Any]) -> str:
        kind = self._session_kind_from_values(
            session_info.get("Name"), session_info.get("Type")
        )
        if kind in (SESSION_KIND_SPRINT_QUALIFYING, SESSION_KIND_SPRINT):
            return WEEKEND_FORMAT_SPRINT
        if kind in (SESSION_KIND_QUALIFYING, SESSION_KIND_RACE):
            return (
                self._weekend_format
                if self._weekend_format != WEEKEND_FORMAT_UNKNOWN
                else WEEKEND_FORMAT_NORMAL
            )
        return WEEKEND_FORMAT_UNKNOWN

    def _current_or_next_index_session(self) -> dict[str, Any] | None:
        sessions = list(self._iter_index_sessions())
        if not sessions:
            return None
        now = dt_util.utcnow()

        def session_start(session: dict[str, Any]) -> datetime | None:
            return self._parse_session_datetime(
                session.get("StartDate"), session.get("GmtOffset")
            )

        def session_end(session: dict[str, Any]) -> datetime | None:
            return self._parse_session_datetime(
                session.get("EndDate"), session.get("GmtOffset")
            )

        active: list[dict[str, Any]] = []
        future: list[tuple[datetime, dict[str, Any]]] = []
        recent: list[tuple[datetime, dict[str, Any]]] = []
        for session in sessions:
            start = session_start(session)
            end = session_end(session) or start
            if start is None:
                continue
            if end is not None and start - timedelta(hours=2) <= now <= end + timedelta(
                hours=3
            ):
                active.append(session)
            elif start > now:
                future.append((start, session))
            elif end is not None:
                recent.append((end, session))
        if active:
            active.sort(
                key=lambda session: (
                    session_start(session) or datetime.max.replace(tzinfo=UTC)
                )
            )
            return active[0]
        if future:
            future.sort(key=lambda item: item[0])
            return future[0][1]
        if recent:
            recent.sort(key=lambda item: item[0], reverse=True)
            return recent[0][1]
        return None

    def _initial_status_from_index(
        self, weekend_key: str, weekend_format: str
    ) -> tuple[str, str]:
        sessions = list(self._index_sessions_for_weekend(weekend_key))
        now = dt_util.utcnow()

        def kind_session(kind: str) -> dict[str, Any] | None:
            for session in sessions:
                if (
                    self._session_kind_from_values(
                        session.get("Name"), session.get("Type")
                    )
                    == kind
                ):
                    return session
            return None

        def start(session: dict[str, Any] | None) -> datetime | None:
            if session is None:
                return None
            return self._parse_session_datetime(
                session.get("StartDate"), session.get("GmtOffset")
            )

        def end(session: dict[str, Any] | None) -> datetime | None:
            if session is None:
                return None
            return self._parse_session_datetime(
                session.get("EndDate"), session.get("GmtOffset")
            )

        race = kind_session(SESSION_KIND_RACE)
        race_end = end(race)
        if race_end is not None and now > race_end:
            return STATUS_COMPLETED, CONTEXT_NONE

        qualifying = kind_session(SESSION_KIND_QUALIFYING)
        qualifying_start = start(qualifying)
        qualifying_end = end(qualifying)
        if weekend_format == WEEKEND_FORMAT_SPRINT:
            sprint = kind_session(SESSION_KIND_SPRINT)
            sprint_qualifying = kind_session(SESSION_KIND_SPRINT_QUALIFYING)
            sprint_start = start(sprint)
            sprint_end = end(sprint)
            sprint_qualifying_start = start(sprint_qualifying)
            sprint_qualifying_end = end(sprint_qualifying)
            if sprint_end is not None and now > sprint_end:
                if qualifying_start is not None and now >= qualifying_start:
                    return STATUS_COLLECTING, CONTEXT_RACE
                return STATUS_WAITING_QUALIFYING, CONTEXT_RACE
            if sprint_start is not None and now >= sprint_start:
                return STATUS_COLLECTING, CONTEXT_SPRINT
            if sprint_qualifying_end is not None and now > sprint_qualifying_end:
                return STATUS_WAITING_SPRINT_QUALIFYING, CONTEXT_SPRINT
            if sprint_qualifying_start is not None and now >= sprint_qualifying_start:
                return STATUS_COLLECTING, CONTEXT_SPRINT
            return STATUS_WAITING_SPRINT_QUALIFYING, CONTEXT_SPRINT

        if qualifying_start is not None and now >= qualifying_start:
            if qualifying_end is not None and now > qualifying_end:
                return STATUS_WAITING_QUALIFYING, CONTEXT_RACE
            return STATUS_COLLECTING, CONTEXT_RACE
        return STATUS_WAITING_QUALIFYING, CONTEXT_RACE

    def _index_sessions_for_weekend(
        self, weekend_key: str | None
    ) -> Iterable[dict[str, Any]]:
        if not weekend_key:
            return []
        return [
            session
            for session in self._iter_index_sessions()
            if self._weekend_key_from_index_session(session) == weekend_key
        ]

    def _iter_index_sessions(self) -> Iterable[dict[str, Any]]:
        data = getattr(self._session_coord, "data", None)
        if not isinstance(data, dict):
            return []
        meetings = data.get("Meetings") or data.get("meetings") or []
        if isinstance(meetings, dict):
            meetings = list(meetings.values())
        if not isinstance(meetings, list):
            return []
        sessions: list[dict[str, Any]] = []
        for meeting in meetings:
            if not isinstance(meeting, dict):
                continue
            meeting_sessions = meeting.get("Sessions") or meeting.get("sessions") or []
            if isinstance(meeting_sessions, dict):
                meeting_sessions = list(meeting_sessions.values())
            if not isinstance(meeting_sessions, list):
                continue
            for session in meeting_sessions:
                if not isinstance(session, dict):
                    continue
                item = dict(session)
                item["_meeting"] = meeting
                sessions.append(item)
        return sessions

    def _weekend_key_from_session_info(self, payload: dict[str, Any]) -> str | None:
        meeting = payload.get("Meeting")
        if isinstance(meeting, dict):
            key = meeting.get("Key")
            if key is not None:
                return f"meeting:{key}"
        return self._weekend_key_from_path(payload.get("Path"))

    def _weekend_key_from_index_session(self, session: dict[str, Any]) -> str | None:
        meeting = session.get("_meeting")
        if isinstance(meeting, dict):
            key = meeting.get("Key")
            if key is not None:
                return f"meeting:{key}"
        return self._weekend_key_from_path(session.get("Path"))

    @staticmethod
    def _weekend_key_from_path(path: Any) -> str | None:
        if not isinstance(path, str) or not path.strip():
            return None
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"path:{parts[0]}/{parts[1]}"
        return f"path:{path.strip('/')}"

    @staticmethod
    def _session_kind_from_values(name: Any, session_type: Any) -> str:
        name_l = str(name or "").strip().lower()
        type_l = str(session_type or "").strip().lower()
        if "sprint qualifying" in name_l or "sprint shootout" in name_l:
            return SESSION_KIND_SPRINT_QUALIFYING
        if name_l == "qualifying" or (
            "qualifying" in name_l and "sprint" not in name_l
        ):
            return SESSION_KIND_QUALIFYING
        if name_l == "sprint" or ("sprint" in name_l and type_l == "race"):
            return SESSION_KIND_SPRINT
        if name_l == "race" or (type_l == "race" and "sprint" not in name_l):
            return SESSION_KIND_RACE
        if type_l == "practice" or "practice" in name_l:
            return SESSION_KIND_PRACTICE
        return SESSION_KIND_OTHER

    def _current_session_kind(self) -> str:
        return self._session_kind_from_values(
            self._current_session.get("name"), self._current_session.get("type")
        )

    @staticmethod
    def _status_from_payload(payload: dict[str, Any]) -> str | None:
        for key in ("Status", "SessionStatus", "Started", "Message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _session_name(payload: dict[str, Any]) -> str | None:
        name = payload.get("Name")
        return str(name).strip() if name is not None else None

    @staticmethod
    def _session_key(payload: dict[str, Any]) -> str | None:
        key = payload.get("Key")
        return str(key).strip() if key is not None else None

    @staticmethod
    def _meeting_name(payload: dict[str, Any]) -> str | None:
        meeting = payload.get("Meeting")
        if isinstance(meeting, dict):
            name = meeting.get("Name") or meeting.get("OfficialName")
            return str(name).strip() if name is not None else None
        return None

    @staticmethod
    def _index_meeting_name(session: dict[str, Any]) -> str | None:
        meeting = session.get("_meeting")
        if isinstance(meeting, dict):
            name = meeting.get("Name") or meeting.get("OfficialName")
            return str(name).strip() if name is not None else None
        return None

    @staticmethod
    def _target_session_name(context: str) -> str | None:
        if context == CONTEXT_SPRINT:
            return "Sprint"
        if context == CONTEXT_RACE:
            return "Race"
        return None

    @staticmethod
    def _source_session_name(context: str) -> str | None:
        if context == CONTEXT_SPRINT:
            return "Sprint Qualifying"
        if context == CONTEXT_RACE:
            return "Qualifying"
        return None

    def _extract_segment_times(self, raw: Any, context: str) -> list[dict[str, Any]]:
        if isinstance(raw, dict):
            items = raw.items()
        elif isinstance(raw, list):
            items = enumerate(raw)
        else:
            return []
        prefix = "SQ" if context == CONTEXT_SPRINT else "Q"
        segments: list[dict[str, Any]] = []
        for idx_raw, payload in items:
            if not isinstance(payload, dict) or not payload:
                continue
            try:
                idx = int(idx_raw) + 1
            except (TypeError, ValueError):
                continue
            if idx not in (1, 2, 3):
                continue
            lap = self._lap_payload(payload, segment=f"{prefix}{idx}")
            if lap is not None:
                segments.append(lap)
        segments.sort(key=lambda item: str(item.get("segment") or ""))
        return segments

    def _lap_payload(
        self, raw: Any, *, segment: str | None = None
    ) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        value = str(raw.get("Value") or "").strip()
        if not value:
            return None
        return {
            "segment": segment,
            "time": value,
            "time_secs": self._parse_lap_time_secs(value),
            "lap": self._parse_int(raw.get("Lap")),
        }

    @staticmethod
    def _parse_lap_time_secs(value: str | None) -> float | None:
        if not value:
            return None
        try:
            text = value.strip()
            if ":" in text:
                minutes, seconds = text.split(":", 1)
                return int(minutes) * 60.0 + float(seconds)
            return float(text)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            if isinstance(value, int):
                return value
            text = str(value).strip()
            if not text:
                return None
            if text.isdigit():
                return int(text)
            return int(float(text))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_team_color(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        color = value.strip()
        return color if color.startswith("#") else f"#{color}"

    @staticmethod
    def _parse_session_datetime(value: Any, gmt_offset: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            text = value.strip()
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                offset = str(gmt_offset or "").strip()
                if offset:
                    sign = -1 if offset.startswith("-") else 1
                    clean = offset.lstrip("+-")
                    parts = clean.split(":")
                    hours = int(parts[0]) if parts and parts[0] else 0
                    minutes = int(parts[1]) if len(parts) > 1 else 0
                    dt = dt.replace(tzinfo=UTC) - sign * timedelta(
                        hours=hours, minutes=minutes
                    )
                    return dt.astimezone(UTC)
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except (TypeError, ValueError):
            return None
