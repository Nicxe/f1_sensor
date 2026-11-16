from __future__ import annotations

from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize(
    ("issued", "served", "remaining", "uncertain"),
    [
        (
            ["5 SECOND TIME PENALTY", "10 SECOND TIME PENALTY"],
            "5 SECOND TIME PENALTY",
            ["10 SECOND TIME PENALTY"],
            False,
        ),
        (
            ["5 SECOND TIME PENALTY", "DRIVE THROUGH PENALTY"],
            "5 SECOND TIME PENALTY",
            ["DRIVE THROUGH PENALTY"],
            False,
        ),
        (
            ["10 SECOND STOP AND GO PENALTY", "10 SECOND TIME PENALTY"],
            "10 SECOND STOP/GO PENALTY",
            ["10 SECOND TIME PENALTY"],
            False,
        ),
        (
            ["5 SECOND TIME PENALTY", "5 SECOND TIME PENALTY"],
            "5 SECOND TIME PENALTY",
            ["5 SECOND TIME PENALTY"] * 2,
            True,
        ),
        (
            ["5 SECOND TIME PENALTY", "DRIVE THROUGH PENALTY"],
            None,
            ["5 SECOND TIME PENALTY", "DRIVE THROUGH PENALTY"],
            True,
        ),
        (
            ["5 SECOND TIME PENALTY", "REPRIMAND (DRIVING)"],
            None,
            ["REPRIMAND (DRIVING)"],
            False,
        ),
        (["5 SECOND TIME PENALTY"], None, [], False),
        (["REPRIMAND (DRIVING)"], None, ["REPRIMAND (DRIVING)"], False),
        (
            ["5 SECOND TIME PENALTY"],
            "5 SECONDS TIME PENALTY",
            ["5 SECOND TIME PENALTY"],
            True,
        ),
        (
            ["5 SECOND TIME PENALTY"],
            "10 SECOND TIME PENALTY",
            ["5 SECOND TIME PENALTY"],
            False,
        ),
    ],
)
def test_served_message_resolves_only_an_unambiguous_matching_penalty(
    issued, served, remaining, uncertain
) -> None:
    """A served notice must not silently erase other outstanding sanctions."""
    sensor = _build_sensor()
    messages = [
        {
            "Utc": f"2026-11-07T12:{index:02d}:00",
            "Lap": index + 1,
            "Message": f"FIA STEWARDS: {penalty} FOR CAR 63 (RUS) - INCIDENT {index}",
        }
        for index, penalty in enumerate(issued)
    ]
    messages.append(
        {
            "Utc": "2026-11-07T12:10:00",
            "Message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 1 (VER) - TRACK LIMITS",
        }
    )
    _process_messages(sensor, messages)
    other_driver = dict(sensor.extra_state_attributes["penalties"][-1])
    typed = f" - {served}" if served else ""
    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-11-07T12:20:00",
                "Message": f"FIA STEWARDS: PENALTY SERVED{typed} FOR CAR 63 (RUS)",
            }
        ],
    )

    russell = [
        item
        for item in sensor.extra_state_attributes["penalties"]
        if item["racing_number"] == "63"
    ]
    assert [item["penalty"] for item in russell] == remaining
    assert all(
        (item.get("service_status") == "unknown") == uncertain for item in russell
    )
    assert sensor.extra_state_attributes["penalties"][-1] == other_driver


def test_ambiguous_served_status_persists_until_a_specific_notice() -> None:
    sensor = _build_sensor()
    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-11-07T12:00:00",
                "Message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 63 (RUS)",
            },
            {
                "Utc": "2026-11-07T12:01:00",
                "Message": "FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 63 (RUS)",
            },
            {
                "Utc": "2026-11-07T12:05:00",
                "Message": "FIA STEWARDS: PENALTY SERVED FOR CAR 63 (RUS)",
            },
        ],
    )
    assert all(
        item["service_status"] == "unknown"
        for item in sensor.extra_state_attributes["penalties"]
    )
    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-11-07T12:06:00",
                "Message": "FIA STEWARDS: PENALTY SERVED - DRIVE THROUGH PENALTY FOR CAR 63 (RUS)",
            }
        ],
    )
    assert [
        (item["penalty"], item["service_status"])
        for item in sensor.extra_state_attributes["penalties"]
    ] == [("5 SECOND TIME PENALTY", "unknown")]


def test_served_reason_does_not_clear_a_mentioned_second_drivers_penalty() -> None:
    sensor = _build_sensor()
    _process_messages(
        sensor,
        [
            {
                "Utc": "2026-11-07T12:00:00",
                "Message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 63 (RUS)",
            },
            {
                "Utc": "2026-11-07T12:01:00",
                "Message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 1 (VER)",
            },
            {
                "Utc": "2026-11-07T12:05:00",
                "Message": "FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 63 (RUS) - COLLISION WITH CAR 1 (VER)",
            },
        ],
    )
    assert [
        (item["racing_number"], item.get("service_status"))
        for item in sensor.extra_state_attributes["penalties"]
    ] == [("1", None)]
