import datetime
import asyncio
import re
from zoneinfo import ZoneInfo

import async_timeout
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import F1AuxEntity, F1BaseEntity
from .const import (
    CONF_OPERATION_MODE,
    DEFAULT_OPERATION_MODE,
    LATEST_TRACK_STATUS,
    OPERATION_MODE_DEVELOPMENT,
)
from .helpers import get_timezone, normalize_track_status
from .live_window import STATIC_BASE
from logging import getLogger
from homeassistant.util import dt as dt_util

RACE_SWITCH_GRACE = datetime.timedelta(hours=3)

SYMBOL_CODE_TO_MDI = {
    "clearsky_day": "mdi:weather-sunny",
    "clearsky_night": "mdi:weather-night",
    "fair_day": "mdi:weather-partly-cloudy",
    "fair_night": "mdi:weather-night-partly-cloudy",
    "partlycloudy_day": "mdi:weather-partly-cloudy",
    "partlycloudy_night": "mdi:weather-night-partly-cloudy",
    "cloudy": "mdi:weather-cloudy",
    "fog": "mdi:weather-fog",
    "rainshowers_day": "mdi:weather-rainy",
    "rainshowers_night": "mdi:weather-rainy",
    "rainshowersandthunder_day": "mdi:weather-lightning-rainy",
    "rainshowersandthunder_night": "mdi:weather-lightning-rainy",
    "heavyrainshowers_day": "mdi:weather-pouring",
    "heavyrainshowers_night": "mdi:weather-pouring",
    "sleetshowers_day": "mdi:weather-snowy-rainy",
    "sleetshowers_night": "mdi:weather-snowy-rainy",
    "snowshowers_day": "mdi:weather-snowy",
    "snowshowers_night": "mdi:weather-snowy",
    "rain": "mdi:weather-pouring",
    "heavyrain": "mdi:weather-pouring",
    "heavyrainandthunder": "mdi:weather-lightning-rainy",
    "sleet": "mdi:weather-snowy-rainy",
    "snow": "mdi:weather-snowy",
    "snowandthunder": "mdi:weather-snowy-heavy",
    "rainandthunder": "mdi:weather-lightning-rainy",
    "sleetandthunder": "mdi:weather-lightning-rainy",
    "lightrainshowers_day": "mdi:weather-rainy",
    "lightrainshowers_night": "mdi:weather-rainy",
    "lightrainshowersandthunder_day": "mdi:weather-lightning-rainy",
    "lightrainshowersandthunder_night": "mdi:weather-lightning-rainy",
    "lightsleetshowers_day": "mdi:weather-snowy-rainy",
    "lightsleetshowers_night": "mdi:weather-snowy-rainy",
    "lightsnowshowers_day": "mdi:weather-snowy",
    "lightsnowshowers_night": "mdi:weather-snowy",
    "lightsnowshowersandthunder_day": "mdi:weather-lightning-snowy",
    "lightsnowshowersandthunder_night": "mdi:weather-lightning-snowy",
    "lightssleetshowersandthunder_day": "mdi:weather-lightning-snowy-rainy",
    "lightssleetshowersandthunder_night": "mdi:weather-lightning-snowy-rainy",
    "lightssnowshowersandthunder_day": "mdi:weather-lightning-snowy",
    "lightssnowshowersandthunder_night": "mdi:weather-lightning-snowy",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Create sensors when integration is added."""
    data = hass.data[DOMAIN][entry.entry_id]
    base = entry.data.get("sensor_name", "F1")
    # Normalize legacy/stale sensor keys
    allowed = {
        "next_race",
        "current_season",
        "driver_standings",
        "constructor_standings",
        "weather",
        "track_weather",
        "race_lap_count",
        "driver_list",
        "current_tyres",
        # TEMP_DISABLED: race_order
        # TEMP_DISABLED: driver_favorites
        "last_race_results",
        "season_results",
        "sprint_results",
        "driver_points_progression",
        "constructor_points_progression",
        "race_week",
        "track_status",
        "session_status",
        "current_session",
        "safety_car",
        "fia_documents",
        "race_control",
        "top_three",
        "team_radio",
        "pitstops",
        "championship_prediction",
        "live_timing_diagnostics",
    }
    raw_enabled = entry.data.get("enabled_sensors", [])
    normalized = []
    seen = set()
    for key in raw_enabled:
        if key == "next_session":
            key = "next_race"
        if key in allowed and key not in seen:
            normalized.append(key)
            seen.add(key)
    enabled = normalized

    mapping = {
        "next_race": (F1NextRaceSensor, data["race_coordinator"]),
        "current_season": (F1CurrentSeasonSensor, data["race_coordinator"]),
        "driver_standings": (F1DriverStandingsSensor, data["driver_coordinator"]),
        "constructor_standings": (
            F1ConstructorStandingsSensor,
            data["constructor_coordinator"],
        ),
        "weather": (F1WeatherSensor, data["race_coordinator"]),
        "track_weather": (F1TrackWeatherSensor, data.get("weather_data_coordinator")),
        "race_lap_count": (F1RaceLapCountSensor, data.get("lap_count_coordinator")),
        "last_race_results": (F1LastRaceSensor, data["last_race_coordinator"]),
        "season_results": (F1SeasonResultsSensor, data["season_results_coordinator"]),
        "sprint_results": (F1SprintResultsSensor, data["sprint_results_coordinator"]),
        "driver_points_progression": (F1DriverPointsProgressionSensor, data["season_results_coordinator"]),
        "constructor_points_progression": (F1ConstructorPointsProgressionSensor, data["season_results_coordinator"]),
        "track_status": (F1TrackStatusSensor, data.get("track_status_coordinator")),
        "session_status": (F1SessionStatusSensor, data.get("session_status_coordinator")),
        "current_session": (F1CurrentSessionSensor, data.get("session_info_coordinator")),
        "driver_list": (F1DriverListSensor, data.get("drivers_coordinator")),
        "current_tyres": (F1CurrentTyresSensor, data.get("drivers_coordinator")),
        "fia_documents": (F1FiaDocumentsSensor, data.get("fia_documents_coordinator")),
        "race_control": (F1RaceControlSensor, data.get("race_control_coordinator")),
        "top_three": (None, data.get("top_three_coordinator")),
        "team_radio": (F1TeamRadioSensor, data.get("team_radio_coordinator")),
        "pitstops": (F1PitStopsSensor, data.get("pitstop_coordinator")),
        "championship_prediction": (None, data.get("championship_prediction_coordinator")),
        "live_timing_diagnostics": (None, None),
    }

    sensors = []
    for key in enabled:
        cls, coord = mapping.get(key, (None, None))
        if key == "top_three":
            # Expandera till tre separata sensorer: P1, P2, P3
            if not coord:
                continue
            for pos in range(3):
                sensors.append(
                    F1TopThreePositionSensor(
                        coord,
                        f"{base}_top_three_p{pos + 1}",
                        f"{entry.entry_id}_top_three_p{pos + 1}",
                        entry.entry_id,
                        base,
                        pos,
                    )
                )
        elif key == "championship_prediction":
            if not coord:
                continue
            sensors.append(
                F1ChampionshipPredictionDriversSensor(
                    coord,
                    f"{base}_championship_prediction_drivers",
                    f"{entry.entry_id}_championship_prediction_drivers",
                    entry.entry_id,
                    base,
                )
            )
            sensors.append(
                F1ChampionshipPredictionTeamsSensor(
                    coord,
                    f"{base}_championship_prediction_teams",
                    f"{entry.entry_id}_championship_prediction_teams",
                    entry.entry_id,
                    base,
                )
            )
        elif key == "live_timing_diagnostics":
            sensors.append(
                F1LiveTimingModeSensor(
                    hass,
                    entry.entry_id,
                    base,
                )
            )
        elif cls and coord:
            sensors.append(
                cls(
                    coord,
                    f"{base}_{key}",
                    f"{entry.entry_id}_{key}",
                    entry.entry_id,
                    base,
                )
            )
    async_add_entities(sensors, True)


class F1LiveTimingModeSensor(F1AuxEntity, SensorEntity):
    """Diagnostic mode sensor for the live timing transport (idle/live/replay)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["idle", "live", "replay"]

    def __init__(self, hass: HomeAssistant, entry_id: str, device_name: str) -> None:
        super().__init__(
            name=f"{device_name}_live_timing_mode",
            unique_id=f"{entry_id}_live_timing_mode",
            entry_id=entry_id,
            device_name=device_name,
        )
        self.hass = hass
        self._entry_id = entry_id
        self._unsub_live_state = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        live_state = reg.get("live_state")
        if live_state is not None and hasattr(live_state, "add_listener"):
            try:
                self._unsub_live_state = live_state.add_listener(
                    lambda *_: self._safe_write_ha_state()
                )
                self.async_on_remove(self._unsub_live_state)
            except Exception:
                self._unsub_live_state = None

        # Periodic update for age/window attributes
        try:
            unsub = async_track_time_interval(
                self.hass,
                lambda *_: self._safe_write_ha_state(),
                datetime.timedelta(seconds=10),
            )
            self.async_on_remove(unsub)
        except Exception:
            pass

    def _compute(self) -> tuple[str, dict]:
        reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}) or {}
        operation_mode = reg.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE)
        live_state = reg.get("live_state")
        live_bus = reg.get("live_bus")
        live_supervisor = reg.get("live_supervisor")

        is_live_window = bool(getattr(live_state, "is_live", False)) if live_state is not None else False
        reason = getattr(live_state, "reason", None) if live_state is not None else None

        if operation_mode == OPERATION_MODE_DEVELOPMENT:
            mode = "replay"
        else:
            mode = "live" if is_live_window else "idle"

        window = None
        try:
            cw = getattr(live_supervisor, "current_window", None) if live_supervisor is not None else None
            if cw is not None and hasattr(cw, "label"):
                window = cw.label
        except Exception:
            window = None

        hb_age = None
        activity_age = None
        try:
            if live_bus is not None:
                hb_age = live_bus.last_heartbeat_age()
                activity_age = live_bus.last_stream_activity_age()
        except Exception:
            hb_age = activity_age = None

        attrs = {
            "reason": reason,
            "window": window,
            "heartbeat_age_s": (round(hb_age, 1) if hb_age is not None else None),
            "activity_age_s": (round(activity_age, 1) if activity_age is not None else None),
        }
        return mode, attrs

    @property
    def native_value(self):
        mode, _ = self._compute()
        return mode

    @property
    def extra_state_attributes(self):
        _, attrs = self._compute()
        return attrs


