"""Behavior matrix for the small live stream coordinators."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.f1_sensor import (
    RCM_OVERTAKE_DISABLED,
    RCM_OVERTAKE_ENABLED,
    RCM_STRAIGHT_DISABLED,
    RCM_STRAIGHT_LOW,
    RCM_STRAIGHT_NORMAL,
    ChampionshipPredictionCoordinator,
    LapCountCoordinator,
    LiveDriversCoordinator,
    LiveModeCoordinator,
    PitStopCoordinator,
    RaceControlCoordinator,
    SessionInfoCoordinator,
    SessionStatusCoordinator,
    TeamRadioCoordinator,
    TopThreeCoordinator,
    TrackStatusCoordinator,
    WeatherDataCoordinator,
    _reset_replay_sensitive_coordinator_state,
)
from custom_components.f1_sensor.const import LATEST_TRACK_STATUS


def _session_coord():
    return SimpleNamespace(
        data={},
        async_add_listener=lambda _callback: Mock(),
    )


class _Bus:
    def __init__(self, *, auth_enabled=True) -> None:
        self.auth_enabled = auth_enabled
        self.callbacks = {}
        self.removers = []

    def subscribe(self, stream, callback):
        self.callbacks[stream] = callback
        remover = Mock()
        self.removers.append(remover)
        return remover


def _bypass_config_entry_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        DataUpdateCoordinator,
        "async_config_entry_first_refresh",
        AsyncMock(),
    )


async def test_track_status_parsing_delivery_dedupe_and_live_state(
    hass, monkeypatch
) -> None:
    coordinator = TrackStatusCoordinator(hass, _session_coord())
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    assert coordinator._parse_message(None) is None
    assert coordinator._parse_message(
        {"M": [{"A": ["TrackStatus", {"Status": "2"}]}]}
    ) == {"Status": "2"}
    assert coordinator._parse_message({"R": {"TrackStatus": {"Status": "1"}}}) == {
        "Status": "1"
    }
    assert coordinator._parse_message({"M": [{"A": []}]}) is None

    coordinator._deliver({"Status": "1", "Message": "All clear"})
    assert coordinator.data_list == [{"Status": "1", "Message": "All clear"}]
    assert hass.data[LATEST_TRACK_STATUS]["Status"] == "1"
    coordinator._on_bus_message({"Status": "2", "Message": "Yellow"})
    await hass.async_block_till_done()
    assert coordinator._last_message["Status"] == "2"
    coordinator._on_bus_message({"Status": "2", "Message": "Yellow"})
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator.available is False
    assert coordinator.data_list == []
    coordinator._startup_cutoff = datetime.now(UTC) + timedelta(minutes=1)
    coordinator._on_bus_message({"Utc": datetime.now(UTC).isoformat(), "Status": "3"})
    assert coordinator._last_message is None
    coordinator._handle_live_state(True, "replay")
    assert coordinator._startup_cutoff is None


async def test_session_status_context_parsing_delivery_and_reset(
    hass, monkeypatch
) -> None:
    coordinator = SessionStatusCoordinator(hass, _session_coord())
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    assert coordinator._iter_series_items(None) == []
    assert coordinator._iter_series_items([{}, "bad"]) == [{}]
    assert coordinator._iter_series_items({"2": {"x": 2}, "1": {"x": 1}}) == [
        {"x": 1},
        {"x": 2},
    ]
    assert coordinator._is_qualifying_like_session({"Name": "Sprint Shootout"}) is True
    coordinator._on_session_info_context({"Type": "Qualifying"})
    coordinator._on_session_data_context(
        {"Series": {"0": {"QualifyingPart": "bad"}, "1": {"QualifyingPart": 2}}}
    )
    assert coordinator.qualifying_part == 2
    coordinator._on_bus_message({"Status": "Started"})
    assert coordinator._last_message == {"Status": "Started"}
    assert coordinator._parse_message(
        {"M": [{"A": ["SessionStatus", {"Status": "Finished"}]}]}
    ) == {"Status": "Finished"}
    assert coordinator._parse_message(
        {"R": {"SessionStatus": {"Status": "Inactive"}}}
    ) == {"Status": "Inactive"}
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator.qualifying_part is None
    assert coordinator.is_qualifying_like_session is False


async def test_top_three_full_snapshot_delta_delivery_and_reset(
    hass, monkeypatch
) -> None:
    coordinator = TopThreeCoordinator(hass, _session_coord())
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    coordinator._merge_topthree(
        {"Withheld": True, "Lines": [{"Tla": "NOR"}, None, {"Tla": "PIA"}]}
    )
    assert coordinator._state["withheld"] is True
    assert coordinator._state["lines"][1] is None
    coordinator._merge_topthree(
        {
            "Lines": {
                "0": {"DiffToLeader": "+0.000"},
                "2": {"Position": 2},
                "4": {"ignored": True},
                "bad": {},
                "1": "ignored",
            }
        }
    )
    assert coordinator._state["lines"][0]["Tla"] == "NOR"
    assert coordinator._state["lines"][2]["Position"] == 2
    coordinator._on_bus_message({"Lines": {"1": {"Tla": "VER"}}})
    assert coordinator._state["lines"][1]["Tla"] == "VER"
    coordinator._deliver()
    assert coordinator.data is coordinator._state
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator._state["lines"] == [None, None, None]
    coordinator._handle_live_state(True, "replay")
    assert coordinator._replay_mode is True


class _UnsortableSeries(dict):
    _calls = 0

    def keys(self):
        self._calls += 1
        if self._calls == 1:
            raise RuntimeError("keys")
        return super().keys()


class _BadUpdateDict(dict):
    def update(self, *_args, **_kwargs):
        raise RuntimeError("update")


async def test_status_coordinators_exact_error_and_subscription_paths(
    hass, monkeypatch
) -> None:
    _bypass_config_entry_gate(monkeypatch)
    delay_remove = Mock()
    live_remove = Mock()
    delay_controller = SimpleNamespace(add_listener=Mock(return_value=delay_remove))
    live_state = SimpleNamespace(add_listener=Mock(return_value=live_remove))
    bus = _Bus()
    track = TrackStatusCoordinator(
        hass,
        _session_coord(),
        delay_seconds=3,
        bus=bus,
        delay_controller=delay_controller,
        live_state=live_state,
    )
    assert track._async_update_data is not None
    track._on_bus_message("bad")
    track._startup_cutoff = datetime.now(UTC) - timedelta(seconds=1)
    track._on_bus_message({"Utc": datetime.now(UTC).replace(tzinfo=None).isoformat()})
    bad_loop = SimpleNamespace(call_later=Mock(side_effect=RuntimeError("timer")))
    original_hass = track.hass
    track.hass = SimpleNamespace(loop=bad_loop, data={})
    track._deliver = Mock()
    track._on_bus_message({"Status": "2"})
    track._deliver.assert_called_once()
    track.hass = original_hass
    await track.async_config_entry_first_refresh()
    assert set(bus.callbacks) == {"TrackStatus"}
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: True
    )
    track._deliver({"Status": "1"})
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    # The next assertions replace timer handles: cancel the real scheduled work first.
    for handle in track._deliver_handles:
        handle.cancel()
    track._deliver_handle = Mock()
    track._deliver_handles = [Mock(), Mock()]
    track._handle_live_state(True, "replay")
    assert track._deliver_handles == []
    track._deliver_handles = [Mock()]
    track._handle_live_state(True, "no-spoiler")
    await track.async_close()
    delay_remove.assert_called_once()
    live_remove.assert_called_once()

    status = SessionStatusCoordinator(hass, _session_coord(), bus=bus)
    assert status._iter_series_items(_UnsortableSeries({"x": {"ok": True}})) == [
        {"ok": True}
    ]
    status._on_session_info_context("bad")
    status._on_session_info_context({"Name": "Race"})
    assert status.is_qualifying_like_session is False
    status._on_session_data_context("bad")
    status._on_session_data_context({"Series": [{}, {"QualifyingPart": None}]})
    assert status._parse_message("bad") is None
    status._on_bus_message("bad")
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: True
    )
    status._deliver({"Status": "Started"})
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    status._handle_live_state(True, "no-spoiler")

    cleanup = Mock()
    status._context_unsubs = [cleanup]
    status._bus = SimpleNamespace(subscribe=Mock(side_effect=RuntimeError("subscribe")))
    await status.async_config_entry_first_refresh()
    assert status._context_unsubs == []
    cleanup.assert_called_once()
    await status.async_close()


async def test_top_three_exact_defensive_and_refresh_paths(hass, monkeypatch) -> None:
    _bypass_config_entry_gate(monkeypatch)
    coordinator = TopThreeCoordinator(hass, _session_coord())
    assert await coordinator._async_update_data() is coordinator._state
    coordinator._handle_live_state(True, "init")
    coordinator._handle_live_state(True, "no-spoiler")
    coordinator._merge_topthree("bad")
    coordinator._merge_topthree({"Lines": [{"Tla": "NOR"}]})
    assert coordinator._state["lines"] == [{"Tla": "NOR"}, None, None]
    coordinator._state["lines"][0] = _BadUpdateDict()
    coordinator._merge_topthree({"Lines": {"0": {"Tla": "VER"}}})
    monkeypatch.setattr(coordinator, "_merge_topthree", Mock(side_effect=RuntimeError))
    coordinator._on_bus_message({"Lines": []})
    coordinator._on_bus_message("bad")
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: True
    )
    coordinator._deliver()

    coordinator._bus = SimpleNamespace(
        subscribe=Mock(side_effect=RuntimeError("subscribe"))
    )
    await coordinator.async_config_entry_first_refresh()
    assert coordinator._unsub is None
    coordinator._bus = None
    coordinator.hass = SimpleNamespace(data=None)
    await coordinator.async_config_entry_first_refresh()


async def test_replay_reset_clears_every_coordinator_state(hass) -> None:
    session = _session_coord()
    weather = WeatherDataCoordinator(hass, session)
    weather._last_message = {"AirTemp": "20"}
    weather.data_list = [weather._last_message]

    race_control = RaceControlCoordinator(hass, session)
    race_handle = SimpleNamespace(cancel=lambda: None)
    race_control._deliver_handles = [race_handle]
    race_control._last_message = {"Message": "Yellow"}
    race_control._seen_ids_set.add("id")
    race_control._seen_ids_order.append("id")

    live_mode = LiveModeCoordinator(hass, race_control)
    live_mode._state = {"straight_mode": "disabled", "overtake_enabled": True}

    lap_count = LapCountCoordinator(hass, session)
    lap_count._last_message = {"CurrentLap": 2}
    lap_count.data_list = [lap_count._last_message]

    pit_stops = PitStopCoordinator(hass, session)
    pit_stops._by_car = {"4": [{"lap": 2}]}
    team_radio = TeamRadioCoordinator(hass, session)
    team_radio._state = {"latest": {"RacingNumber": "4"}, "history": [{}]}
    prediction = ChampionshipPredictionCoordinator(hass, session)
    prediction._drivers = {"4": {"points": 100}}

    live_drivers = LiveDriversCoordinator(hass, session)
    live_drivers._state["drivers"] = {"4": {"identity": {}}}

    track_status = TrackStatusCoordinator(hass, session)
    track_handle = SimpleNamespace(cancel=lambda: None)
    track_status._deliver_handle = track_handle
    track_status._deliver_handles = [track_handle]
    track_status._last_untimestamped_fingerprint = "old"
    hass.data[LATEST_TRACK_STATUS] = {"Status": "2"}

    session_status = SessionStatusCoordinator(hass, session)
    session_status.is_qualifying_like_session = True
    session_status.qualifying_part = 2
    session_status._last_message = {"Status": "Started"}

    top_three = TopThreeCoordinator(hass, session)
    top_three._state["lines"][0] = {"Tla": "NOR"}
    session_info = SessionInfoCoordinator(hass, session)
    session_info._last_message = {"Name": "Race"}

    for coordinator in (
        weather,
        race_control,
        live_mode,
        lap_count,
        pit_stops,
        team_radio,
        prediction,
        live_drivers,
        track_status,
        session_status,
        top_three,
        session_info,
    ):
        _reset_replay_sensitive_coordinator_state(coordinator)

    assert weather.data is None and weather.data_list == []
    assert race_control.data is None and race_control._seen_ids_set == set()
    assert live_mode.data is None
    assert lap_count.data is None and lap_count.data_list == []
    assert pit_stops._by_car == {}
    assert team_radio._state == {"latest": None, "history": []}
    assert prediction._drivers == {}
    assert live_drivers.data["drivers"] == {}
    assert track_status.data is None
    assert hass.data[LATEST_TRACK_STATUS] is None
    assert session_status.qualifying_part is None
    assert top_three.data["lines"] == [None, None, None]
    assert session_info.data is None


async def test_track_and_session_status_close_release_all_callbacks(hass) -> None:
    track = TrackStatusCoordinator(hass, _session_coord())
    track_unsub = Mock()
    track_handle = Mock()
    queued_handle = Mock()
    track_delay_unsub = Mock()
    track_live_unsub = Mock()
    track._unsub = track_unsub
    track._deliver_handle = track_handle
    track._deliver_handles = [queued_handle]
    track._delay_listener = track_delay_unsub
    track._live_state_unsub = track_live_unsub

    await track.async_close()

    track_unsub.assert_called_once()
    track_handle.cancel.assert_called_once()
    queued_handle.cancel.assert_called_once()
    track_delay_unsub.assert_called_once()
    track_live_unsub.assert_called_once()
    assert track._unsub is None
    assert track._deliver_handle is None

    status = SessionStatusCoordinator(hass, _session_coord())
    context_unsubs = [Mock(), Mock()]
    status_unsub = Mock()
    status_handle = Mock()
    status_delay_unsub = Mock()
    status_live_unsub = Mock()
    status._context_unsubs = context_unsubs
    status._unsub = status_unsub
    status._deliver_handle = status_handle
    status._delay_listener = status_delay_unsub
    status._live_state_unsub = status_live_unsub

    await status.async_close()

    assert all(unsub.called for unsub in context_unsubs)
    status_unsub.assert_called_once()
    status_handle.cancel.assert_called_once()
    status_delay_unsub.assert_called_once()
    status_live_unsub.assert_called_once()
    assert status._context_unsubs == []


async def test_session_info_parsing_delivery_and_live_reset(hass, monkeypatch) -> None:
    coordinator = SessionInfoCoordinator(hass, _session_coord())
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    assert coordinator._parse_message(None) is None
    assert coordinator._parse_message(
        {"M": [{"A": ["SessionInfo", {"Name": "Race"}]}]}
    ) == {"Name": "Race"}
    assert coordinator._parse_message({"R": {"SessionInfo": {"Name": "Sprint"}}}) == {
        "Name": "Sprint"
    }
    coordinator._on_bus_message({"Name": "Race", "Type": "Race"})
    assert coordinator.data_list[0]["Name"] == "Race"
    assert await coordinator._async_update_data() == {"Name": "Race", "Type": "Race"}
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator.data_list == []
    coordinator._handle_live_state(True, "no-spoiler")
    assert coordinator.available is False


async def test_weather_and_lap_count_full_bus_lifecycle(hass, monkeypatch) -> None:
    _bypass_config_entry_gate(monkeypatch)
    bus = _Bus()
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    weather = WeatherDataCoordinator(hass, _session_coord(), bus=bus)
    assert weather._has_timestamp({"Utc": "now"}) is True
    assert weather._has_timestamp({}) is False
    assert weather._should_skip_duplicate("bad") is False
    assert weather._parse_message(None) is None
    assert weather._parse_message(
        {"M": [{"A": ["WeatherData", {"AirTemp": "20"}]}]}
    ) == {"AirTemp": "20"}
    assert weather._parse_message({"R": {"WeatherData": {"AirTemp": "21"}}}) == {
        "AirTemp": "21"
    }
    weather._on_bus_message("bad")
    weather._on_bus_message({"AirTemp": "20", "TrackTemp": "30"})
    weather._on_bus_message({"AirTemp": "20", "TrackTemp": "30"})
    assert weather.data["AirTemp"] == "20"
    weather._on_bus_message({"AirTemp": "21", "TrackTemp": "30"})
    await weather.async_config_entry_first_refresh()
    assert "WeatherData" in bus.callbacks
    weather._handle_live_state(True, "init")
    weather._handle_live_state(True, "replay")
    weather._handle_live_state(False, "window-ended")
    assert weather.data is None
    await weather.async_close()

    lap_bus = _Bus()
    laps = LapCountCoordinator(hass, _session_coord(), bus=lap_bus)
    assert laps._parse_message(None) is None
    assert laps._parse_message({"M": [{"A": ["LapCount", {"CurrentLap": 2}]}]}) == {
        "CurrentLap": 2
    }
    assert laps._parse_message({"R": {"LapCount": {"CurrentLap": 3}}}) == {
        "CurrentLap": 3
    }
    laps._on_bus_message("bad")
    laps._on_bus_message({"CurrentLap": 4, "TotalLaps": 70})
    assert laps.data["CurrentLap"] == 4
    await laps.async_config_entry_first_refresh()
    assert "LapCount" in lap_bus.callbacks
    laps._handle_live_state(True, "no-spoiler")
    laps._handle_live_state(False, "window-ended")
    assert laps.data is None
    await laps.async_close()


async def test_race_control_delivery_dedupe_live_states_and_close(
    hass, monkeypatch
) -> None:
    _bypass_config_entry_gate(monkeypatch)
    bus = _Bus()
    log_store = SimpleNamespace(
        append=Mock(return_value={"sequence": 1}),
        clear_for_source_stop=Mock(),
        session_key="session",
    )
    coordinator = RaceControlCoordinator(
        hass, _session_coord(), bus=bus, log_store=log_store
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    assert coordinator._parse_message(None) is None
    assert coordinator._parse_message(
        {"M": [{"A": ["RaceControlMessages", {"Message": "Yellow"}]}]}
    ) == {"Message": "Yellow"}
    assert coordinator._parse_message(
        {"R": {"RaceControlMessages": {"Message": "Clear"}}}
    ) == {"Message": "Clear"}
    assert coordinator._extract_items("bad") == []
    assert coordinator._extract_items([{"Message": "one"}, "bad"]) == [
        {"Message": "one"}
    ]
    items = coordinator._extract_items(
        {"Messages": {"2": {"Message": "two"}, "1": {"Message": "one"}}}
    )
    assert [item["id"] for item in items] == [1, 2]

    old = {
        "Utc": "2020-01-01T00:00:00Z",
        "Message": "historical",
    }
    coordinator._startup_cutoff = datetime.now(UTC)
    coordinator._on_bus_message({"Messages": [old]})
    assert coordinator._seen_ids_set == set()
    coordinator._startup_cutoff = None
    coordinator._on_bus_message(
        {"Messages": [{"Utc": "2026-09-01T12:00:00Z", "Message": "Yellow"}]}
    )
    await hass.async_block_till_done()
    assert coordinator.data["Message"] == "Yellow"
    assert log_store.append.called
    seen = set(coordinator._seen_ids_set)
    coordinator._on_bus_message(
        {"Messages": [{"Utc": "2026-09-01T12:00:00Z", "Message": "Yellow"}]}
    )
    assert coordinator._seen_ids_set == seen

    await coordinator.async_config_entry_first_refresh()
    assert "RaceControlMessages" in bus.callbacks
    coordinator._delay = 10
    coordinator._schedule_deliver({"Message": "queued"})
    assert coordinator._deliver_handles
    coordinator._handle_live_state(True, "replay")
    assert coordinator._deliver_handles == []
    coordinator._handle_live_state(False, "window-ended")
    log_store.clear_for_source_stop.assert_called_once()
    coordinator._handle_live_state(True, "no-spoiler")
    await coordinator.async_close()


async def test_live_mode_all_messages_terminal_live_and_close(
    hass, monkeypatch
) -> None:
    _bypass_config_entry_gate(monkeypatch)
    race = _session_coord()
    race.data = None
    status = _session_coord()
    status.data = {"Status": "Started"}
    mode = LiveModeCoordinator(hass, race, status)
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    assert await mode._async_update_data() is None
    assert mode.session_is_terminal is False
    for message, key, value in (
        (RCM_OVERTAKE_ENABLED, "overtake_enabled", True),
        (RCM_OVERTAKE_DISABLED, "overtake_enabled", False),
        (RCM_STRAIGHT_NORMAL, "straight_mode", "normal_grip"),
        (RCM_STRAIGHT_LOW, "straight_mode", "low_grip"),
        (RCM_STRAIGHT_DISABLED, "straight_mode", "disabled"),
    ):
        race.data = {"Category": "Other", "Message": message}
        mode._on_race_control_update()
        assert mode._state[key] == value
    race.data = {"Category": "Flag", "Message": "ignored"}
    mode._on_race_control_update()
    race.data = {"Category": "Other", "Message": "ignored"}
    mode._on_race_control_update()
    status.data = {"Status": "Finished"}
    assert mode.session_is_terminal is True
    mode._handle_session_status_update()
    assert mode.data is None
    mode._handle_live_state(True, "init")
    mode._handle_live_state(True, "no-spoiler")
    mode._handle_live_state(False, "window-ended")
    await mode.async_config_entry_first_refresh()
    await mode.async_close()


async def test_team_radio_and_prediction_full_payload_lifecycle(
    hass, monkeypatch
) -> None:
    _bypass_config_entry_gate(monkeypatch)
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    session = _session_coord()
    bus = _Bus(auth_enabled=True)
    radio = TeamRadioCoordinator(hass, session, bus=bus, history_limit=2)
    assert radio._normalize_captures("bad") == []
    assert (
        radio._normalize_captures(
            {"Captures": [{"Utc": "1"}, "bad"], "_static_root": "root"}
        )[0]["_static_root"]
        == "root"
    )
    assert (
        radio._normalize_captures({"Captures": {"2": {"Utc": "2"}, "1": {"Utc": "1"}}})[
            0
        ]["Utc"]
        == "1"
    )
    assert (
        radio._normalize_captures({"Captures": {"Utc": "3", "Path": "clip"}})[0]["Utc"]
        == "3"
    )
    radio._on_bus_message("bad")
    radio._on_bus_message({"Utc": "1", "RacingNumber": "4", "Path": "a"})
    radio._on_bus_message({"Utc": "2", "RacingNumber": "81", "Path": "b"})
    radio._on_bus_message({"Utc": "3", "RacingNumber": "1", "Path": "c"})
    assert len(radio.data["history"]) == 2
    await radio.async_config_entry_first_refresh()
    assert "TeamRadio" in bus.callbacks
    radio._handle_live_state(True, "replay")
    radio._handle_live_state(False, "window-ended")
    assert radio.data["latest"] is None
    await radio.async_close()

    prediction = ChampionshipPredictionCoordinator(hass, session, bus=bus)
    prediction._on_driverlist(
        {
            "4": {"Tla": "NOR", "FullName": "Lando", "TeamName": "McLaren"},
            "bad": "ignored",
        }
    )
    prediction._on_bus_message(
        {
            "Drivers": {
                "4": {
                    "RacingNumber": "4",
                    "PredictedPosition": "1",
                    "PredictedPoints": "400.5",
                },
                "81": {"PredictedPosition": "2"},
                "bad": "ignored",
            },
            "Teams": {
                "mclaren": {"PredictedPosition": 1, "PredictedPoints": 700},
                "bad": "ignored",
            },
        }
    )
    assert prediction.data["predicted_driver_p1"]["tla"] == "NOR"
    assert prediction.data["predicted_team_p1"]["team_name"] == "mclaren"
    assert prediction._to_int("2.0") == 2
    assert prediction._to_int("bad") is None
    assert prediction._to_float("bad") is None
    await prediction.async_config_entry_first_refresh()
    assert {"ChampionshipPrediction", "DriverList"} <= set(bus.callbacks)
    prediction._handle_live_state(True, "replay")
    prediction._handle_live_state(False, "window-ended")
    assert prediction.data["drivers"] == {}
    await prediction.async_close()


async def test_pit_stop_identity_counts_deltas_fallback_and_bus_lifecycle(
    hass, monkeypatch
) -> None:
    """Exercise the live pit-stop fallbacks used when streams arrive piecemeal."""
    _bypass_config_entry_gate(monkeypatch)
    bus = _Bus()
    session = _session_coord()
    session.data = {"Meetings": []}
    drivers = SimpleNamespace(
        data={
            "drivers": {
                "44": {
                    "identity": {
                        "tla": "HAM",
                        "name": "Lewis Hamilton",
                        "team": "Ferrari",
                    },
                    "timing": {"pit_stops": "2"},
                    "lap_history": {
                        "laps": {
                            "7": "1:30.000",
                            "8": "1:31.000",
                            "9": "1:29.000",
                            "10": "1:45.000",
                            "11": "1:30.000",
                        }
                    },
                },
                "bad": "ignored",
                "0": {"timing": {"pit_stops": 1}},
            }
        },
        async_add_listener=lambda _callback: Mock(),
    )
    coordinator = PitStopCoordinator(
        hass,
        session,
        bus=bus,
        history_limit=1,
        drivers_coordinator=drivers,
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor._seed_driver_map_from_ergast",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )

    assert coordinator._parse_int(None) is None
    assert coordinator._parse_int("2.0") == 2
    assert coordinator._parse_int("bad") is None
    assert coordinator._parse_float(2) == 2.0
    assert coordinator._parse_float("") is None
    assert coordinator._normalize_racing_number("00") is None
    assert coordinator._normalize_racing_number("x") is None
    assert coordinator._bounded_text(None) is None
    assert coordinator._bounded_text("  ") is None
    assert coordinator._dedup_key("44", 1, "utc", 20.0, 2.0)[1] == "ts"

    coordinator._on_driverlist("bad")
    coordinator._on_driverlist(
        {
            "44": {"Tla": "HAM", "BroadcastName": "Hamilton"},
            "bad": "ignored",
            "0": {"Tla": "invalid"},
        }
    )
    coordinator._on_bus_pitstopseries("bad")
    coordinator._ingest_pitstopseries({})
    coordinator._ingest_pitstopseries(
        {
            "PitTimes": {
                "44": {
                    "0": "bad",
                    "1": {"PitStop": "bad"},
                    "2": {
                        "Timestamp": "one",
                        "PitStop": {
                            "Lap": 10,
                            "PitStopTime": 2.5,
                            "PitLaneTime": 20,
                        },
                    },
                    "3": {
                        "Timestamp": "two",
                        "PitStop": {
                            "Lap": 20,
                            "PitStopTime": 3,
                            "PitLaneTime": 21,
                        },
                    },
                },
                "81": "ignored",
            }
        }
    )
    assert len(coordinator._by_car["44"]) == 1
    coordinator._rebuild_pitstop_dedup()
    assert coordinator._dedup
    assert coordinator._refresh_pit_counts_from_coordinator() is True
    assert coordinator._refresh_pit_counts_from_coordinator() is False
    assert coordinator._refresh_driver_map_from_coordinator() is True
    assert coordinator._refresh_driver_map_from_coordinator() is False
    assert coordinator._get_identity("44")["tla"] == "HAM"
    assert coordinator._get_lap_history("44")["10"] == "1:45.000"
    assert coordinator._select_pit_lap_secs({"10": "bad"}, 9) is None
    assert coordinator._select_reference_lap_secs({}, 10) is None
    assert (
        coordinator._select_reference_lap_secs({"7": "1:30", "8": "1:32"}, 10) == 91.0
    )
    assert coordinator._compute_pit_delta("44", {}) is None

    coordinator._deliver()
    assert coordinator.data["cars"]["44"]["count"] == 2
    monkeypatch.setattr(coordinator, "_get_identity", Mock(side_effect=RuntimeError))
    coordinator._deliver()
    assert coordinator.data["total_stops"] == 2

    await coordinator.async_config_entry_first_refresh()
    assert {"DriverList", "PitStopSeries"} <= set(bus.callbacks)
    coordinator._handle_live_state(True, "init")
    coordinator._handle_live_state(True, "replay")
    assert coordinator.available is True
    coordinator._handle_live_state(True, "no-spoiler")
    coordinator._handle_live_state(False, "window-ended")
    assert coordinator.data["total_stops"] == 0
    await coordinator.async_close()


async def test_small_stream_first_refresh_subscriptions_and_close_matrix(
    hass, monkeypatch
) -> None:
    """Verify the remaining stream coordinators register and release listeners."""
    _bypass_config_entry_gate(monkeypatch)
    monkeypatch.setattr(
        "custom_components.f1_sensor._is_no_spoiler_blocked", lambda _coord: False
    )
    session = _session_coord()
    for coordinator, streams in (
        (TrackStatusCoordinator(hass, session, bus=_Bus()), {"TrackStatus"}),
        (SessionStatusCoordinator(hass, session, bus=_Bus()), {"SessionStatus"}),
        (TopThreeCoordinator(hass, session, bus=_Bus()), {"TopThree"}),
    ):
        await coordinator.async_config_entry_first_refresh()
        assert streams <= set(coordinator._bus.callbacks)
        coordinator.set_delay(1)
        coordinator.set_delay(0)
        await coordinator.async_close()
