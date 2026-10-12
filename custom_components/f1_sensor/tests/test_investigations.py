from __future__ import annotations

from types import SimpleNamespace

from custom_components.f1_sensor.sensor import F1InvestigationsSensor


def _build_sensor() -> F1InvestigationsSensor:
    return F1InvestigationsSensor(
        SimpleNamespace(data_list=[], available=True),
        "test_investigations",
        "test_entry",
        "F1",
    )


def _process_messages(
    sensor: F1InvestigationsSensor, messages: list[dict[str, object]]
) -> None:
    for message in messages:
        sensor._process_message(message)
    sensor._update_attributes()


def test_stop_and_go_penalty_is_cleared_after_served() -> None:
    sensor = _build_sensor()

    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-03-08T04:01:21",
                "Lap": 1,
                "Category": "Other",
                "Message": "INCIDENT INVOLVING CAR 43 (COL) NOTED - STARTING PROCEDURE INFRINGEMENT",
            },
            {
                "Utc": "2026-03-08T04:03:53",
                "Lap": 1,
                "Category": "Other",
                "Message": "FIA STEWARDS: INCIDENT INVOLVING CAR 43 (COL) UNDER INVESTIGATION - STARTING PROCEDURE INFRINGEMENT",
            },
            {
                "Utc": "2026-03-08T04:14:16",
                "Lap": 8,
                "Category": "Other",
                "Message": "FIA STEWARDS: STOP-AND-GO PENALTY FOR CAR 43 (COL) - STARTING PROCEDURE INFRINGEMENT",
            },
            {
                "Utc": "2026-03-08T04:21:13",
                "Lap": 13,
                "Category": "Other",
                "Message": "FIA STEWARDS: PENALTY SERVED - STOP-AND-GO PENALTY FOR CAR 43 (COL) - STARTING PROCEDURE INFRINGEMENT",
            },
        ],
    )

    assert sensor.state == 0
    assert sensor.extra_state_attributes["under_investigation"] == []
    assert sensor.extra_state_attributes["penalties"] == []


def test_timed_stop_and_go_penalty_replaces_under_investigation() -> None:
    sensor = _build_sensor()

    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-03-08T04:01:21",
                "Lap": 1,
                "Category": "Other",
                "Message": "INCIDENT INVOLVING CAR 43 (COL) NOTED - STARTING PROCEDURE INFRINGEMENT",
            },
            {
                "Utc": "2026-03-08T04:03:53",
                "Lap": 1,
                "Category": "Other",
                "Message": "FIA STEWARDS: INCIDENT INVOLVING CAR 43 (COL) UNDER INVESTIGATION - STARTING PROCEDURE INFRINGEMENT",
            },
            {
                "Utc": "2026-03-08T04:14:16",
                "Lap": 8,
                "Category": "Other",
                "Message": "FIA STEWARDS: 10 SECOND STOP AND GO PENALTY FOR CAR 43 (COL) - STARTING PROCEDURE INFRINGEMENT",
            },
        ],
    )

    assert sensor.state == 1
    assert sensor.extra_state_attributes["under_investigation"] == []
    assert sensor.extra_state_attributes["penalties"] == [
        {
            "driver": "COL",
            "racing_number": "43",
            "penalty": "10 SECOND STOP AND GO PENALTY",
            "reason": None,
            "utc": "2026-03-08T04:14:16",
            "lap": 8,
        }
    ]


def test_after_session_investigation_replaces_noted_incident() -> None:
    sensor = _build_sensor()

    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-10-10T14:17:16",
                "Category": "Other",
                "Message": "TURN 5 INCIDENT INVOLVING CARS 27 (HUL) AND 55 (SAI) NOTED - IMPEDING (22:10:13)",
            },
            {
                "Utc": "2026-10-10T14:18:34",
                "Category": "Other",
                "Message": "FIA STEWARDS: TURN 5 INCIDENT INVOLVING CARS 27 (HUL) AND 55 (SAI) WILL BE INVESTIGATED AFTER THE SESSION - IMPEDING (22:10:13)",
            },
        ],
    )

    assert sensor.state == 1
    assert sensor.extra_state_attributes["noted"] == []
    assert sensor.extra_state_attributes["under_investigation"] == [
        {
            "utc": "2026-10-10T14:17:16",
            "lap": None,
            "drivers": ["HUL", "SAI"],
            "racing_numbers": ["27", "55"],
            "location": "TURN 5",
            "reason": "IMPEDING (22:10:13)",
            "after_race": True,
        }
    ]