class F1NextRaceSensor(F1BaseEntity, SensorEntity):
    """Sensor that returns date/time (ISO8601) for the next race in 'state'."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = datetime.datetime.now(datetime.timezone.utc)

        for race in races:
            date = race.get("date")
            time = race.get("time") or "00:00:00Z"
            dt_str = f"{date}T{time}".replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            # Consider a race as "current" until a grace period after the scheduled start.
            # This prevents `sensor.f1_next_race` from flipping to the next weekend
            # immediately when lights go out.
            end_dt = dt + RACE_SWITCH_GRACE
            if end_dt > now:
                return race
        return None

    def combine_date_time(self, date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone(datetime.timezone.utc)
            return dt.isoformat()
        except ValueError:
            return None

    def _timezone_from_location(self, lat, lon):
        return get_timezone(lat, lon)

    def _to_local(self, iso_ts, timezone):
        if not iso_ts or not timezone:
            return None
        try:
            dt = datetime.datetime.fromisoformat(iso_ts)
            return dt.astimezone(ZoneInfo(timezone)).isoformat()
        except Exception:
            return None

    def _to_home(self, iso_ts):
        if not iso_ts:
            return None
        try:
            dt = datetime.datetime.fromisoformat(iso_ts)
        except Exception:
            return None
        tzname = getattr(self.hass.config, "time_zone", None)
        if not tzname:
            return dt.isoformat()
        tzinfo = dt_util.get_time_zone(tzname)
        if tzinfo is None:
            return dt.isoformat()
        try:
            return dt.astimezone(tzinfo).isoformat()
        except Exception:
            return dt.isoformat()

    @property
    def state(self):
        next_race = self._get_next_race()
        if not next_race:
            return None
        return self.combine_date_time(next_race.get("date"), next_race.get("time"))

    @property
    def extra_state_attributes(self):
        race = self._get_next_race()
        if not race:
            return {}

        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        timezone = self._timezone_from_location(loc.get("lat"), loc.get("long"))

        first_practice = race.get("FirstPractice", {})
        second_practice = race.get("SecondPractice", {})
        third_practice = race.get("ThirdPractice", {})
        qualifying = race.get("Qualifying", {})
        sprint_qualifying = race.get("SprintQualifying", {})
        sprint = race.get("Sprint", {})

        race_start = self.combine_date_time(race.get("date"), race.get("time"))
        first_start = self.combine_date_time(
            first_practice.get("date"), first_practice.get("time")
        )
        second_start = self.combine_date_time(
            second_practice.get("date"), second_practice.get("time")
        )
        third_start = self.combine_date_time(
            third_practice.get("date"), third_practice.get("time")
        )
        qual_start = self.combine_date_time(
            qualifying.get("date"), qualifying.get("time")
        )
        sprint_quali_start = self.combine_date_time(
            sprint_qualifying.get("date"), sprint_qualifying.get("time")
        )
        sprint_start = self.combine_date_time(sprint.get("date"), sprint.get("time"))

        attrs = {
            "season": race.get("season"),
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
        }

        def _populate(label, iso_value):
            attrs[f"{label}_utc"] = iso_value
            attrs[label] = self._to_home(iso_value)
            attrs[f"{label}_local"] = self._to_local(iso_value, timezone)

        _populate("race_start", race_start)
        _populate("first_practice_start", first_start)
        _populate("second_practice_start", second_start)
        _populate("third_practice_start", third_start)
        _populate("qualifying_start", qual_start)
        _populate("sprint_qualifying_start", sprint_quali_start)
        _populate("sprint_start", sprint_start)

        return attrs


class F1CurrentSeasonSensor(F1BaseEntity, SensorEntity):
    """Sensor showing number of races this season."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-month"

    @property
    def state(self):
        data = self.coordinator.data or {}
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        return len(races)

    @property
    def extra_state_attributes(self):
        table = (self.coordinator.data or {}).get("MRData", {}).get("RaceTable", {})
        return {"season": table.get("season"), "races": table.get("Races", [])}


