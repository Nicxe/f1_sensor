"""Shared static data projections; no Entity subclasses or HA state publication."""

from __future__ import annotations

from contextlib import suppress
from copy import deepcopy
import datetime
import re
from zoneinfo import ZoneInfo

from .card_data_models import DataSnapshot
from .const import (
    RACE_SWITCH_GRACE,
)
from .data_helpers import (
    _combine_date_time,
    _timezone_from_circuit,
    _to_float_value,
    _to_home,
    _to_local,
)
from .entity import (
    entry_runtime_registry,
)
from .helpers import (
    get_circuit_map_url,
    get_circuit_outline_url,
    get_country_code,
    get_country_flag_url,
    get_next_race,
)
from .race_weather import legacy_weather_observation, weather_icon


class ProjectionModel:
    """A calculation context; never a Home Assistant entity."""

    def __init__(self, coordinator, unique_id=None, entry_id=None, device_name=None):
        self.coordinator = coordinator
        self.hass = getattr(coordinator, "hass", None)
        self._entry_id = entry_id
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._history_coordinator = None

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def available(self):
        return bool(getattr(self.coordinator, "last_update_success", True))

    @property
    def state(self):
        return self.native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    def snapshot(self):
        self._history_coordinator = entry_runtime_registry(
            self.hass, self._entry_id
        ).get("next_race_history_coordinator")
        if hasattr(self, "_recompute"):
            self._recompute()
        elif hasattr(self, "_refresh_cached_state"):
            self._refresh_cached_state()
        elif hasattr(self, "_update_from_coordinator"):
            self._update_from_coordinator()
        return DataSnapshot(self.state, deepcopy(self.extra_state_attributes))


class NextRaceProjection(ProjectionModel):
    """Projection extracted from _NextRaceMixin; shared with its entity adapter."""

    def _get_next_race(self, *, default_time: str = "00:00:00Z") -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        _, race = get_next_race(
            races, grace=RACE_SWITCH_GRACE, default_time=default_time
        )
        return race


