"""Behavior matrix for live session sensor state models."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.f1_sensor.const import DOMAIN, LATEST_TRACK_STATUS
from custom_components.f1_sensor.sensor import (
    F1CurrentSessionSensor,
    F1SessionStatusSensor,
    F1TopThreePositionSensor,
    F1TrackStatusSensor,
    F1TrackWeatherSensor,
    _hex_to_rgb,
    _map_session_status_payload,
)


def _coordinator(data=None, data_list=None):
    return SimpleNamespace(data=data, data_list=data_list, available=True)


def test_track_weather_extract_apply_and_clear() -> None:
    sensor = F1TrackWeatherSensor(
        _coordinator(data={"data": {"AirTemp": "22.5", "Humidity": "50"}}),
        "weather",
        "entry",
        "F1",
    )
    assert sensor._to_float(None) is None
    assert sensor._to_float("bad") is None
    assert sensor._extract_current()["AirTemp"] == "22.5"
    sensor._apply_payload(
        {
            "AirTemp": "22.5",
            "TrackTemp": "31",
            "Humidity": "50",
            "Pressure": "1001",
            "Rainfall": "0",
            "WindDirection": "180",
            "WindSpeed": "3.2",
        }
    )
    assert sensor._attr_native_value == 22.5
    assert sensor.extra_state_attributes["measurement_inferred"] is True
    sensor.coordinator.data = None
    sensor.coordinator.data_list = [{"TrackTemp": "30", "AirTemp": "21"}]
    assert sensor._extract_current()["AirTemp"] == "21"
    sensor._clear_state()
    assert sensor._attr_native_value is None


def test_track_status_extraction_terminal_and_clear(hass) -> None:
    sensor = F1TrackStatusSensor(
        _coordinator(data={"data": {"Status": "2"}}),
        "track_status",
        "entry",
        "F1",
    )
    sensor.hass = hass
    assert sensor._extract_current() == {"Status": "2"}
    assert sensor._normalize({"Status": "2"}) == "YELLOW"
    sensor._session_status_coordinator = SimpleNamespace(
        data={"Status": "Finished"},
        is_qualifying_like_session=True,
        qualifying_part=1,
    )
    assert sensor._session_is_terminal() is False
    sensor._session_status_coordinator.qualifying_part = 3
    assert sensor._session_is_terminal() is True
    sensor._clear_state()
    assert sensor._forced_unavailable is True
    assert sensor.extra_state_attributes == {}
    hass.data[LATEST_TRACK_STATUS] = {"Status": "1"}
    sensor.coordinator.data = None
    sensor.coordinator.data_list = []
    assert sensor._extract_current() == {"Status": "1"}


def test_top_three_state_normalization_and_withheld_paths() -> None:
    sensor = F1TopThreePositionSensor(_coordinator(data="bad"), "p3", "entry", "F1", 9)
    assert sensor._position_index == 2
    assert sensor._extract_state() is None
    sensor._update_from_coordinator(initial=True)
    assert sensor.extra_state_attributes["withheld"] is None
    assert sensor._normalize_color(None) is None
    assert sensor._normalize_color(" ") == ""
    assert sensor._normalize_color("#fff") == "#fff"
    assert sensor._normalize_color("ff8700") == "#ff8700"
    assert _hex_to_rgb(None) is None
    assert _hex_to_rgb("bad") is None
    assert _hex_to_rgb("zzzzzz") is None
    assert _hex_to_rgb("ff8700") == [255, 135, 0]

    sensor.coordinator.data = {"withheld": True, "lines": [], "last_update_ts": "t"}
    sensor._update_from_coordinator(initial=True)
    assert sensor._attr_native_value is None
    sensor.coordinator.data = {
        "withheld": False,
        "lines": [None, None, {"TLA": "PIA", "TeamColor": "ff8700"}],
        "last_update_ts": "t",
    }
    sensor._update_from_coordinator(initial=True)
    assert sensor._attr_native_value == "PIA"
    assert sensor.extra_state_attributes["team_color_rgb"] == [255, 135, 0]


def test_session_status_mapping_metadata_and_track_grip(hass) -> None:
    hass.data[LATEST_TRACK_STATUS] = {"Status": "1"}
    assert _map_session_status_payload(None, hass) is None
    assert _map_session_status_payload({"Status": "Started"}, hass) == "live"
    assert (
        _map_session_status_payload(
            {"Status": "Finished"}, hass, is_qualifying_like=True, qualifying_part=2
        )
        == "break"
    )
    assert _map_session_status_payload({"Status": "Finalised"}, hass) == "finalised"
    assert _map_session_status_payload({"Status": "Ends"}, hass) == "ended"
    assert (
        _map_session_status_payload({"Status": "Inactive", "Started": "Finished"}, hass)
        == "break"
    )
    assert (
        _map_session_status_payload({"Status": "Inactive", "Started": "Started"}, hass)
        == "live"
    )
    assert (
        _map_session_status_payload({"Status": "Aborted", "Started": "Started"}, hass)
        == "live"
    )
    assert _map_session_status_payload({"Status": "unknown"}, hass) == "pre"

    sensor = F1SessionStatusSensor(
        _coordinator(data={"data": {"Status": "Started"}}),
        "session_status",
        "entry",
        "F1",
    )
    sensor.hass = hass
    assert sensor._extract_current() == {"Status": "Started"}
    sensor._session_info_coordinator = SimpleNamespace(
        data={
            "Meeting": {
                "Name": "Test GP",
                "Location": "Test",
                "Country": {"Name": "Sweden"},
                "Circuit": {"ShortName": "Test Ring"},
            },
            "GmtOffset": "+02:00",
            "StartDate": "start",
            "EndDate": "end",
        }
    )
    assert sensor._extract_session_info()["meeting_country"] == "Sweden"
    sensor._race_control_coordinator = SimpleNamespace(
        data_list=[{"Text": "NORMAL GRIP CONDITIONS"}]
    )
    assert sensor._detect_track_grip() == "normal"
    sensor._race_control_coordinator.data_list.append(
        {"Message": "LOW GRIP CONDITIONS"}
    )
    assert sensor._detect_track_grip() == "low"
    sensor._clear_state()
    assert sensor._track_grip_state is None


def test_current_session_labels_status_and_metadata(hass) -> None:
    hass.data.setdefault(DOMAIN, {})["entry"] = {}
    sensor = F1CurrentSessionSensor(
        _coordinator(data={}), "current_session", "entry", "F1"
    )
    sensor.hass = hass
    labels = [
        ({"Type": "Practice", "Number": "2"}, "Practice 2"),
        ({"Type": "Practice", "Number": "bad", "Name": "Practice"}, "Practice"),
        ({"Type": "Qualifying", "Name": "Qualifying"}, "Qualifying"),
        (
            {"Type": "Qualifying", "Name": "Sprint Shootout"},
            "Sprint Qualifying",
        ),
        ({"Type": "Race", "Name": "Sprint"}, "Sprint"),
        ({"Type": "Race", "Name": "Race"}, "Race"),
        ({"Type": "Other", "Name": "Test"}, "Test"),
        ({}, None),
    ]
    for payload, expected in labels:
        assert sensor._resolve_label(payload)[0] == expected
    sensor._status_coordinator = SimpleNamespace(
        data={"Status": "Started"},
        is_qualifying_like_session=False,
        qualifying_part=None,
    )
    raw = {
        "Type": "Race",
        "Name": "Race",
        "Meeting": {
            "Key": 1,
            "Name": "Test GP",
            "Location": "Test",
            "Country": {"Name": "Sweden"},
            "Circuit": {"ShortName": "Test Ring"},
        },
        "StartDate": "2026-09-01T10:00:00Z",
        "EndDate": "2099-09-01T12:00:00Z",
    }
    sensor._apply_payload(raw)
    assert sensor._attr_native_value == "Race"
    assert sensor.extra_state_attributes["active"] is True
    sensor._status_coordinator.data = {"Status": "Finalised"}
    sensor._apply_payload(raw)
    assert sensor._attr_native_value is None
    assert sensor.extra_state_attributes["last_label"] == "Race"
    sensor._status_coordinator = SimpleNamespace(data="bad")
    assert sensor._live_status_payload() is None
    sensor._clear_state()
    assert sensor.extra_state_attributes == {}