class F1DriverStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for driver standings."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple-check"

    @property
    def state(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        return len(lists[0].get("DriverStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not lists:
            return {}
        first = lists[0]
        return {
            "season": first.get("season"),
            "round": first.get("round"),
            "driver_standings": first.get("DriverStandings", []),
        }


class F1ConstructorStandingsSensor(F1BaseEntity, SensorEntity):
    """Sensor for constructor standings."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:factory"

    @property
    def state(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        return len(lists[0].get("ConstructorStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        lists = (
            (self.coordinator.data or {})
            .get("MRData", {})
            .get("StandingsTable", {})
            .get("StandingsLists", [])
        )
        if not lists:
            return {}
        first = lists[0]
        return {
            "season": first.get("season"),
            "round": first.get("round"),
            "constructor_standings": first.get("ConstructorStandings", []),
        }


class F1WeatherSensor(F1BaseEntity, SensorEntity):
    """Sensor for current and race-start weather."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:weather-partly-cloudy"
        self._current = {}
        self._race = {}
        self._circuit = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(
            lambda: self.hass.async_create_task(self._update_weather())
        )
        self.async_on_remove(removal)
        await self._update_weather()

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        now = datetime.datetime.now(datetime.timezone.utc)

        for race in races:
            date = race.get("date")
            time = race.get("time") or "00:00:00Z"
            dt_str = f"{date}T{time}".replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                continue
            # Keep using the active race (for weather etc.) until a grace period
            # after the scheduled start. This matches `sensor.f1_next_race` and
            # defaults to 3 hours via `RACE_SWITCH_GRACE`.
            end_dt = dt + RACE_SWITCH_GRACE
            if end_dt > now:
                return race
        return None

    def _combine_date_time(self, date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except ValueError:
            return None

    async def _update_weather(self):
        race = self._get_next_race()
        # Store which circuit this weather is for, so the UI can show context even
        # when only temperature is used as the sensor state.
        if race:
            circuit = race.get("Circuit", {}) or {}
            loc = circuit.get("Location", {}) or {}
            self._circuit = {
                "season": race.get("season"),
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
            }
        else:
            self._circuit = {}
        loc = race.get("Circuit", {}).get("Location", {}) if race else {}
        lat, lon = loc.get("lat"), loc.get("long")
        if lat is None or lon is None:
            return
        session = async_get_clientsession(self.hass)
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        headers = {"User-Agent": "homeassistant-f1_sensor"}
        try:
            async with async_timeout.timeout(10):
                resp = await session.get(url, headers=headers)
                data = await resp.json()
        except Exception:
            return
        times = data.get("properties", {}).get("timeseries", [])
        if not times:
            return
        curr = times[0].get("data", {}).get("instant", {}).get("details", {})
        # Derive current precipitation from forecast blocks (prefer max of 1h/6h/12h)
        data0 = times[0].get("data", {})
        block1 = data0.get("next_1_hours") or {}
        block6 = data0.get("next_6_hours") or {}
        block12 = data0.get("next_12_hours") or {}

        def _precip_triplet(block: dict):
            details = (block or {}).get("details", {}) or {}
            amt = details.get("precipitation_amount")
            if amt is None:
                amt = details.get("precipitation_amount_min")
            if amt is None:
                amt = details.get("precipitation_amount_max")
            if amt is None:
                amt = 0
            return amt, details.get("precipitation_amount_min"), details.get("precipitation_amount_max")

        def _precip_probability(block: dict):
            details = (block or {}).get("details", {}) or {}
            return details.get("probability_of_precipitation")

        p1, p1min, p1max = _precip_triplet(block1)
        p6, p6min, p6max = _precip_triplet(block6)
        p12, p12min, p12max = _precip_triplet(block12)
        candidates = [
            (p1, p1min, p1max, block1),
            (p6, p6min, p6max, block6),
            (p12, p12min, p12max, block12),
        ]
        sel_amt, sel_min, sel_max, sel_block = max(candidates, key=lambda t: t[0])
        curr_with_precip = dict(curr)
        curr_with_precip["precipitation_amount"] = sel_amt
        curr_with_precip["probability_of_precipitation"] = _precip_probability(sel_block)
        # Also expose min/max precipitation; fallback to selected amount when missing
        _cur_min = sel_min
        _cur_max = sel_max
        curr_with_precip["precipitation_amount_min"] = _cur_min if _cur_min is not None else sel_amt
        curr_with_precip["precipitation_amount_max"] = _cur_max if _cur_max is not None else sel_amt
        self._current = self._extract(curr_with_precip)
        current_symbol = (sel_block or {}).get("summary", {}).get("symbol_code")
        current_icon = SYMBOL_CODE_TO_MDI.get(current_symbol, self._attr_icon)
        self._attr_icon = current_icon
        start_iso = (
            self._combine_date_time(race.get("date"), race.get("time"))
            if race
            else None
        )
        self._race = {k: None for k in self._current}
        if start_iso:
            start_dt = datetime.datetime.fromisoformat(start_iso)
            same_day = [
                t
                for t in times
                if datetime.datetime.fromisoformat(t["time"]).date() == start_dt.date()
            ]
            if same_day:
                closest = min(
                    same_day,
                    key=lambda t: abs(
                        datetime.datetime.fromisoformat(t["time"]) - start_dt
                    ),
                )
                data_entry = closest.get("data", {})
                instant_details = data_entry.get("instant", {}).get("details", {})
                # Choose race precipitation as max of 1h/6h/12h around start time
                r1 = data_entry.get("next_1_hours") or {}
                r6 = data_entry.get("next_6_hours") or {}
                r12 = data_entry.get("next_12_hours") or {}
                rp1, rp1min, rp1max = _precip_triplet(r1)
                rp6, rp6min, rp6max = _precip_triplet(r6)
                rp12, rp12min, rp12max = _precip_triplet(r12)
                rcandidates = [
                    (rp1, rp1min, rp1max, r1),
                    (rp6, rp6min, rp6max, r6),
                    (rp12, rp12min, rp12max, r12),
                ]
                r_sel_amt, r_sel_min, r_sel_max, r_sel_block = max(rcandidates, key=lambda t: t[0])
                rd = dict(instant_details)
                rd["precipitation_amount"] = r_sel_amt
                rd["probability_of_precipitation"] = _precip_probability(r_sel_block)
                # Also expose min/max precipitation at race time; fallback to selected amount
                rd["precipitation_amount_min"] = r_sel_min if r_sel_min is not None else r_sel_amt
                rd["precipitation_amount_max"] = r_sel_max if r_sel_max is not None else r_sel_amt
                self._race = self._extract(rd)
                forecast_block = r_sel_block or {}
                race_symbol = forecast_block.get("summary", {}).get("symbol_code")
                race_icon = SYMBOL_CODE_TO_MDI.get(race_symbol, self._attr_icon)
                self._race["weather_icon"] = race_icon
        self.async_write_ha_state()

    def _extract(self, d):
        wd = d.get("wind_from_direction")
        return {
            "temperature": d.get("air_temperature"),
            "temperature_unit": "celsius",
            "humidity": d.get("relative_humidity"),
            "humidity_unit": "%",
            "cloud_cover": d.get("cloud_area_fraction"),
            "cloud_cover_unit": "%",
            "precipitation": d.get("precipitation_amount", 0),
            "precipitation_amount_min": d.get("precipitation_amount_min"),
            "precipitation_amount_max": d.get("precipitation_amount_max"),
            "precipitation_probability": d.get("probability_of_precipitation"),
            "precipitation_probability_unit": "%",
            "precipitation_unit": "mm",
            "wind_speed": d.get("wind_speed"),
            "wind_speed_unit": "m/s",
            "wind_direction": self._abbr(wd),
            "wind_from_direction_degrees": wd,
            "wind_from_direction_unit": "degrees",
        }

    def _abbr(self, deg):
        if deg is None:
            return None
        dirs = [
            (i * 22.5, d)
            for i, d in enumerate(
                [
                    "N",
                    "NNE",
                    "NE",
                    "ENE",
                    "E",
                    "ESE",
                    "SE",
                    "SSE",
                    "S",
                    "SSW",
                    "SW",
                    "WSW",
                    "W",
                    "WNW",
                    "NW",
                    "NNW",
                    "N",
                ]
            )
        ]
        return min(dirs, key=lambda x: abs(deg - x[0]))[1]

    @property
    def state(self):
        return self._current.get("temperature")

    @property
    def extra_state_attributes(self):
        attrs = dict(self._circuit or {})
        attrs.update({f"current_{k}": v for k, v in self._current.items()})
        attrs.update({f"race_{k}": v for k, v in self._race.items()})
        return attrs


class F1LastRaceSensor(F1BaseEntity, SensorEntity):
    """Sensor for results of the latest race."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:trophy"

    def combine_date_time(self, date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(dt_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone(datetime.timezone.utc)
            return dt.isoformat()
        except ValueError:
            return None

    def _timezone_from_location(self, lat, lon):
        return get_timezone(lat, lon)

    def _to_local(self, iso_ts, timezone):
        if not iso_ts or not timezone:
            return None
        try:
            dt = datetime.datetime.fromisoformat(iso_ts)
            return dt.astimezone(ZoneInfo(timezone)).isoformat()
        except Exception:
            return None

    def _to_home(self, iso_ts):
        if not iso_ts:
            return None
        try:
            dt = datetime.datetime.fromisoformat(iso_ts)
        except Exception:
            return None
        tzname = getattr(self.hass.config, "time_zone", None)
        if not tzname:
            return dt.isoformat()
        tzinfo = dt_util.get_time_zone(tzname)
        if tzinfo is None:
            return dt.isoformat()
        try:
            return dt.astimezone(tzinfo).isoformat()
        except Exception:
            return dt.isoformat()

    @property
    def state(self):
        races = (
            self.coordinator.data.get("MRData", {})
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
            self.coordinator.data.get("MRData", {})
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
        timezone = self._timezone_from_location(loc.get("lat"), loc.get("long"))
        race_start = self.combine_date_time(race.get("date"), race.get("time"))
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
        attrs["race_start"] = self._to_home(race_start)
        attrs["race_start_local"] = self._to_local(race_start, timezone)
        return attrs


class F1SeasonResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor for entire season's results."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:podium"

    @property
    def state(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        return len(races)

    @property
    def extra_state_attributes(self):
        races = (
            self.coordinator.data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )

        def _clean_result(r):
            return {
                "number": r.get("number"),
                "position": r.get("position"),
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


class F1SprintResultsSensor(F1BaseEntity, SensorEntity):
    """Sensor exposing sprint results across the current season."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-variant"

    def _get_races(self):
        data = self.coordinator.data or {}
        races = (
            data.get("MRData", {})
            .get("RaceTable", {})
            .get("Races", [])
        )
        return races or []

    @staticmethod
    def _clean_result(result: dict) -> dict:
        driver = result.get("Driver", {}) or {}
        constructor = result.get("Constructor", {}) or {}
        return {
            "number": result.get("number"),
            "position": result.get("position"),
            "points": result.get("points"),
            "status": result.get("status"),
            "driver": {
                "permanentNumber": driver.get("permanentNumber"),
                "code": driver.get("code"),
                "givenName": driver.get("givenName"),
                "familyName": driver.get("familyName"),
            },
            "constructor": {
                "name": constructor.get("name"),
            },
        }

    @property
    def state(self):
        races = self._get_races()
        if not races:
            return 0
        # Only count sprint weekends that actually include sprint results
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


class F1FiaDocumentsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor that tracks FIA decision documents per race weekend."""

    _DOC1_RESET_PATTERN = re.compile(
        r"\bdoc(?:ument)?(?:\s+(?:no\.?|number))?\s*0*1\b",
        re.IGNORECASE,
    )
    _DOC_NUMBER_RE = re.compile(
        r"\bdoc(?:ument)?(?:\s+(?:no\.?|number))?\s*0*(\d+)\b",
        re.IGNORECASE,
    )

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:file-document-alert"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"documents": []}
        self._documents: list[dict] = []
        self._seen_urls: set[str] = set()
        self._event_key: str | None = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._restore_last_state()
        self._update_from_coordinator(force=True)
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    async def _restore_last_state(self) -> None:
        last = await self.async_get_last_state()
        if not last or last.state in (None, "unknown", "unavailable"):
            return
        attrs = dict(getattr(last, "attributes", {}) or {})
        docs = attrs.get("documents")
        if isinstance(docs, list):
            cleaned = [doc for doc in docs if isinstance(doc, dict)]
            self._documents = cleaned
            self._seen_urls = {
                str(doc.get("url")).strip()
                for doc in cleaned
                if isinstance(doc.get("url"), str)
            }
        else:
            # Newer format: restore single latest document from flat attributes if present
            name = attrs.get("name")
            url = attrs.get("url")
            published = attrs.get("published")
            if any((name, url, published)):
                self._documents = [
                    {
                        "name": name,
                        "url": url,
                        "published": published,
                    }
                ]
        self._sort_documents()

        latest = self._select_latest_document(self._documents) if self._documents else None
        self._attr_native_value = self._extract_doc_number(latest.get("name")) if latest else 0
        self._attr_extra_state_attributes = self._build_latest_attributes(latest)

    def _handle_coordinator_update(self) -> None:
        changed = self._update_from_coordinator()
        if changed:
            from logging import getLogger

            try:
                getLogger(__name__).debug(
                    "FIA documents updated -> event=%s count=%s",
                    self._event_key,
                    self._attr_native_value,
                )
            except Exception:
                pass
            self._safe_write_ha_state()

    def _update_from_coordinator(self, force: bool = False) -> bool:
        data = self.coordinator.data or {}
        updated = False
        event_key = data.get("event_key")
        race_info = data.get("race") if isinstance(data.get("race"), dict) else {}
        documents = data.get("documents") if isinstance(data.get("documents"), list) else []

        if isinstance(event_key, str) and event_key and event_key != self._event_key:
            self._event_key = event_key
            self._documents = []
            self._seen_urls = set()
            updated = True

        # Process documents from oldest to newest so that "Doc 1" for the
        # current event is handled before later documents. This ensures that
        # the final reset triggered by a new Document 1 corresponds to the
        # latest race weekend instead of wiping out its newer docs.
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

        # Keep bounded attribute size
        if len(self._documents) > 100:
            excess = len(self._documents) - 100
            for _ in range(excess):
                removed = self._documents.pop(0)
                url = str(removed.get("url") or "").strip()
                if url in self._seen_urls:
                    self._seen_urls.remove(url)
            updated = True

        self._sort_documents()

        latest = self._select_latest_document(self._documents) if self._documents else None
        new_state = self._extract_doc_number(latest.get("name")) if latest else 0
        attrs = self._build_latest_attributes(latest)

        if force or new_state != self._attr_native_value or attrs != self._attr_extra_state_attributes:
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
                dt = dt.replace(tzinfo=datetime.timezone.utc)
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
            # Primary key: highest document number
            if num > best_num:
                best_doc = doc
                best_num = num
                best_ts = ts
                continue
            if num < best_num:
                continue
            # Same document number: use newest publish timestamp when available
            if ts is not None and (best_ts is None or ts > best_ts):
                best_doc = doc
                best_ts = ts
        # Fallback: if we never selected anything (e.g. all names invalid), return the last doc
        return best_doc or docs[-1]

    @classmethod
    def _build_latest_attributes(cls, latest: dict | None) -> dict:
        """Build attributes for the latest document only."""
        if not isinstance(latest, dict) or not latest:
            return {}
        return {
            "name": latest.get("name"),
            "url": latest.get("url"),
            "published": latest.get("published"),
        }


class F1DriverPointsProgressionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor that exposes per-round and cumulative points per driver, including sprint points.

    - State: number of rounds included.
    - Attributes: season, rounds[], drivers{}, series{} for charting.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-line"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._recompute()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                attrs = dict(getattr(last, "attributes", {}) or {})
                self._attr_extra_state_attributes = attrs
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._recompute()
        self.async_write_ha_state()

    def _get_sprint_results(self) -> list:
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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

    def _get_full_schedule(self) -> list:
        """Return full season schedule (all planned rounds) from race_coordinator if available."""
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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
                        round_num = int(str(lists[0].get("round") or 0)) if str(lists[0].get("round") or "").isdigit() else None
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
            return points_map, round_num
        except Exception:
            return {}, None

    @staticmethod
    def _to_float(value):
        try:
            if value is None:
                return 0.0
            s = str(value).strip()
            return float(s) if s else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _combine_date_time(date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            import datetime as _dt
            dt = _dt.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except Exception:
            return None

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = (
            data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        )
        season = None
        rounds_meta = []
        # Build base per-round points from race Results
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        name_map: dict[str, dict] = {}
        round_numbers: list[int] = []
        for race in races:
            season = season or race.get("season")
            rnd = int(str(race.get("round") or 0)) if str(race.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append({
                "round": rnd,
                "race_name": race.get("raceName"),
                "date": self._combine_date_time(race.get("date"), race.get("time")),
            })
            # Prepare default 0 entries first
            # We'll fill driver points dynamically as we encounter drivers
            results = race.get("Results", []) or []
            # Determine winner code for wins array
            winner_code = None
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                if res.get("position") == "1" or res.get("positionText") == "1":
                    winner_code = code
                name_map.setdefault(code, {
                    "code": drv.get("code") or None,
                    "driverId": drv.get("driverId"),
                    "name": f"{drv.get('givenName','')} {drv.get('familyName','')}".strip() or drv.get("familyName"),
                })
                # Ensure lists are sized to rnd index (append later)
            # Assign race points
            for res in results:
                drv = res.get("Driver", {}) or {}
                code = drv.get("code") or drv.get("driverId")
                if not code:
                    continue
                pts = self._to_float(res.get("points"))
                per_round_points.setdefault(code, [])
                wins_per_round.setdefault(code, [])
                per_round_points[code].append(pts)
                wins_per_round[code].append(1 if code == winner_code else 0)
            # Normalize length for drivers missing this round
            max_len = len(round_numbers)
            for code in list(per_round_points.keys()):
                while len(per_round_points[code]) < max_len:
                    per_round_points[code].append(0.0)
                while len(wins_per_round[code]) < max_len:
                    wins_per_round[code].append(0)

        # Merge sprint points (by round)
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = int(str(sp.get("round") or 0)) if str(sp.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            if rnd not in round_index:
                # Lägg till sprint-rond som ännu ej har kört huvudlopp
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append({
                    "round": rnd,
                    "race_name": sp.get("raceName"),
                    "date": self._combine_date_time(sp.get("date"), sp.get("time")),
                })
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
                pts = self._to_float(res.get("points"))
                per_round_points.setdefault(code, [0.0] * len(round_numbers))
                wins_per_round.setdefault(code, [None] * len(round_numbers))
                # Add sprint points to the same round
                try:
                    per_round_points[code][idx] += pts
                except Exception:
                    pass

        # Align totals with latest standings if they refer to a newer round
        try:
            standings_map, standings_round = self._get_driver_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                # If standings reference a newer round, create it
                new_index_created = False
                if standings_round and (max_round is None or standings_round > max_round):
                    round_numbers.append(standings_round)
                    rounds_meta.append({
                        "round": standings_round,
                        "race_name": None,
                        "date": None,
                    })
                    # pad existing arrays
                    for code in list(per_round_points.keys()):
                        per_round_points[code].append(0.0)
                    for code in list(wins_per_round.keys()):
                        wins_per_round[code].append(None)
                    new_index_created = True
                # Compute and apply deltas
                for code, total_pts in standings_map.items():
                    pts_list = per_round_points.get(code)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        try:
                            computed_total += float(v or 0.0)
                        except Exception:
                            pass
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        # Apply delta to last available round (new one if created)
                        if new_index_created:
                            per_round_points[code][-1] = (per_round_points[code][-1] or 0.0) + delta
                        else:
                            per_round_points[code][-1] = (per_round_points[code][-1] or 0.0) + delta
        except Exception:
            pass

        # Återställ: visa endast körda ronder (som vi redan byggt från resultat)

        # Bygg cumulative och totals samt series
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
            # Sanitize None -> 0 for totals
            safe_wins = [int(w) if isinstance(w, int) else (1 if w is True else 0) for w in wins]
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
            series["series"].append({
                "key": info.get("code") or code,
                "name": info.get("name") or code,
                "data": cum,
            })

        self._attr_native_value = len(round_numbers) if round_numbers else None
        self._attr_extra_state_attributes = {
            "season": season,
            "rounds": rounds_meta,
            "drivers": drivers_attr,
            "series": series,
        }


class F1ConstructorPointsProgressionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Constructor points per team by round, including sprint; cumulative series for charts."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:chart-line"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._recompute()
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._recompute()
        self.async_write_ha_state()

    def _get_sprint_results(self) -> list:
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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

    @staticmethod
    def _to_float(value):
        try:
            if value is None:
                return 0.0
            s = str(value).strip()
            return float(s) if s else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _combine_date_time(date_str, time_str):
        if not date_str:
            return None
        if not time_str:
            time_str = "00:00:00Z"
        dt_str = f"{date_str}T{time_str}".replace("Z", "+00:00")
        try:
            import datetime as _dt
            dt = _dt.datetime.fromisoformat(dt_str)
            return dt.isoformat()
        except Exception:
            return None

    def _recompute(self) -> None:
        data = self.coordinator.data or {}
        races = (
            data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        )
        season = None
        rounds_meta = []
        round_numbers: list[int] = []

        # Per round team points and wins
        per_round_points: dict[str, list[float]] = {}
        wins_per_round: dict[str, list[int]] = {}
        team_info: dict[str, dict] = {}  # constructorId -> {name}

        for race in races:
            season = season or race.get("season")
            rnd = int(str(race.get("round") or 0)) if str(race.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            round_numbers.append(rnd)
            rounds_meta.append({
                "round": rnd,
                "race_name": race.get("raceName"),
                "date": self._combine_date_time(race.get("date"), race.get("time")),
            })

            # Aggregate points by constructor this round
            results = race.get("Results", []) or []
            # Identify winning constructor (winner driver position 1)
            winning_constructor = None
            for res in results:
                if str(res.get("position") or res.get("positionText")) == "1":
                    c = (res.get("Constructor") or {}).get("constructorId")
                    winning_constructor = c
                    break
            # Sum per constructor
            per_round_sum: dict[str, float] = {}
            for res in results:
                cons = res.get("Constructor", {}) or {}
                cid = cons.get("constructorId") or cons.get("name")
                if not cid:
                    continue
                team_info.setdefault(cid, {"constructorId": cons.get("constructorId"), "name": cons.get("name")})
                per_round_sum[cid] = per_round_sum.get(cid, 0.0) + self._to_float(res.get("points"))

            # Append to arrays
            for cid, pts in per_round_sum.items():
                per_round_points.setdefault(cid, [])
                wins_per_round.setdefault(cid, [])
                per_round_points[cid].append(pts)
                wins_per_round[cid].append(1 if cid == winning_constructor else 0)
            # Normalize length for teams not present in this round
            max_len = len(round_numbers)
            for cid in list(per_round_points.keys()):
                while len(per_round_points[cid]) < max_len:
                    per_round_points[cid].append(0.0)
                while len(wins_per_round[cid]) < max_len:
                    wins_per_round[cid].append(0)

        # Merge sprint points
        sprints = self._get_sprint_results()
        round_index = {r: idx for idx, r in enumerate(round_numbers)}
        for sp in sprints or []:
            rnd = int(str(sp.get("round") or 0)) if str(sp.get("round") or "").isdigit() else None
            if rnd is None:
                continue
            if rnd not in round_index:
                # Lägg till sprint-rond även om huvudlopp saknas
                round_index[rnd] = len(round_numbers)
                round_numbers.append(rnd)
                rounds_meta.append({
                    "round": rnd,
                    "race_name": sp.get("raceName"),
                    "date": self._combine_date_time(sp.get("date"), sp.get("time")),
                })
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
                team_info.setdefault(cid, {"constructorId": cons.get("constructorId"), "name": cons.get("name")})
                per_round_points.setdefault(cid, [0.0] * len(round_numbers))
                wins_per_round.setdefault(cid, [None] * len(round_numbers))
                try:
                    per_round_points[cid][idx] += self._to_float(res.get("points"))
                except Exception:
                    pass

        # Synka totals med senaste Constructor Standings
        try:
            standings_map, standings_round = self._get_constructor_standings()
            if standings_map:
                max_round = max(round_numbers) if round_numbers else None
                new_index_created = False
                if standings_round and (max_round is None or standings_round > max_round):
                    round_numbers.append(standings_round)
                    rounds_meta.append({
                        "round": standings_round,
                        "race_name": None,
                        "date": None,
                    })
                    for cid in list(per_round_points.keys()):
                        per_round_points[cid].append(0.0)
                    for cid in list(wins_per_round.keys()):
                        wins_per_round[cid].append(None)
                    new_index_created = True
                for cid, total_pts in standings_map.items():
                    pts_list = per_round_points.get(cid)
                    if not pts_list:
                        continue
                    computed_total = 0.0
                    for v in pts_list:
                        try:
                            computed_total += float(v or 0.0)
                        except Exception:
                            pass
                    delta = round(float(total_pts - computed_total), 3)
                    if delta > 0.0:
                        per_round_points[cid][-1] = (per_round_points[cid][-1] or 0.0) + delta
        except Exception:
            pass

        # Build cumulative and series
        teams_attr = {}
        series = {"labels": [f"R{r}" for r in round_numbers], "series": []}
        for cid, pts_list in per_round_points.items():
            cum = []
            total = 0.0
            for p in pts_list:
                total += float(p or 0.0)
                cum.append(total)
            wins = wins_per_round.get(cid, [0] * len(pts_list))
            safe_wins = [int(w) if isinstance(w, int) else (1 if w is True else 0) for w in wins]
            info = team_info.get(cid, {"name": cid})
            teams_attr[cid] = {
                "identity": {"constructorId": info.get("constructorId"), "name": info.get("name")},
                "points_per_round": pts_list,
                "cumulative_points": cum,
                "wins_per_round": wins,
                "totals": {"points": total, "wins": sum(safe_wins)},
            }
            series["series"].append({
                "key": info.get("constructorId") or cid,
                "name": info.get("name") or cid,
                "data": cum,
            })

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
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
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
                        round_num = int(str(lists[0].get("round") or 0)) if str(lists[0].get("round") or "").isdigit() else None
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
            return points_map, round_num
        except Exception:
            return {}, None


class F1TrackWeatherSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor for live track weather via WeatherData feed.

    State: air temperature (Celsius). Attributes include track temp, humidity, pressure, rainfall,
    wind speed and direction, with units. Restores last value on restart if no live data yet.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:thermometer"
        try:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = "°C"
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        # No stale timer: we keep last known value until a new payload arrives

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator if available, else restore
        init = self._extract_current()
        if init is not None:
            self._apply_payload(init)
            try:
                getLogger(__name__).debug("TrackWeather: Initialized from coordinator: %s", init)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                # Restore last known state and attributes; do not clear due to age
                self._attr_native_value = self._to_float(last.state)
                attrs = dict(getattr(last, "attributes", {}) or {})
                for k in ("measurement_time", "measurement_age_seconds", "received_at"):
                    attrs.pop(k, None)
                self._attr_extra_state_attributes = attrs
                try:
                    getLogger(__name__).debug("TrackWeather: Restored last state: %s", last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        return

    def _to_float(self, value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        # Accept direct dict from coordinator
        if isinstance(data, dict) and any(k in data for k in ("TrackTemp", "AirTemp", "Humidity")):
            return data
        # Or wrapped inside {"data": {...}}
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            inner = data.get("data")
            if any(k in inner for k in ("TrackTemp", "AirTemp", "Humidity")):
                return inner
        # Fallback: recent history buffer if available
        history = getattr(self.coordinator, "data_list", None)
        if isinstance(history, list) and history:
            last = history[-1]
            if isinstance(last, dict) and any(k in last for k in ("TrackTemp", "AirTemp", "Humidity")):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        # Parse and set state and attributes
        track_temp = self._to_float(raw.get("TrackTemp"))
        air_temp = self._to_float(raw.get("AirTemp"))
        humidity = self._to_float(raw.get("Humidity"))
        pressure = self._to_float(raw.get("Pressure"))
        rainfall = self._to_float(raw.get("Rainfall"))
        wind_dir = self._to_float(raw.get("WindDirection"))
        wind_speed = self._to_float(raw.get("WindSpeed"))

        # Try to extract a timestamp from the payload; if absent, infer measurement time as now
        ts_iso = None
        age_seconds = None
        received_at_update = None
        measurement_inferred = False
        now_utc = dt_util.utcnow()
        try:
            utc_raw = (
                raw.get("Utc")
                or raw.get("utc")
                or raw.get("processedAt")
                or raw.get("timestamp")
            )
            if utc_raw:
                ts = datetime.datetime.fromisoformat(str(utc_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                ts_iso = ts.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
                self._last_timestamped_dt = ts
                try:
                    age_seconds = (now_utc - ts).total_seconds()
                except Exception:
                    age_seconds = None
                # Only update 'received_at' when payload carries a timestamp
                received_at_update = now_utc.isoformat(timespec="seconds")
            else:
                # No explicit timestamp; do not assign measurement_time
                ts_iso = None
                measurement_inferred = True
                age_seconds = None
        except Exception:
            ts_iso = None

        try:
            getLogger(__name__).debug(
                "TrackWeather sensor state computed at %s, raw=%s -> air_temp=%s (inferred_ts=%s)",
                now_utc.isoformat(timespec="seconds"),
                raw,
                air_temp,
                measurement_inferred,
            )
        except Exception:
            pass

        self._attr_native_value = air_temp
        self._last_received_utc = now_utc
        self._attr_extra_state_attributes = {
            "air_temperature": air_temp,
            "air_temperature_unit": "celsius",
            "humidity": humidity,
            "humidity_unit": "%",
            "pressure": pressure,
            "pressure_unit": "hPa",
            "rainfall": rainfall,
            "rainfall_unit": "mm",
            "track_temperature": track_temp,
            "track_temperature_unit": "celsius",
            "wind_speed": wind_speed,
            "wind_speed_unit": "m/s",
            "wind_from_direction_degrees": wind_dir,
            "wind_from_direction_unit": "degrees",
            "measurement_inferred": measurement_inferred,
        }

        # No staleness handling: keep last known value until a new payload arrives

    # No stale scheduling required for Track Weather

    # No stale timeout handler

    # Use default attributes storage; do not force placeholders

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        if raw is None:
            # Keep last known values; just log an update
            try:
                getLogger(__name__).debug(
                    "TrackWeather: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            except Exception:
                pass
            self._safe_write_ha_state()
            return
        self._apply_payload(raw)
        self._safe_write_ha_state()

    def _safe_write_ha_state(self) -> None:
        try:
            in_loop = False
            try:
                running = asyncio.get_running_loop()
                in_loop = running is self.hass.loop
            except RuntimeError:
                in_loop = False
            if in_loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()
        except Exception:
            # Last resort: avoid raising in thread-safety guard
            try:
                self.schedule_update_ha_state()
            except Exception:
                pass


class F1TrackStatusSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Track status sensor independent from flag logic."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-checkered"
        self._attr_native_value = None
        # Advertise as enum sensor so HA UI can suggest valid states
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        # Canonical states as produced by normalize_track_status
        self._attr_options = [
            "CLEAR",
            "YELLOW",
            "VSC",
            "SC",
            "RED",
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Prefer coordinator's latest if present, otherwise restore last state
        initial = self._normalize(self._extract_current())
        if initial is not None:
            self._attr_native_value = initial
            try:
                from logging import getLogger
                getLogger(__name__).debug("TrackStatus: Initialized from coordinator: %s", initial)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                try:
                    from logging import getLogger
                    getLogger(__name__).debug("TrackStatus: Restored last state: %s", last.state)
                except Exception:
                    pass
        # Listen for coordinator pushes
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state() 

    def _normalize(self, raw: dict | None) -> str | None:
        return normalize_track_status(raw)

    def _extract_current(self) -> dict | None:
        # Coordinator stores last payload for TrackStatus
        data = self.coordinator.data
        if not data:
            # Fallback: some ws updates may only land in data_list initially
            try:
                hist = getattr(self.coordinator, "data_list", None)
                if isinstance(hist, list) and hist:
                    last = hist[-1]
                    if isinstance(last, dict):
                        return last
            except Exception:  # noqa: BLE001
                pass
            # Final fallback: integration-level latest cache
            try:
                cache = self.hass.data.get(LATEST_TRACK_STATUS)
                if isinstance(cache, dict):
                    return cache
            except Exception:  # noqa: BLE001
                pass
            return None
        # Expect either direct dict or wrapper with 'data'
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
        return None

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def state(self):
        # Return stored value so restored/initialized state is honored until an update arrives
        return self._attr_native_value

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        new_state = self._normalize(raw)
        prev = self._attr_native_value
        if prev == new_state:
            return
        try:
            from logging import getLogger
            getLogger(__name__).debug(
                "TrackStatus changed at %s: %s -> %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev,
                new_state,
            )
        except Exception:  # noqa: BLE001
            pass
        self._attr_native_value = new_state
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return {}


class F1TopThreePositionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live Top Three sensor for a single position (P1, P2 eller P3).

    - State: TLA (t.ex. VER) för vald position när Withheld är False.
    - Attribut: withhold-flagga och fält för just den positionen.
    """

    def __init__(
        self,
        coordinator,
        sensor_name,
        unique_id,
        entry_id,
        device_name,
        position_index: int,
    ):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        # 0-baserat index: 0=P1, 1=P2, 2=P3
        self._position_index = max(0, min(2, int(position_index or 0)))
        # Enkelt ikonval; P1 kan få "full" trophy
        if self._position_index == 0:
            self._attr_icon = "mdi:trophy"
        else:
            self._attr_icon = "mdi:trophy-outline"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Försök initialisera från koordinatorns state; annars restaurera från historik
        self._update_from_coordinator(initial=True)
        if self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                try:
                    attrs = dict(getattr(last, "attributes", {}) or {})
                    self._attr_extra_state_attributes = attrs
                    from logging import getLogger

                    getLogger(__name__).debug(
                        "TopThree P%s: Restored last state: %s",
                        self._position_index + 1,
                        last.state,
                    )
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _extract_state(self) -> dict | None:
        data = self.coordinator.data
        if not isinstance(data, dict):
            return None
        # Förvänta samma struktur som TopThreeCoordinator._state
        # { "withheld": bool|None, "lines": [dict|None, dict|None, dict|None], ... }
        lines = data.get("lines")
        if not isinstance(lines, list):
            return {
                "withheld": data.get("withheld"),
                "lines": [None, None, None],
                "last_update_ts": data.get("last_update_ts"),
            }
        # Normalisera till exakt tre element
        norm = []
        for idx in range(3):
            try:
                item = lines[idx]
            except Exception:
                item = None
            norm.append(item if isinstance(item, dict) else None)
        return {
            "withheld": data.get("withheld"),
            "lines": norm,
            "last_update_ts": data.get("last_update_ts"),
        }

    @staticmethod
    def _normalize_color(value):
        if not isinstance(value, str) or not value:
            return value
        try:
            s = value.strip()
            if not s:
                return s
            if s.startswith("#"):
                return s
            return f"#{s}"
        except Exception:
            return value

    def _build_attrs(self, state: dict | None, line: dict | None) -> dict:
        """Bygg ett komplett attributschema även när ingen data finns ännu.

        Detta gör det enklare för användaren att se vilka fält som finns tillgängliga.
        """
        if isinstance(state, dict):
            withheld = state.get("withheld")
            last_update_ts = state.get("last_update_ts")
        else:
            withheld = None
            last_update_ts = None

        withheld_flag = bool(withheld) if withheld is not None else None

        if isinstance(line, dict):
            team_color = self._normalize_color(
                line.get("TeamColour") or line.get("TeamColor")
            )
            position = line.get("Position")
            racing_number = line.get("RacingNumber")
            tla = line.get("Tla") or line.get("TLA")
            broadcast_name = line.get("BroadcastName")
            full_name = line.get("FullName")
            first_name = line.get("FirstName")
            last_name = line.get("LastName")
            team = line.get("Team")
            lap_time = line.get("LapTime")
            overall_fastest = line.get("OverallFastest")
            personal_fastest = line.get("PersonalFastest")
        else:
            team_color = None
            # Vi känner fortfarande till “index” (P1/P2/P3), men position i loppet
            # kan vara okänd när feeden inte skickat något ännu.
            position = None
            racing_number = None
            tla = None
            broadcast_name = None
            full_name = None
            first_name = None
            last_name = None
            team = None
            lap_time = None
            overall_fastest = None
            personal_fastest = None

        return {
            "withheld": withheld_flag,
            # “position” = position i listan (om känd från feeden)
            "position": position,
            "racing_number": racing_number,
            "tla": tla,
            "broadcast_name": broadcast_name,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "team": team,
            "team_color": team_color,
            "lap_time": lap_time,
            "overall_fastest": overall_fastest,
            "personal_fastest": personal_fastest,
            "last_update_ts": last_update_ts,
        }

    def _update_from_coordinator(self, *, initial: bool = False) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes

        state = self._extract_state()
        if not isinstance(state, dict):
            self._attr_native_value = None
            # Ingen feed-data ännu – exponera ändå fulla attribut med None-värden
            self._attr_extra_state_attributes = self._build_attrs(None, None)
            return

        withheld = state.get("withheld")
        lines = state.get("lines") or [None, None, None]

        if withheld is True:
            # När F1 undanhåller topp-3-data, exponera inget state
            self._attr_native_value = None
            self._attr_extra_state_attributes = self._build_attrs(state, None)
            return

        # Hämta raden för den här sensorns position
        line = None
        try:
            line = lines[self._position_index]
        except Exception:
            line = None

        if not isinstance(line, dict):
            self._attr_native_value = None
            self._attr_extra_state_attributes = self._build_attrs(state, None)
        else:
            tla = line.get("Tla") or line.get("TLA") or line.get("BroadcastName")
            self._attr_native_value = tla
            self._attr_extra_state_attributes = self._build_attrs(state, line)

        # På initial start vill vi alltid skriva state; annars kan vi rate-limita
        if initial:
            return

        if (
            prev_state == self._attr_native_value
            and prev_attrs == self._attr_extra_state_attributes
        ):
            return

        try:
            from logging import getLogger

            getLogger(__name__).debug(
                "TopThree P%s changed at %s: %s -> %s",
                self._position_index + 1,
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev_state,
                self._attr_native_value,
            )
        except Exception:
            pass

        # Rate-limita skrivningar till max var 5:e sekund
        try:
            import time as _time

            lw = getattr(self, "_last_write_ts", None)
            now = _time.time()
            if lw is None or (now - lw) >= 5.0:
                setattr(self, "_last_write_ts", now)
                self._safe_write_ha_state()
            else:
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    setattr(self, "_pending_write", True)
                    delay = max(0.0, 5.0 - (now - lw)) if lw is not None else 5.0

                    def _do_write(_):
                        try:
                            setattr(self, "_last_write_ts", _time.time())
                            self._safe_write_ha_state()
                        finally:
                            setattr(self, "_pending_write", False)

                    async_call_later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        self._update_from_coordinator(initial=False)

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def state(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes


class F1SessionStatusSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor mapping SessionStatus to semantic states for automations."""

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:timer-play"
        self._attr_native_value = None
        self._started_flag = None
        # Advertise as enum sensor so HA UI can suggest valid states
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        # Possible mapped states from _map_status
        self._attr_options = [
            "pre",
            "live",
            "suspended",
            "break",
            "finished",
            "finalised",
            "ended",
        ]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator or restore
        init = self._extract_current()
        if init is not None:
            self._attr_native_value = self._map_status(init)
            try:
                getLogger(__name__).debug("SessionStatus: Initialized from coordinator: raw=%s -> %s", init, self._attr_native_value)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                try:
                    getLogger(__name__).debug("SessionStatus: Restored last state: %s", last.state)
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if not data:
            return None
        if isinstance(data, dict) and ("Status" in data or "Message" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict):
            return inner
        return None

    def _map_status(self, raw: dict | None) -> str | None:
        if not raw:
            return None
        # Prefer explicit string in Status, fall back to Message
        message = str(raw.get("Status") or raw.get("Message") or "").strip()
        started_hint = str(raw.get("Started") or "").strip()

        # Stateless mapping based only on this payload.
        if message == "Started":
            return "live"

        if message == "Finished":
            # A qualifying part or the session segment ended.
            # Reset internal memory defensively.
            self._started_flag = None
            return "finished"

        if message == "Finalised":
            # Session finalised without requiring a prior "Finished".
            self._started_flag = None
            return "finalised"

        if message == "Ends":
            # Session officially ends. Clear any sticky state.
            self._started_flag = None
            return "ended"

        if message == "Inactive":
            # Planned qualifying break vs. suspension vs. pre-session
            if started_hint == "Finished":
                # Planned pause between quali segments
                self._started_flag = None
                return "break"
            if started_hint == "Started":
                # Tie-break using latest TrackStatus: if not RED, treat as live
                try:
                    cache = self.hass.data.get(LATEST_TRACK_STATUS)
                    track_state = normalize_track_status(cache) if isinstance(cache, dict) else None
                except Exception:
                    track_state = None
                if track_state and track_state != "RED":
                    return "live"
                # Red flag / suspended while session is considered started
                return "suspended"
            # Not started yet
            return "pre"

        if message == "Aborted":
            # Aborted within an already started session is a suspension-like state
            if started_hint == "Started":
                # Tie-break using latest TrackStatus: if not RED, treat as live
                try:
                    cache = self.hass.data.get(LATEST_TRACK_STATUS)
                    track_state = normalize_track_status(cache) if isinstance(cache, dict) else None
                except Exception:
                    track_state = None
                if track_state and track_state != "RED":
                    return "live"
                return "suspended"
            # Otherwise treat like pre (no live running yet)
            return "pre"

        # Fallback: unknown values behave like pre-session
        return "pre"

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        new_state = self._map_status(raw)
        prev = self._attr_native_value
        if prev == new_state:
            return
        try:
            getLogger(__name__).debug(
                "SessionStatus changed at %s: %s -> %s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                prev,
                new_state,
            )
        except Exception:  # noqa: BLE001
            pass
        self._attr_native_value = new_state
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return {}


class F1CurrentSessionSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live sensor reporting current session label (e.g., Practice 1, Qualifying/Q1, Sprint Qualifying/SQ1, Sprint, Race).

    - State: compact label string
    - Attributes: full session metadata from SessionInfo (Type, Name, Number, Meeting, Circuit, Start/End),
                  session_part (numeric), resolved_label, and raw payloads; includes live status from SessionStatus if available.
    - Behavior: restores last state on restart; respects global live delay via coordinator.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:calendar-clock"
        try:
            self._attr_device_class = SensorDeviceClass.ENUM
        except Exception:
            self._attr_device_class = None
        self._attr_native_value = None
        # Enumerate possible labels for UI dropdowns in automations
        self._attr_options = [
            "Practice 1",
            "Practice 2",
            "Practice 3",
            "Qualifying",
            "Sprint Qualifying",
            "Sprint",
            "Race",
        ]
        self._status_coordinator = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Wire listeners first so _live_status() reflects current coordinator state
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        # Also listen to SessionStatus so we can clear state when session ends
        try:
            reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
            self._status_coordinator = reg.get("session_status_coordinator")
            if self._status_coordinator is not None:
                rem2 = self._status_coordinator.async_add_listener(self._handle_status_update)
                self.async_on_remove(rem2)
        except Exception:
            self._status_coordinator = None

        # Restore last known state immediately; prevents unknown on restart mid-session
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            # Restore last attributes as well for better end-detection and UI context
            attrs = dict(getattr(last, "attributes", {}) or {})
            self._attr_extra_state_attributes = attrs
            # If saved payload indicates the session ended long ago, clear state on startup
            ended_by_attrs = False
            try:
                end_iso = attrs.get("end") or attrs.get("EndDate")
                if end_iso:
                    end_dt = datetime.datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
                    now_utc = datetime.datetime.now(datetime.timezone.utc)
                    if now_utc >= (end_dt + datetime.timedelta(minutes=5)):
                        # Also consider live status if available
                        st = str(self._live_status() or "").strip()
                        if st not in ("Started", "Green", "GreenFlag"):
                            ended_by_attrs = True
            except Exception:
                ended_by_attrs = False
            if ended_by_attrs:
                # Keep last label in attributes, but clear current state
                if last.state:
                    try:
                        self._attr_extra_state_attributes = dict(attrs)
                        self._attr_extra_state_attributes.setdefault("last_label", last.state)
                        self._attr_extra_state_attributes["active"] = False
                    except Exception:
                        pass
                self._attr_native_value = None
                try:
                    getLogger(__name__).debug(
                        "CurrentSession: Restored as ended (cleared) based on saved end=%s", attrs.get("end") or attrs.get("EndDate")
                    )
                except Exception:
                    pass
            else:
                self._attr_native_value = last.state
                try:
                    getLogger(__name__).debug("CurrentSession: Restored last state: %s", last.state)
                except Exception:
                    pass

        # Initialize from coordinator if available, but avoid clearing state at startup
        init = self._extract_current()
        if init is not None:
            self._apply_payload(init, allow_clear=False)
            try:
                getLogger(__name__).debug("CurrentSession: Initialized from coordinator (no clear on startup): %s", init)
            except Exception:
                pass

        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and any(k in data for k in ("Type", "Name", "Meeting")):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and any(k in inner for k in ("Type", "Name", "Meeting")):
            return inner
        # No dedicated history usage; SessionInfo snapshots have no high-frequency heartbeat like others
        return None

    def _resolve_label(self, info: dict) -> tuple[str | None, dict]:
        t = str(info.get("Type") or "").strip()
        name = str(info.get("Name") or "").strip()
        num = info.get("Number")
        try:
            num_i = int(num) if num is not None else None
        except Exception:
            num_i = None

        # Try detect session part from consolidated drivers coordinator if available
        session_part = None
        try:
            drivers_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("drivers_coordinator")
            if drivers_data and hasattr(drivers_data, "data"):
                sd = drivers_data.data or {}
                session = sd.get("session") or {}
                session_part = session.get("part")
        except Exception:
            session_part = None

        label = None
        if t == "Practice":
            label = f"Practice {num_i}" if num_i else (name or "Practice")
        elif t == "Qualifying":
            # Aggregate all Q1/Q2/Q3 into "Qualifying"; treat Sprint Shootout as Sprint Qualifying
            nm = name.lower()
            is_sprint_quali = nm.startswith("sprint qualifying") or nm.startswith("sprint shootout")
            label = "Sprint Qualifying" if is_sprint_quali else "Qualifying"
        elif t == "Race":
            # Some events report Sprint/Sprint Qualifying under Type "Race" via Name
            nm = name.lower()
            if nm.startswith("sprint qualifying") or nm.startswith("sprint shootout"):
                label = "Sprint Qualifying"
            elif nm.startswith("sprint"):
                label = "Sprint"
            else:
                label = name or "Race"
        else:
            # Fallback: use Name then Type
            label = name or t or None

        meta = {
            "type": t or None,
            "name": name or None,
            "number": num_i,
            "session_part": session_part,
        }
        return label, meta

    def _live_status(self) -> str | None:
        try:
            if self._status_coordinator and isinstance(self._status_coordinator.data, dict):
                d = self._status_coordinator.data
                return str(d.get("Status") or d.get("Message") or "").strip()
        except Exception:
            return None
        return None

    def _apply_payload(self, raw: dict, allow_clear: bool = True) -> None:
        label, meta = self._resolve_label(raw or {})
        status = self._live_status()
        # Treat session as ended by explicit status; only use EndDate as a soft fallback with grace
        ended = str(status or "").strip() in ("Finished", "Finalised", "Ends")
        try:
            end_iso = raw.get("EndDate")
            if end_iso and not ended:
                end_dt = datetime.datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=datetime.timezone.utc)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                # Consider EndDate only if we are well past it and no active/green status is present
                if now_utc >= (end_dt + datetime.timedelta(minutes=5)):
                    st = str(status or "").strip()
                    if st not in ("Started", "Green", "GreenFlag"):
                        ended = True
        except Exception:
            pass
        active = (str(status or "").strip() == "Started")
        desired_state = None
        if label in ("Qualifying", "Sprint Qualifying"):
            desired_state = None if ended else label
        else:
            desired_state = label if active else None
        # On startup we may not yet have live status; avoid clearing to unknown
        if desired_state is None and not allow_clear:
            # Do not substitute the label on startup for ended/inactive sessions; keep prior value only
            desired_state = self._attr_native_value
        self._attr_native_value = desired_state
        attrs = dict(meta)
        # Merge common metadata
        try:
            meeting = raw.get("Meeting") or {}
            circuit = (meeting.get("Circuit") if isinstance(meeting, dict) else None) or {}
            attrs.update(
                {
                    "meeting_key": (meeting or {}).get("Key"),
                    "meeting_name": (meeting or {}).get("Name"),
                    "meeting_location": (meeting or {}).get("Location"),
                    "meeting_country": ((meeting or {}).get("Country") or {}).get("Name"),
                    "circuit_short_name": (circuit or {}).get("ShortName"),
                    "gmt_offset": raw.get("GmtOffset"),
                    "start": raw.get("StartDate"),
                    "end": raw.get("EndDate"),
                }
            )
        except Exception:
            pass
        # Include live status and activity flag
        try:
            attrs["live_status"] = status
            attrs["active"] = active
            if not active and label:
                attrs["last_label"] = label
        except Exception:
            pass
        self._attr_extra_state_attributes = attrs
        try:
            getLogger(__name__).debug(
                "CurrentSession apply: label=%s status=%s ended=%s active=%s",
                label,
                status,
                ended,
                active,
            )
        except Exception:
            pass

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        if raw is None:
            try:
                getLogger(__name__).debug(
                    "CurrentSession: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            except Exception:
                pass
            self.async_write_ha_state()
            return
        self._apply_payload(raw)
        self.async_write_ha_state()

    def _handle_status_update(self) -> None:
        # Re-evaluate state based on latest status (may clear on Ends/Finished/Finalised)
        raw = self._extract_current() or {}
        self._apply_payload(raw)
        try:
            getLogger(__name__).debug(
                "CurrentSession: Status update at %s -> state=%s, live_status=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
                self._live_status(),
            )
        except Exception:
            pass
        self.async_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value


class F1RaceControlSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Expose the latest Race Control message as an easy-to-use sensor."""

    _history_limit = 5

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:flag-outline"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_event_id: str | None = None
        self._history: list[dict] = []
        self._sequence = 0

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        payload = self._extract_current()
        if payload:
            self._apply_payload(payload, force=True)
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
                self._last_event_id = self._attr_extra_state_attributes.get("event_id")
                hist = self._attr_extra_state_attributes.get("history")
                if isinstance(hist, list):
                    self._history = [dict(item) for item in hist[: self._history_limit] if isinstance(item, dict)]
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and data:
            return data
        hist = getattr(self.coordinator, "data_list", None)
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, dict):
                return last
        return None

    def _cleanup_string(self, value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _build_event_id(self, payload: dict) -> str | None:
        ts = self._cleanup_string(
            payload.get("Utc")
            or payload.get("utc")
            or payload.get("processedAt")
            or payload.get("timestamp")
        ) or ""
        category = self._cleanup_string(payload.get("Category") or payload.get("CategoryType") or "") or ""
        message = self._cleanup_string(payload.get("Message") or payload.get("Text") or payload.get("Flag") or "") or ""
        ident = f"{ts}|{category}|{message}"
        return ident if ident.strip("|") else None

    def _resolve_icon(self, flag: str | None, category: str | None) -> str:
        flag_upper = (flag or "").upper()
        if flag_upper in ("RED", "BLACK"):
            return "mdi:flag-variant"
        if flag_upper in ("YELLOW", "DOUBLE YELLOW"):
            return "mdi:flag"
        if flag_upper in ("GREEN", "CLEAR"):
            return "mdi:flag-checkered"
        if flag_upper in ("BLUE", "WHITE"):
            return "mdi:flag-variant-outline"
        if str(category or "").lower() == "safetycar":
            return "mdi:car-emergency"
        if str(category or "").lower() == "vsc":
            return "mdi:car-brake-alert"
        return "mdi:flag-outline"

    def _format_state(self, payload: dict) -> str:
        message = self._cleanup_string(payload.get("Message") or payload.get("Text"))
        if message:
            return message[:255]
        flag = self._cleanup_string(payload.get("Flag"))
        category = self._cleanup_string(payload.get("Category") or payload.get("CategoryType"))
        scope = self._cleanup_string(payload.get("Scope"))
        sector = self._cleanup_string(payload.get("Sector"))
        parts = [part for part in (flag, category, scope, sector) if part]
        return " - ".join(parts) if parts else "Race control update"

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        event_id = self._build_event_id(payload)
        if event_id and self._last_event_id == event_id and not force:
            return

        utc_str = self._cleanup_string(
            payload.get("Utc")
            or payload.get("utc")
            or payload.get("processedAt")
            or payload.get("timestamp")
        )
        try:
            if utc_str:
                dt = datetime.datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                utc_str = dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
        except Exception:
            utc_str = self._cleanup_string(utc_str)

        category = self._cleanup_string(payload.get("Category") or payload.get("CategoryType"))
        flag = self._cleanup_string(payload.get("Flag"))
        scope = self._cleanup_string(payload.get("Scope"))
        sector = self._cleanup_string(payload.get("Sector") or payload.get("TrackSegment"))
        car_number = self._cleanup_string(
            payload.get("CarNumber")
            or payload.get("Number")
            or payload.get("Car")
            or payload.get("Driver")
        )
        message = self._format_state(payload)
        received_at = dt_util.utcnow().isoformat(timespec="seconds")

        self._sequence += 1
        attrs = {
            "utc": utc_str,
            "received_at": received_at,
            "category": category,
            "flag": flag,
            "scope": scope,
            "sector": sector,
            "car_number": car_number,
            "message": self._cleanup_string(payload.get("Message") or payload.get("Text")),
            "event_id": event_id,
            "sequence": self._sequence,
            "raw_message": payload,
        }

        history_entry = {
            "event_id": event_id,
            "utc": utc_str,
            "category": category,
            "flag": flag,
            "message": attrs["message"] or message,
        }
        self._history.insert(0, history_entry)
        self._history = self._history[: self._history_limit]
        attrs["history"] = [dict(item) for item in self._history]

        self._attr_native_value = message
        self._attr_extra_state_attributes = attrs
        self._attr_icon = self._resolve_icon(flag, category)
        if event_id:
            self._last_event_id = event_id

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        if payload is None:
            self._safe_write_ha_state()
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value


class F1TeamRadioSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Sensor exposing the latest Team Radio clip.

    - State: latest clip UTC timestamp (ISO8601, TIMESTAMP device_class)
    - Attributes: racing_number, path, received_at, sequence, history, raw_message
    """

    _history_limit = 20

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:headset"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._last_utc: str | None = None
        self._history: list[dict] = []
        self._sequence = 0

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        payload = self._extract_current()
        if payload:
            self._apply_payload(payload, force=True)
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                # Restore last timestamp state as string
                self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(
                    getattr(last, "attributes", {}) or {}
                )
                hist = self._attr_extra_state_attributes.get("history")
                if isinstance(hist, list):
                    self._history = [
                        dict(item)
                        for item in hist[: self._history_limit]
                        if isinstance(item, dict)
                    ]
                self._last_utc = self._attr_extra_state_attributes.get("utc")
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        # TeamRadioCoordinator exposes {"latest": {...}, "history": [...]}
        if isinstance(data, dict):
            latest = data.get("latest")
            if isinstance(latest, dict):
                return latest
        return None

    def _cleanup_string(self, value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_utc(self, utc_str: str | None) -> str | None:
        text = self._cleanup_string(utc_str)
        if not text:
            return None
        try:
            dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
        except Exception:
            return text

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        utc_raw = (
            payload.get("Utc")
            or payload.get("utc")
            or payload.get("processedAt")
            or payload.get("timestamp")
        )
        utc_norm = self._normalize_utc(utc_raw)
        if utc_norm and self._last_utc == utc_norm and not force:
            return

        racing_number = self._cleanup_string(payload.get("RacingNumber"))
        path = self._cleanup_string(payload.get("Path"))
        clip_url = None

        # 1) Försök använda statisk root från replay-dumpen (development-läge)
        static_root = self._cleanup_string(
            payload.get("_static_root") or payload.get("static_root")
        )
        if static_root and path:
            clip_url = f"{static_root.rstrip('/')}/{path.lstrip('/')}"

        # 2) Fallback: bygg URL från LiveSession-window (live-läge)
        if clip_url is None:
            try:
                if self.hass and path:
                    reg = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
                    live_supervisor = reg.get("live_supervisor") if isinstance(reg, dict) else None
                    window = getattr(live_supervisor, "current_window", None)
                    base_path = getattr(window, "path", None)
                    if isinstance(base_path, str) and base_path:
                        # Index.json "Path" can be either:
                        # - "2025/2025-12-07_Abu_Dhabi_Grand_Prix/2025-12-07_Race/"
                        # - "2025-12-07_Abu_Dhabi_Grand_Prix/2025-12-07_Race/"
                        # Ensure we have the year segment when missing so the resulting URL is usable.
                        cleaned_base = base_path.strip("/")
                        year = None
                        try:
                            if isinstance(reg, dict):
                                session_coord = reg.get("session_coordinator")
                                year = getattr(session_coord, "year", None)
                        except Exception:
                            year = None
                        try:
                            if cleaned_base and not re.match(r"^\d{4}/", f"{cleaned_base}/"):
                                if year and str(year).isdigit():
                                    cleaned_base = f"{int(year)}/{cleaned_base}"
                        except Exception:
                            # Keep best-effort base if regex/year parsing fails
                            cleaned_base = base_path.strip("/")
                        root = f"{STATIC_BASE}/{cleaned_base}"
                        clip_url = f"{root}/{path.lstrip('/')}"
            except Exception:
                clip_url = None

        received_at = dt_util.utcnow().isoformat(timespec="seconds")

        self._sequence += 1

        attrs = {
            "utc": utc_norm,
            "received_at": received_at,
            "racing_number": racing_number,
            "path": path,
            "clip_url": clip_url,
            "sequence": self._sequence,
            "raw_message": payload,
        }

        history_entry = {
            "utc": utc_norm,
            "racing_number": racing_number,
            "path": path,
            "clip_url": clip_url,
        }
        self._history.insert(0, history_entry)
        self._history = self._history[: self._history_limit]
        attrs["history"] = [dict(item) for item in self._history]

        self._attr_native_value = utc_norm
        self._attr_extra_state_attributes = attrs
        self._last_utc = utc_norm

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        if payload is None:
            self._safe_write_ha_state()
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()

    @property
    def state(self):
        return self._attr_native_value


class F1PitStopsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live pit stops for all cars (aggregated).

    - State: total pit stops (int)
    - Attributes: cars (dict keyed by racing number), last_update
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:car-wrench"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"cars": {}, "last_update": None}
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        init = self._extract_current()
        if init is not None:
            self._apply_payload(init, force=True)
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(float(str(last.state)))
                except Exception:
                    self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(
                    getattr(last, "attributes", {}) or {}
                )
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        total = payload.get("total_stops")
        cars = payload.get("cars")
        last_update = payload.get("last_update")

        try:
            total_int = int(total) if total is not None else 0
        except Exception:
            try:
                total_int = int(float(str(total)))
            except Exception:
                total_int = 0

        # Avoid unnecessary writes
        if (not force) and self._attr_native_value == total_int:
            try:
                prev_cars = (self._attr_extra_state_attributes or {}).get("cars")
                if prev_cars == cars:
                    return
            except Exception:
                pass

        self._attr_native_value = total_int
        self._attr_extra_state_attributes = {
            "cars": cars if isinstance(cars, dict) else {},
            "last_update": last_update,
        }

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        if payload is None:
            self._safe_write_ha_state()
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()


class F1ChampionshipPredictionDriversSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Predicted Drivers Championship winner (P1).

    - State: predicted P1 driver TLA (string) when available
    - Attributes: predicted_driver_p1, drivers, last_update
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:trophy"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        init = self._extract_current()
        if init is not None:
            self._apply_payload(init, force=True)
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        pred = payload.get("predicted_driver_p1")
        drivers = payload.get("drivers")
        last_update = payload.get("last_update")

        tla = None
        if isinstance(pred, dict):
            tla = pred.get("tla")
        if tla is not None:
            tla = str(tla).strip() or None

        if (not force) and self._attr_native_value == tla:
            return

        self._attr_native_value = tla
        self._attr_extra_state_attributes = {
            "predicted_driver_p1": pred if isinstance(pred, dict) else None,
            "drivers": drivers if isinstance(drivers, dict) else {},
            "last_update": last_update,
        }

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        if payload is None:
            self._safe_write_ha_state()
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()


class F1ChampionshipPredictionTeamsSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Predicted Constructors Championship winner (P1).

    - State: predicted P1 team name (string)
    - Attributes: predicted_team_p1, teams, last_update
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:trophy-variant"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)

        init = self._extract_current()
        if init is not None:
            self._apply_payload(init, force=True)
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = last.state
                self._attr_extra_state_attributes = dict(getattr(last, "attributes", {}) or {})
        self.async_write_ha_state()

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        return data if isinstance(data, dict) else None

    def _apply_payload(self, payload: dict, *, force: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        pred = payload.get("predicted_team_p1")
        teams = payload.get("teams")
        last_update = payload.get("last_update")

        team_name = None
        if isinstance(pred, dict):
            team_name = pred.get("team_name")
        if team_name is not None:
            team_name = str(team_name).strip() or None

        if (not force) and self._attr_native_value == team_name:
            return

        self._attr_native_value = team_name
        self._attr_extra_state_attributes = {
            "predicted_team_p1": pred if isinstance(pred, dict) else None,
            "teams": teams if isinstance(teams, dict) else {},
            "last_update": last_update,
        }

    def _handle_coordinator_update(self) -> None:
        payload = self._extract_current()
        if payload is None:
            self._safe_write_ha_state()
            return
        self._apply_payload(payload)
        self._safe_write_ha_state()


class F1RaceLapCountSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live race lap count based on LapCount coordinator.

    - State: current lap (int)
    - Attributes: total_laps (if present), measurement_time, measurement_age_seconds, received_at, raw
    - Restore: Remembers last value/attributes on restart and keeps them until new feed data arrives.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:counter"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._last_timestamped_dt = None
        self._last_received_utc = None
        self._stale_timer = None
        

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        init = self._extract_current()
        if init is not None:
            self._apply_payload(init)
            try:
                getLogger(__name__).debug("RaceLapCount: Initialized from coordinator: %s", init)
            except Exception:
                pass
        else:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                self._attr_native_value = self._to_int(last.state)
                attrs = dict(getattr(last, "attributes", {}) or {})
                for k in ("measurement_time", "measurement_age_seconds", "received_at"):
                    attrs.pop(k, None)
                self._attr_extra_state_attributes = attrs
                now_utc = dt_util.utcnow()
                try:
                    t_ref = None
                    mt = self._attr_extra_state_attributes.get("measurement_time")
                    if isinstance(mt, str) and mt:
                        t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                        if t_ref.tzinfo is None:
                            t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                        self._last_timestamped_dt = t_ref
                    if t_ref is None:
                        ra = self._attr_extra_state_attributes.get("received_at")
                        if isinstance(ra, str) and ra:
                            t_ref = datetime.datetime.fromisoformat(ra.replace("Z", "+00:00"))
                            if t_ref.tzinfo is None:
                                t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                    if isinstance(t_ref, datetime.datetime):
                        self._last_received_utc = t_ref
                except Exception:
                    pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self._safe_write_ha_state()
        # No staleness timer: we keep last known value until new feed data arrives
        

    async def async_will_remove_from_hass(self) -> None:
        try:
            if self._stale_timer:
                self._stale_timer()
                self._stale_timer = None
        except Exception:
            pass
        

    def _to_int(self, value):
        try:
            if value is None:
                return None
            return int(float(value))
        except Exception:
            return None

    def _extract_current(self) -> dict | None:
        data = self.coordinator.data
        if isinstance(data, dict) and ("CurrentLap" in data or "TotalLaps" in data or "LapCount" in data):
            return data
        inner = data.get("data") if isinstance(data, dict) else None
        if isinstance(inner, dict) and ("CurrentLap" in inner or "TotalLaps" in inner or "LapCount" in inner):
            return inner
        hist = getattr(self.coordinator, "data_list", None)
        if isinstance(hist, list) and hist:
            last = hist[-1]
            if isinstance(last, dict) and ("CurrentLap" in last or "TotalLaps" in last or "LapCount" in last):
                return last
        return None

    def _apply_payload(self, raw: dict) -> None:
        curr = self._to_int(raw.get("CurrentLap") if "CurrentLap" in raw else raw.get("LapCount"))
        total = self._to_int(raw.get("TotalLaps"))

        ts_iso = None
        age_seconds = None
        received_at_update = None
        now_utc = dt_util.utcnow()
        try:
            utc_raw = (
                raw.get("Utc")
                or raw.get("utc")
                or raw.get("processedAt")
                or raw.get("timestamp")
            )
            if utc_raw:
                ts = datetime.datetime.fromisoformat(str(utc_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=datetime.timezone.utc)
                ts_iso = ts.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")
                self._last_timestamped_dt = ts
                try:
                    age_seconds = (now_utc - ts).total_seconds()
                except Exception:
                    age_seconds = None
                received_at_update = now_utc.isoformat(timespec="seconds")
        except Exception:
            ts_iso = None

        self._attr_native_value = curr
        self._last_received_utc = now_utc
        # Preserve last known total_laps if not present in this payload to avoid transient 'unknown'
        prev_total = None
        try:
            prev_total = (self._attr_extra_state_attributes or {}).get("total_laps")
        except Exception:
            prev_total = None
        if total is None:
            total = prev_total
        self._attr_extra_state_attributes = {
            "total_laps": total,
        }

        # No staleness handling: do not clear state; keep last value until a new payload arrives

    def _schedule_stale_check(self, t_ref: datetime.datetime | None = None, now_utc: datetime.datetime | None = None) -> None:
        try:
            if now_utc is None:
                now_utc = dt_util.utcnow()
            if t_ref is None:
                t_ref = None
                mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
                if isinstance(mt, str) and mt:
                    try:
                        t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                        if t_ref.tzinfo is None:
                            t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                    except Exception:
                        t_ref = None
                if t_ref is None and isinstance(self._last_timestamped_dt, datetime.datetime):
                    t_ref = self._last_timestamped_dt
                if t_ref is None and isinstance(self._last_received_utc, datetime.datetime):
                    t_ref = self._last_received_utc
            if not isinstance(t_ref, datetime.datetime):
                return
            age = (now_utc - t_ref).total_seconds()
            threshold = 300
            delay = max(0.0, threshold - age)
            if self._stale_timer:
                try:
                    self._stale_timer()
                except Exception:
                    pass
                self._stale_timer = None
            def _cb(_now):
                self._handle_stale_timeout()
            self._stale_timer = async_call_later(self.hass, delay, _cb)
        except Exception:
            pass

    def _handle_stale_timeout(self) -> None:
        try:
            now_utc = dt_util.utcnow()
            t_ref = None
            mt = (self._attr_extra_state_attributes or {}).get("measurement_time")
            if isinstance(mt, str) and mt:
                try:
                    t_ref = datetime.datetime.fromisoformat(mt.replace("Z", "+00:00"))
                    if t_ref.tzinfo is None:
                        t_ref = t_ref.replace(tzinfo=datetime.timezone.utc)
                except Exception:
                    t_ref = None
            if t_ref is None and isinstance(self._last_timestamped_dt, datetime.datetime):
                t_ref = self._last_timestamped_dt
            if t_ref is None and isinstance(self._last_received_utc, datetime.datetime):
                t_ref = self._last_received_utc
            if isinstance(t_ref, datetime.datetime) and (now_utc - t_ref).total_seconds() >= 300:
                self._attr_native_value = None
                attrs = dict(self._attr_extra_state_attributes or {})
                attrs["stale"] = True
                attrs["stale_threshold_seconds"] = 300
                self._attr_extra_state_attributes = attrs
                self._safe_write_ha_state()
        except Exception:
            pass

    def _safe_write_ha_state(self) -> None:
        try:
            import asyncio as _asyncio
            in_loop = False
            try:
                running = _asyncio.get_running_loop()
                in_loop = running is self.hass.loop
            except RuntimeError:
                in_loop = False
            if in_loop:
                self.async_write_ha_state()
            else:
                self.schedule_update_ha_state()
        except Exception:
            try:
                self.schedule_update_ha_state()
            except Exception:
                pass

    def _handle_coordinator_update(self) -> None:
        raw = self._extract_current()
        if raw is None:
            try:
                getLogger(__name__).debug(
                    "RaceLapCount: No payload on update at %s; keeping previous state",
                    dt_util.utcnow().isoformat(timespec="seconds"),
                )
            except Exception:
                pass
            self._safe_write_ha_state()
            return
        self._apply_payload(raw)
        self._safe_write_ha_state()
        


class F1DriverListSensor(F1BaseEntity, RestoreEntity, SensorEntity):
    """Live driver list sensor.

    - State: number of drivers in attributes
    - Attributes: drivers: [ { racing_number, tla, name, first_name, last_name, team, team_color, headshot_small, headshot_large, reference } ]
    - Behavior: restores last known state; logs only on change; respects consolidated drivers coordinator.
    """

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        self._attr_icon = "mdi:account-multiple"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize from coordinator (only if it has real driver data) or restore.
        #
        # LiveDriversCoordinator intentionally clears its consolidated state when
        # the live window ends to avoid briefly showing stale timing data at the
        # start of a new session. For `sensor.f1_driver_list` we *do* want to keep
        # the last known list for dashboards/UI, so we treat an empty coordinator
        # payload as "no update" and keep/restored state.
        updated = self._update_from_coordinator()
        if (not updated) and self._attr_native_value is None:
            last = await self.async_get_last_state()
            if last and last.state not in (None, "unknown", "unavailable"):
                try:
                    self._attr_native_value = int(last.state)
                except Exception:
                    self._attr_native_value = None
                try:
                    from logging import getLogger
                    attrs = dict(getattr(last, "attributes", {}) or {})
                    # Drop legacy key 'headshot' if present (top-level or nested per-driver)
                    attrs.pop("headshot", None)
                    drivers_attr = attrs.get("drivers")
                    if isinstance(drivers_attr, list):
                        for drv in drivers_attr:
                            if isinstance(drv, dict):
                                drv.pop("headshot", None)
                    self._attr_extra_state_attributes = attrs
                    getLogger(__name__).debug("DriverList: Restored last state -> %s", last.state)
                except Exception:
                    pass
        # If we have neither live data nor a restored state, try a one-time
        # bootstrap from Ergast/Jolpica standings (typically last completed season).
        if self._attr_native_value is None:
            try:
                boot = self._bootstrap_from_ergast()
                if boot:
                    from logging import getLogger
                    getLogger(__name__).info(
                        "DriverList: Bootstrapped from Ergast/Jolpica standings (no live feed / no restore-state yet)"
                    )
            except Exception:
                pass
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        updated = self._update_from_coordinator()
        if not updated:
            # No driver payload (common outside live windows): keep last value/attrs.
            return
        if prev_state == self._attr_native_value and prev_attrs == self._attr_extra_state_attributes:
            return
        try:
            from logging import getLogger
            getLogger(__name__).debug(
                "DriverList: Computed at %s -> count=%s",
                dt_util.utcnow().isoformat(timespec="seconds"),
                self._attr_native_value,
            )
        except Exception:
            pass
        # Rate limit writes to once per 60s
        try:
            import time as _time
            lw = getattr(self, "_last_write_ts", None)
            now = _time.time()
            if lw is None or (now - lw) >= 60.0:
                setattr(self, "_last_write_ts", now)
                self._safe_write_ha_state()
            else:
                # Schedule a delayed write at the 60s boundary if not already pending
                pending = getattr(self, "_pending_write", False)
                if not pending:
                    setattr(self, "_pending_write", True)
                    delay = max(0.0, 60.0 - (now - lw)) if lw is not None else 60.0
                    from homeassistant.helpers.event import async_call_later as _later
                    def _do_write(_):
                        try:
                            setattr(self, "_last_write_ts", _time.time())
                            self._safe_write_ha_state()
                        finally:
                            setattr(self, "_pending_write", False)
                    _later(self.hass, delay, _do_write)
        except Exception:
            self._safe_write_ha_state()

    def _update_from_coordinator(self) -> bool:
        data = self.coordinator.data or {}
        drivers = (data.get("drivers") or None) if isinstance(data, dict) else None
        if not isinstance(drivers, dict) or not drivers:
            return False
        # Build normalized list sorted by racing number (numeric if possible)
        items = []
        for rn, info in drivers.items():
            ident = (info.get("identity") or {}) if isinstance(info, dict) else {}
            try:
                team_color = ident.get("team_color")
                if isinstance(team_color, str) and team_color and not team_color.startswith("#"):
                    team_color = f"#{team_color}"
            except Exception:
                team_color = ident.get("team_color")
            items.append(
                {
                    "racing_number": ident.get("racing_number") or rn,
                    "tla": ident.get("tla"),
                    "name": ident.get("name"),
                    "first_name": ident.get("first_name"),
                    "last_name": ident.get("last_name"),
                    "team": ident.get("team"),
                    "team_color": team_color,
                    "headshot_small": ident.get("headshot_small") or ident.get("headshot"),
                    "headshot_large": ident.get("headshot_large") or ident.get("headshot"),
                    "reference": ident.get("reference"),
                }
            )
        def _rn_key(v):
            val = str(v.get("racing_number") or "")
            return (int(val) if val.isdigit() else 9999, val)
        items.sort(key=_rn_key)
        self._attr_extra_state_attributes = {"drivers": items}
        self._attr_native_value = len(items)
        return True

    def _bootstrap_from_ergast(self) -> bool:
        """Best-effort bootstrap driver list from the standings coordinator.

        This is used at season rollover (or first install) when live timing has
        no feed yet and there is no restored state available.
        """
        try:
            hass = getattr(self, "hass", None)
            if hass is None:
                return False
            reg = (hass.data.get(DOMAIN, {}) or {}).get(self._entry_id)
            if not isinstance(reg, dict):
                return False
            driver_coord = reg.get("driver_coordinator")
            data = getattr(driver_coord, "data", None) or {}
            standings = (
                (data.get("MRData") or {})
                .get("StandingsTable", {})
                .get("StandingsLists", [])
            )
            if not isinstance(standings, list) or not standings:
                return False
            ds = (standings[0] or {}).get("DriverStandings", [])
            if not isinstance(ds, list) or not ds:
                return False

            items: list[dict] = []
            for item in ds:
                if not isinstance(item, dict):
                    continue
                driver = item.get("Driver") or {}
                if not isinstance(driver, dict):
                    continue
                rn = str(driver.get("permanentNumber") or "").strip()
                if not rn:
                    continue
                tla = driver.get("code") or driver.get("driverId")
                first = driver.get("givenName")
                last = driver.get("familyName")
                full = None
                try:
                    parts = [p for p in (first, last) if p]
                    full = " ".join(parts) if parts else None
                except Exception:
                    full = None
                constructors = item.get("Constructors") or []
                team = None
                if isinstance(constructors, list) and constructors:
                    c0 = constructors[0]
                    if isinstance(c0, dict):
                        team = c0.get("name")

                items.append(
                    {
                        "racing_number": rn,
                        "tla": tla,
                        "name": full,
                        "first_name": first,
                        "last_name": last,
                        "team": team,
                        "team_color": None,
                        "headshot_small": None,
                        "headshot_large": None,
                        "reference": driver.get("url") or driver.get("driverId"),
                    }
                )

            if not items:
                return False

            def _rn_key(v):
                val = str(v.get("racing_number") or "")
                return (int(val) if val.isdigit() else 9999, val)

            items.sort(key=_rn_key)
            self._attr_extra_state_attributes = {
                "drivers": items,
                "source": "ergast",
            }
            self._attr_native_value = len(items)
            return True
        except Exception:
            return False

    @property
    def available(self) -> bool:
        """Keep this sensor available even without a live timing feed.

        Many dashboards are built around the driver list; showing it as
        `unavailable` breaks those UIs. We therefore keep the last known list and
        do not mirror live-feed availability here.
        """
        return True

    @property
    def state(self):
        return self._attr_native_value


class F1CurrentTyresSensor(F1BaseEntity, SensorEntity):
    """Live sensor exposing current tyre compound per car.

    - State: number of drivers exposed in the list.
    - Attributes: drivers: [
        {
          racing_number,
          compound, compound_short, compound_color,
          new, stint_laps
        }
      ]
    """

    # Simple mappings for UI-friendly representation
    _COMPOUND_SHORT = {
        "SOFT": "S",
        "MEDIUM": "M",
        "HARD": "H",
        "INTERMEDIATE": "I",
        "WET": "W",
    }

    _COMPOUND_COLOR = {
        # Pirelli standard colors (approximate)
        "SOFT": "#FF0000",        # red
        "MEDIUM": "#FFFF00",      # yellow
        "HARD": "#FFFFFF",        # white
        "INTERMEDIATE": "#00FF00",# green
        "WET": "#0000FF",         # blue
    }

    def __init__(self, coordinator, sensor_name, unique_id, entry_id, device_name):
        super().__init__(coordinator, sensor_name, unique_id, entry_id, device_name)
        # Icon for tyres; can be adjusted if a better one is found
        self._attr_icon = "mdi:tire"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {"drivers": []}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Initialize immediately from coordinator
        self._update_from_coordinator()
        # Subscribe to further updates
        removal = self.coordinator.async_add_listener(self._handle_coordinator_update)
        self.async_on_remove(removal)
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        prev_state = self._attr_native_value
        prev_attrs = self._attr_extra_state_attributes
        self._update_from_coordinator()
        if prev_state == self._attr_native_value and prev_attrs == self._attr_extra_state_attributes:
            return
        # For now, write on each effective change; live_drivers coordinator is already throttled.
        self._safe_write_ha_state()

    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data or {}
        drivers = (data.get("drivers") or {}) if isinstance(data, dict) else {}

        items: list[dict] = []

        for rn, info in drivers.items():
            if not isinstance(info, dict):
                continue
            ident = (info.get("identity") or {}) if isinstance(info, dict) else {}
            tyres = (info.get("tyres") or {}) if isinstance(info, dict) else {}

            compound = tyres.get("compound")
            stint_laps = tyres.get("stint_laps")
            is_new = tyres.get("new")

            # Derive short/colour codes
            comp_upper = str(compound).upper() if isinstance(compound, str) else None
            if comp_upper in self._COMPOUND_SHORT:
                compound_short = self._COMPOUND_SHORT[comp_upper]
                compound_color = self._COMPOUND_COLOR.get(comp_upper)
            else:
                compound_short = "?" if compound not in (None, "") else None
                compound_color = None

            items.append(
                {
                    "racing_number": ident.get("racing_number") or rn,
                    "compound": compound,
                    "compound_short": compound_short,
                    "compound_color": compound_color,
                    "new": is_new,
                    "stint_laps": stint_laps,
                }
            )

        def _rn_key(v):
            val = str(v.get("racing_number") or "")
            return (int(val) if val.isdigit() else 9999, val)

        # Stable ordering by car number
        items.sort(key=_rn_key)

        # State is the number of drivers we expose in the list
        self._attr_native_value = len(items)
        self._attr_extra_state_attributes = {"drivers": items}

    @property
    def state(self):
        return self._attr_native_value