class PointsProjection(ProjectionModel):
    """Projection extracted from _PointsProgressionBase; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    def _get_sprint_results(self) -> list:
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            sprint_coord = reg.get("sprint_results_coordinator")
            if sprint_coord and isinstance(sprint_coord.data, dict):
                return (
                    sprint_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []


class NextRaceModel(NextRaceProjection, ProjectionModel):
    """Projection extracted from F1NextRaceSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._history_coordinator = None

    def _history_attributes(self) -> dict:
        data = getattr(self._history_coordinator, "data", None)
        return data if isinstance(data, dict) else {}

    def _refresh_cached_state(self) -> None:
        race = self._get_next_race()
        if not race:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = _timezone_from_circuit(circuit)
        first_practice = race.get("FirstPractice", {})
        second_practice = race.get("SecondPractice", {})
        third_practice = race.get("ThirdPractice", {})
        qualifying = race.get("Qualifying", {})
        sprint_qualifying = race.get("SprintQualifying", {})
        sprint = race.get("Sprint", {})
        race_start = _combine_date_time(
            race.get("date"), race.get("time"), force_utc=True
        )
        first_start = _combine_date_time(
            first_practice.get("date"), first_practice.get("time"), force_utc=True
        )
        second_start = _combine_date_time(
            second_practice.get("date"), second_practice.get("time"), force_utc=True
        )
        third_start = _combine_date_time(
            third_practice.get("date"), third_practice.get("time"), force_utc=True
        )
        qual_start = _combine_date_time(
            qualifying.get("date"), qualifying.get("time"), force_utc=True
        )
        sprint_quali_start = _combine_date_time(
            sprint_qualifying.get("date"), sprint_qualifying.get("time"), force_utc=True
        )
        sprint_start = _combine_date_time(
            sprint.get("date"), sprint.get("time"), force_utc=True
        )
        attrs = {
            "season": race.get("season"),
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "scheduled_laps": race.get("scheduled_laps"),
            "sprint_scheduled_laps": sprint.get("scheduled_laps"),
            "race_url": race.get("url"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "circuit_lat": loc.get("lat"),
            "circuit_long": loc.get("long"),
            "circuit_locality": loc.get("locality"),
            "circuit_country": loc.get("country"),
            "country_code": get_country_code(loc.get("country")),
            "country_flag_url": get_country_flag_url(loc.get("country")),
            "circuit_map_url": get_circuit_map_url(
                circuit.get("circuitId"), race.get("season")
            ),
            "circuit_outline_url": get_circuit_outline_url(
                circuit.get("circuitId"), race.get("season")
            ),
            "circuit_timezone": timezone,
        }

        def _populate(label, iso_value):
            attrs[f"{label}_utc"] = iso_value
            attrs[label] = _to_home(self.hass, iso_value)
            attrs[f"{label}_local"] = _to_local(iso_value, timezone)

        _populate("race_start", race_start)
        _populate("first_practice_start", first_start)
        _populate("second_practice_start", second_start)
        _populate("third_practice_start", third_start)
        _populate("qualifying_start", qual_start)
        _populate("sprint_qualifying_start", sprint_quali_start)
        _populate("sprint_start", sprint_start)
        attrs.update(self._history_attributes())
        self._attr_native_value = race_start
        self._attr_extra_state_attributes = attrs

    @property
    def state(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes


class TrackTimeModel(NextRaceProjection, ProjectionModel):
    """Projection extracted from F1TrackTimeSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._unsub_timer = None

    def _get_circuit_timezone(self, race):
        if not race:
            return None
        return _timezone_from_circuit(race.get("Circuit", {}))

    @property
    def available(self):
        if not super().available:
            return False
        race = self._get_next_race()
        if not race:
            return False
        return self._get_circuit_timezone(race) is not None

    @property
    def state(self):
        race = self._get_next_race()
        tz_name = self._get_circuit_timezone(race)
        if not tz_name:
            return None
        now_utc = datetime.datetime.now(datetime.UTC)
        now_track = now_utc.astimezone(ZoneInfo(tz_name))
        return now_track.strftime("%H:%M")

    @property
    def extra_state_attributes(self):
        race = self._get_next_race()
        if not race:
            return {}
        tz_name = self._get_circuit_timezone(race)
        if not tz_name:
            return {}
        circuit = race.get("Circuit", {})
        now_utc = datetime.datetime.now(datetime.UTC)
        now_track = now_utc.astimezone(ZoneInfo(tz_name))
        home_tz_name = getattr(self.hass.config, "time_zone", None)
        offset_from_home = None
        if home_tz_name:
            now_home = now_utc.astimezone(ZoneInfo(home_tz_name))
            diff_seconds = (
                now_track.utcoffset() - now_home.utcoffset()
            ).total_seconds()
            diff_hours = diff_seconds / 3600
            offset_from_home = f"{diff_hours:+.1f}h"
        return {
            "timezone": tz_name,
            "track_datetime_utc": now_utc.isoformat(timespec="seconds"),
            "track_datetime_local": now_track.isoformat(timespec="seconds"),
            "utc_offset": now_track.strftime("%z"),
            "offset_from_home": offset_from_home,
            "circuit_name": circuit.get("circuitName"),
            "circuit_locality": circuit.get("Location", {}).get("locality"),
            "circuit_country": circuit.get("Location", {}).get("country"),
        }


class CurrentSeasonModel(ProjectionModel):
    """Projection extracted from F1CurrentSeasonSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    @property
    def state(self):
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return len(races)

    @property
    def extra_state_attributes(self):
        table = (self.coordinator.data or {}).get("MRData", {}).get("RaceTable", {})
        races = table.get("Races", [])
        enriched_races = []
        for race in races:
            enriched = dict(race)
            circuit = race.get("Circuit", {})
            country = circuit.get("Location", {}).get("country")
            enriched["country_code"] = get_country_code(country)
            enriched["country_flag_url"] = get_country_flag_url(country)
            enriched["circuit_map_url"] = get_circuit_map_url(
                circuit.get("circuitId"), race.get("season")
            )
            enriched["circuit_outline_url"] = get_circuit_outline_url(
                circuit.get("circuitId"), race.get("season")
            )
            enriched_races.append(enriched)
        return {"season": table.get("season"), "races": enriched_races}


class WeatherModel(ProjectionModel):
    """Projection extracted from F1WeatherSensor; shared with its entity adapter."""

    @property
    def _weather_data(self) -> dict:
        """Return the shared coordinator snapshot."""
        data = self.coordinator.data
        return data if isinstance(data, dict) else {}

    @property
    def available(self) -> bool:
        """Return whether current next-race weather is available."""
        current = self._weather_data.get("current", {})
        return super().available and current.get("temperature") is not None

    @property
    def icon(self):
        """Return an icon matching the current normalized condition."""
        current = self._weather_data.get("current", {})
        return weather_icon(current.get("weather_code"), current.get("is_daytime"))

    @property
    def native_value(self):
        """Return the current circuit temperature."""
        return self._weather_data.get("current", {}).get("temperature")

    @property
    def extra_state_attributes(self):
        """Preserve the established current_* and race_* sensor attributes."""
        data = self._weather_data
        current = legacy_weather_observation(data.get("current"))
        race = legacy_weather_observation(data.get("race"))
        race["weather_icon"] = (
            weather_icon(
                data.get("race", {}).get("weather_code"),
                data.get("race", {}).get("is_daytime"),
            )
            if data.get("race")
            else None
        )
        attrs = dict(data.get("circuit", {}))
        attrs.update({f"current_{key}": value for key, value in current.items()})
        attrs.update({f"race_{key}": value for key, value in race.items()})
        return attrs


class LastRaceModel(ProjectionModel):
    """Projection extracted from F1LastRaceSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    @property
    def state(self):
        races = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        if not races:
            return None
        results = races[0].get("Results", [])
        winner = next((r for r in results if r.get("positionText") == "1"), None)
        return winner.get("Driver", {}).get("familyName") if winner else None

    @property
    def extra_state_attributes(self):
        races = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        if not races:
            return {}
        race = races[0]

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
                "grid": r.get("grid"),
                "laps": r.get("laps"),
                "time": (r.get("Time") or {}).get("time"),
                "points": r.get("points"),
                "status": r.get("status"),
                "driver": {
                    "permanentNumber": r.get("Driver", {}).get("permanentNumber"),
                    "code": r.get("Driver", {}).get("code"),
                    "givenName": r.get("Driver", {}).get("givenName"),
                    "familyName": r.get("Driver", {}).get("familyName"),
                },
                "constructor": {
                    "constructorId": r.get("Constructor", {}).get("constructorId"),
                    "name": r.get("Constructor", {}).get("name"),
                },
            }

        results = [_clean_result(r) for r in race.get("Results", [])]
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = _timezone_from_circuit(circuit)
        race_start = _combine_date_time(
            race.get("date"), race.get("time"), force_utc=True
        )
        attrs = {
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "race_url": race.get("url"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "circuit_lat": loc.get("lat"),
            "circuit_long": loc.get("long"),
            "circuit_locality": loc.get("locality"),
            "circuit_country": loc.get("country"),
            "circuit_timezone": timezone,
            "results": results,
        }
        attrs["race_start_utc"] = race_start
        attrs["race_start"] = _to_home(self.hass, race_start)
        attrs["race_start_local"] = _to_local(race_start, timezone)
        return attrs


class SeasonResultsModel(ProjectionModel):
    """Projection extracted from F1SeasonResultsSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    @property
    def state(self):
        races = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        return len(races)

    @property
    def extra_state_attributes(self):
        races = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
                "grid": r.get("grid"),
                "laps": r.get("laps"),
                "time": (r.get("Time") or {}).get("time"),
                "points": r.get("points"),
                "status": r.get("status"),
                "driver": {
                    "permanentNumber": r.get("Driver", {}).get("permanentNumber"),
                    "code": r.get("Driver", {}).get("code"),
                    "givenName": r.get("Driver", {}).get("givenName"),
                    "familyName": r.get("Driver", {}).get("familyName"),
                },
                "constructor": {
                    "constructorId": r.get("Constructor", {}).get("constructorId"),
                    "name": r.get("Constructor", {}).get("name"),
                },
            }

        cleaned = []
        for race in races:
            results = [_clean_result(r) for r in race.get("Results", [])]
            cleaned.append(
                {
                    "round": race.get("round"),
                    "race_name": race.get("raceName"),
                    "results": results,
                }
            )
        return {"races": cleaned}


class SprintResultsModel(ProjectionModel):
    """Projection extracted from F1SprintResultsSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    def _get_races(self):
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return races or []

    @staticmethod
    def _clean_result(result: dict) -> dict:
        driver = result.get("Driver", {}) or {}
        constructor = result.get("Constructor", {}) or {}
        return {
            "number": result.get("number"),
            "position": result.get("position"),
            "grid": result.get("grid"),
            "laps": result.get("laps"),
            "time": (result.get("Time") or {}).get("time"),
            "points": result.get("points"),
            "status": result.get("status"),
            "driver": {
                "permanentNumber": driver.get("permanentNumber"),
                "code": driver.get("code"),
                "givenName": driver.get("givenName"),
                "familyName": driver.get("familyName"),
            },
            "constructor": {"name": constructor.get("name")},
        }

    @property
    def state(self):
        races = self._get_races()
        if not races:
            return 0
        return sum(1 for race in races if race.get("SprintResults"))

    @property
    def extra_state_attributes(self):
        races = self._get_races()
        cleaned = []
        for race in races:
            sprint_results = race.get("SprintResults") or []
            sprint_payload = [self._clean_result(result) for result in sprint_results]
            cleaned.append(
                {
                    "round": race.get("round"),
                    "race_name": race.get("raceName"),
                    "results": sprint_payload,
                }
            )
        return {"races": cleaned}


class LapPositionProgressionModel(ProjectionModel):
    """Projection extracted from F1LapPositionProgressionSensor; shared with its entity adapter."""

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)

    def _get_sessions(self) -> list[dict]:
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            return []
        return [session for session in sessions if isinstance(session, dict)]

    @staticmethod
    def _clean_session(session: dict) -> dict:
        return {
            "key": session.get("key"),
            "type": session.get("type"),
            "status": session.get("status"),
            "source": session.get("source"),
            "reason": session.get("reason"),
            "season": session.get("season"),
            "round": session.get("round"),
            "race_name": session.get("race_name"),
            "date": session.get("date"),
            "total_laps": session.get("total_laps"),
            "driver_count": session.get("driver_count"),
        }

    @property
    def state(self):
        valid_statuses = {"available", "pending", "unsupported", "error"}
        return sum(
            1
            for session in self._get_sessions()
            if session.get("status") in valid_statuses
        )

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}
        return {
            "season": data.get("season"),
            "source": data.get("source") or "jolpica",
            "updated_at": data.get("updated_at"),
            "data_mode": data.get("data_mode") or "metadata",
            "session_data_api": data.get("session_data_api") or "websocket",
            "session_data_type": data.get("session_data_type")
            or "f1_sensor/lap_position/session",
            "sessions": [
                self._clean_session(session) for session in self._get_sessions()
            ],
        }


class FiaDocumentsModel(ProjectionModel):
    """Projection extracted from F1FiaDocumentsSensor; shared with its entity adapter."""

    _DOC1_RESET_PATTERN = re.compile(
        "\\bdoc(?:ument)?(?:\\s+(?:no\\.?|number))?\\s*0*1\\b", re.IGNORECASE
    )
    _DOC_NUMBER_RE = re.compile(
        "\\bdoc(?:ument)?(?:\\s+(?:no\\.?|number))?\\s*0*(\\d+)\\b", re.IGNORECASE
    )

    def __init__(self, coordinator, unique_id, entry_id, device_name):
        super().__init__(coordinator, unique_id, entry_id, device_name)
        self._attr_native_value = 0
        self._attr_extra_state_attributes = self._build_attributes(None, [], None)
        self._documents: list[dict] = []
        self._seen_urls: set[str] = set()
        self._event_key: str | None = None
        self._race: dict | None = None

    def _update_from_coordinator(self, force: bool = False) -> bool:
        data = self.coordinator.data or {}
        updated = False
        event_key = data.get("event_key")
        race = data.get("race") if isinstance(data.get("race"), dict) else None
        documents = (
            data.get("documents") if isinstance(data.get("documents"), list) else []
        )
        if isinstance(event_key, str) and event_key and (event_key != self._event_key):
            self._event_key = event_key
            self._race = race
            self._documents = []
            self._seen_urls = set()
            updated = True
        elif race != self._race:
            self._race = race
            updated = True
        for doc in reversed(documents):
            if not isinstance(doc, dict):
                continue
            url = str(doc.get("url") or "").strip()
            if not url:
                continue
            is_new = url not in self._seen_urls
            if is_new and self._should_reset_for_doc(doc):
                if self._documents or self._seen_urls:
                    self._documents = []
                    self._seen_urls = set()
                    updated = True
            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)
            self._documents.append(doc)
            updated = True
        if len(self._documents) > 100:
            excess = len(self._documents) - 100
            for _ in range(excess):
                removed = self._documents.pop(0)
                url = str(removed.get("url") or "").strip()
                if url in self._seen_urls:
                    self._seen_urls.remove(url)
            updated = True
        self._sort_documents()
        latest = (
            self._select_latest_document(self._documents) if self._documents else None
        )
        new_state = self._extract_doc_number(latest.get("name")) if latest else 0
        attrs = self._build_attributes(latest, self._documents, self._race)
        if (
            force
            or new_state != self._attr_native_value
            or attrs != self._attr_extra_state_attributes
        ):
            self._attr_native_value = new_state
            self._attr_extra_state_attributes = attrs
            updated = True
        return updated

    @classmethod
    def _should_reset_for_doc(cls, doc: dict) -> bool:
        """Return True when a newly-seen doc indicates a fresh race weekend (Document 1)."""
        name = doc.get("name")
        if not isinstance(name, str):
            return False
        normalized = " ".join(name.split())
        if not normalized:
            return False
        return bool(cls._DOC1_RESET_PATTERN.search(normalized))

    @staticmethod
    def _published_timestamp(doc: dict) -> float | None:
        published = doc.get("published")
        if not isinstance(published, str) or not published:
            return None
        try:
            dt = datetime.datetime.fromisoformat(published.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.UTC)
            return dt.timestamp()
        except Exception:
            return None

    def _sort_documents(self) -> None:
        if not self._documents:
            return
        indexed = list(enumerate(self._documents))

        def sort_key(item):
            idx, doc = item
            ts = self._published_timestamp(doc)
            return (0 if ts is not None else 1, ts if ts is not None else 0.0, idx)

        indexed.sort(key=sort_key)
        self._documents = [doc for _, doc in indexed]

    @classmethod
    def _extract_doc_number(cls, name: str | None) -> int:
        """Extract the document number from a FIA document name like 'Doc 27 - ...'."""
        if not isinstance(name, str) or not name:
            return 0
        match = cls._DOC_NUMBER_RE.search(name)
        if not match:
            return 0
        try:
            return int(match.group(1))
        except Exception:
            return 0

    @classmethod
    def _select_latest_document(cls, docs: list[dict]) -> dict | None:
        """Select the latest document, preferring highest document number, then most recent published time.

        In practice the FIA HTML is not always consistent about the "Published on"
        metadata, but the document number monotonically increases for a given
        event. Using the doc number as the primary key guarantees that we do not
        regress from e.g. Doc 56 back to Doc 1 when some links lack a published
        timestamp or use an unparseable format.
        """
        if not isinstance(docs, list) or not docs:
            return None
        best_doc: dict | None = None
        best_num: int = -1
        best_ts: float | None = None
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            num = cls._extract_doc_number(doc.get("name"))
            ts = cls._published_timestamp(doc)
            if num > best_num:
                best_doc = doc
                best_num = num
                best_ts = ts
                continue
            if num < best_num:
                continue
            if ts is not None and (best_ts is None or ts > best_ts):
                best_doc = doc
                best_ts = ts
        return best_doc or docs[-1]

    @classmethod
    def _clean_document_attribute(cls, doc: dict | None) -> dict:
        """Return a compact, stable document shape for state attributes."""
        if not isinstance(doc, dict) or not doc:
            return {}
        name = doc.get("name")
        number = cls._extract_doc_number(name)
        cleaned = {
            "name": name,
            "url": doc.get("url"),
            "published": doc.get("published"),
        }
        if number:
            cleaned["document_number"] = number
        return cleaned

    @staticmethod
    def _clean_race_attribute(race: dict | None) -> dict | None:
        """Return compact race context for frontend cards."""
        if not isinstance(race, dict) or not race:
            return None
        return {
            "season": race.get("season"),
            "round": race.get("round"),
            "race_name": race.get("race_name"),
            "race_date": race.get("race_date"),
            "race_time": race.get("race_time"),
            "circuit_name": race.get("circuit_name"),
            "locality": race.get("locality"),
            "country": race.get("country"),
        }

    @classmethod
    def _build_attributes(
        cls, latest: dict | None, documents: list[dict] | None, race: dict | None
    ) -> dict:
        """Build frontend-friendly attributes while keeping latest fields flat."""
        cleaned_documents = [
            cleaned
            for doc in documents or []
            if (cleaned := cls._clean_document_attribute(doc))
        ]
        latest_cleaned = cls._clean_document_attribute(latest)
        return {
            "name": latest_cleaned.get("name"),
            "url": latest_cleaned.get("url"),
            "published": latest_cleaned.get("published"),
            "documents": cleaned_documents,
            "race": cls._clean_race_attribute(race),
        }


class DriverPointsProgressionModel(PointsProjection):
    """Projection extracted from F1DriverPointsProgressionSensor; shared with its entity adapter."""

    def _get_full_schedule(self) -> list:
        """Return full season schedule (all planned rounds) from race_coordinator if available."""
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            race_coord = reg.get("race_coordinator")
            if race_coord and isinstance(race_coord.data, dict):
                return (
                    race_coord.data.get("MRData", {})
                    .get("RaceTable", {})
                    .get("Races", [])
                )
        except Exception:
            return []
        return []

    def _get_driver_standings(self) -> tuple[dict, int | None]:
        """Return (points_by_code, standings_round) from driver standings coordinator."""
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            coord = reg.get("driver_coordinator")
            points_map: dict[str, float] = {}
            round_num: int | None = None
            if coord and isinstance(coord.data, dict):
                lists = (
                    coord.data.get("MRData", {})
                    .get("StandingsTable", {})
                    .get("StandingsLists", [])
                )
                if lists:
                    try:
                        round_num = (
                            int(str(lists[0].get("round") or 0))
                            if str(lists[0].get("round") or "").isdigit()
                            else None
                        )
                    except Exception:
                        round_num = None
                    for item in lists[0].get("DriverStandings", []) or []:
                        drv = item.get("Driver", {}) or {}
                        code = drv.get("code") or drv.get("driverId")
                        if not code:
                            continue
                        try:
                            points_map[code] = float(str(item.get("points") or 0))
                        except Exception:
                            points_map[code] = 0.0
            return (points_map, round_num)
        except Exception:
            return ({}, None)

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        season = None
        rounds_meta = []
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        name_map: dict[str, dict] = {}
        round_numbers: list[int] = []
        for race in races:
            season = season or race.get("season")
            rnd = (
                int(str(race.get("round") or 0))
                if str(race.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append(
                {
                    "round": rnd,
                    "race_name": race.get("raceName"),
                    "date": _combine_date_time(race.get("date"), race.get("time")),
                }
            )
            results = race.get("Results", []) or []
            winner_code = None
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                if res.get("position") == "1" or res.get("positionText") == "1":
                    winner_code = code
                name_map.setdefault(
                    code,
                    {
                        "code": drv.get("code") or None,
                        "driverId": drv.get("driverId"),
                        "name": f"{drv.get('givenName', '')} {drv.get('familyName', '')}".strip()
                        or drv.get("familyName"),
                    },
                )
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = _to_float_value(res.get("points"))
                per_round_points.setdefault(code, [])
                wins_per_round.setdefault(code, [])
                per_round_points[code].append(pts)
                wins_per_round[code].append(1 if code == winner_code else 0)
            max_len = len(round_numbers)
            for code in list(per_round_points.keys()):
                while len(per_round_points[code]) < max_len:
                    per_round_points[code].append(0.0)
                while len(wins_per_round[code]) < max_len:
                    wins_per_round[code].append(0)
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = (
                int(str(sp.get("round") or 0))
                if str(sp.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            if rnd not in round_index:
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append(
                    {
                        "round": rnd,
                        "race_name": sp.get("raceName"),
                        "date": _combine_date_time(sp.get("date"), sp.get("time")),
                    }
                )
                for code in list(per_round_points.keys()):
                    per_round_points[code].append(0.0)
                for code in list(wins_per_round.keys()):
                    wins_per_round[code].append(None)
            idx = round_index[rnd]
            results = sp.get("SprintResults") or sp.get("Results") or []
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = _to_float_value(res.get("points"))
                per_round_points.setdefault(code, [0.0] * len(round_numbers))
                wins_per_round.setdefault(code, [None] * len(round_numbers))
                with suppress(Exception):
                    per_round_points[code][idx] += pts
        with suppress(Exception):
            standings_map, standings_round = self._get_driver_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                if standings_round and (
                    max_round is None or standings_round > max_round
                ):
                    round_numbers.append(standings_round)
                    rounds_meta.append(
                        {"round": standings_round, "race_name": None, "date": None}
                    )
                    for code in list(per_round_points.keys()):
                        per_round_points[code].append(0.0)
                    for code in list(wins_per_round.keys()):
                        wins_per_round[code].append(None)
                for code, total_pts in standings_map.items():
                    pts_list = per_round_points.get(code)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        with suppress(Exception):
                            computed_total += float(v or 0.0)
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        per_round_points[code][-1] = (
                            per_round_points[code][-1] or 0.0
                        ) + delta
        drivers_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for code, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                if p is None:
                    cum.append(None)
                else:
                    total += float(p or 0.0)
                    cum.append(total)
            wins = wins_per_round.get(code, [0] * len(pts_list))
            safe_wins = [
                int(w) if isinstance(w, int) else 1 if w is True else 0 for w in wins
            ]
            info = name_map.get(code, {})
            drivers_attr[code] = {
                "identity": {
                    "code": info.get("code") or (code if len(code) <= 3 else None),
                    "driverId": info.get("driverId"),
                    "name": info.get("name"),
                },
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append(
                {
                    "key": info.get("code") or code,
                    "name": info.get("name") or code,
                    "data": cum,
                }
            )
        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "drivers": drivers_attr,
            "series": series,
        }


class ConstructorPointsProgressionModel(PointsProjection):
    """Projection extracted from F1ConstructorPointsProgressionSensor; shared with its entity adapter."""

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        season = None
        rounds_meta = []
        round_numbers: list[int] = []
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        team_info: dict[str, dict] = {}
        for race in races:
            season = season or race.get("season")
            rnd = (
                int(str(race.get("round") or 0))
                if str(race.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append(
                {
                    "round": rnd,
                    "race_name": race.get("raceName"),
                    "date": _combine_date_time(race.get("date"), race.get("time")),
                }
            )
            results = race.get("Results", []) or []
            winning_constructor = None
            for res in results:
                if str(res.get("position") or res.get("positionText")) == "1":
                    c = (res.get("Constructor") or {}).get("constructorId")
                    winning_constructor = c
                    break
            per_round_sum: dict[str, float] = {}
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(
                    cid,
                    {
                        "constructorId": cons.get("constructorId"),
                        "name": cons.get("name"),
                    },
                )
                per_round_sum[cid] = per_round_sum.get(cid, 0.0) + _to_float_value(
                    res.get("points")
                )
            for cid, pts in per_round_sum.items():
                per_round_points.setdefault(cid, [])
                wins_per_round.setdefault(cid, [])
                per_round_points[cid].append(pts)
                wins_per_round[cid].append(1 if cid == winning_constructor else 0)
            max_len = len(round_numbers)
            for cid in list(per_round_points.keys()):
                while len(per_round_points[cid]) < max_len:
                    per_round_points[cid].append(0.0)
                while len(wins_per_round[cid]) < max_len:
                    wins_per_round[cid].append(0)
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = (
                int(str(sp.get("round") or 0))
                if str(sp.get("round") or "").isdigit()
                else None
            )
            if rnd is None:
                continue
            if rnd not in round_index:
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append(
                    {
                        "round": rnd,
                        "race_name": sp.get("raceName"),
                        "date": _combine_date_time(sp.get("date"), sp.get("time")),
                    }
                )
                for cid in list(per_round_points.keys()):
                    per_round_points[cid].append(0.0)
                for cid in list(wins_per_round.keys()):
                    wins_per_round[cid].append(None)
            idx = round_index[rnd]
            results = sp.get("SprintResults") or sp.get("Results") or []
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(
                    cid,
                    {
                        "constructorId": cons.get("constructorId"),
                        "name": cons.get("name"),
                    },
                )
                per_round_points.setdefault(cid, [0.0] * len(round_numbers))
                wins_per_round.setdefault(cid, [None] * len(round_numbers))
                with suppress(Exception):
                    per_round_points[cid][idx] += _to_float_value(res.get("points"))
        with suppress(Exception):
            standings_map, standings_round = self._get_constructor_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                if standings_round and (
                    max_round is None or standings_round > max_round
                ):
                    round_numbers.append(standings_round)
                    rounds_meta.append(
                        {"round": standings_round, "race_name": None, "date": None}
                    )
                    for cid in list(per_round_points.keys()):
                        per_round_points[cid].append(0.0)
                    for cid in list(wins_per_round.keys()):
                        wins_per_round[cid].append(None)
                for cid, total_pts in standings_map.items():
                    pts_list = per_round_points.get(cid)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        with suppress(Exception):
                            computed_total += float(v or 0.0)
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        per_round_points[cid][-1] = (
                            per_round_points[cid][-1] or 0.0
                        ) + delta
        teams_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for cid, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                total += float(p or 0.0)
                cum.append(total)
            wins = wins_per_round.get(cid, [0] * len(pts_list))
            safe_wins = [
                int(w) if isinstance(w, int) else 1 if w is True else 0 for w in wins
            ]
            info = team_info.get(cid, {"name": cid})
            teams_attr[cid] = {
                "identity": {
                    "constructorId": info.get("constructorId"),
                    "name": info.get("name"),
                },
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append(
                {
                    "key": info.get("constructorId") or cid,
                    "name": info.get("name") or cid,
                    "data": cum,
                }
            )
        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "constructors": teams_attr,
            "series": series,
        }

    def _get_constructor_standings(self) -> tuple[dict, int | None]:
        """Return (points_by_constructorId, standings_round) from constructor standings coordinator."""
        try:
            reg = entry_runtime_registry(self.hass, self._entry_id)
            coord = reg.get("constructor_coordinator")
            points_map: dict[str, float] = {}
            round_num: int | None = None
            if coord and isinstance(coord.data, dict):
                lists = (
                    coord.data.get("MRData", {})
                    .get("StandingsTable", {})
                    .get("StandingsLists", [])
                )
                if lists:
                    try:
                        round_num = (
                            int(str(lists[0].get("round") or 0))
                            if str(lists[0].get("round") or "").isdigit()
                            else None
                        )
                    except Exception:
                        round_num = None
                    for item in lists[0].get("ConstructorStandings", []) or []:
                        cons = item.get("Constructor", {}) or {}
                        cid = cons.get("constructorId") or cons.get("name")
                        if not cid:
                            continue
                        try:
                            points_map[cid] = float(str(item.get("points") or 0))
                        except Exception:
                            points_map[cid] = 0.0
            return (points_map, round_num)
        except Exception:
            return ({}, None)
