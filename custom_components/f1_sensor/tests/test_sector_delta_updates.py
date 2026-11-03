"""Regressions for split sector times and flags from Mexico qualifying (#971)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.f1_sensor.__init__ import LiveDriversCoordinator
from custom_components.f1_sensor.sensor import F1DriverPositionsSensor


def _make_coord(hass) -> LiveDriversCoordinator:
    return LiveDriversCoordinator(
        hass,
        SimpleNamespace(),
        delay_seconds=0,
        bus=None,
        config_entry=None,
        delay_controller=None,
        live_state=None,
    )


def _merge_sector(coord, rn: str, idx: int, sector: dict, **timing) -> None:
    coord._merge_timingdata({"Lines": {rn: {**timing, "Sectors": {str(idx): sector}}}})


class _SnapshotCoordinator(SimpleNamespace):
    def async_add_listener(self, _listener):
        return lambda: None


def _driver_attributes(hass, coord, rn: str) -> dict:
    sensor = F1DriverPositionsSensor(
        _SnapshotCoordinator(data=coord._state), "uid", "entry", "F1"
    )
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Qualifying", "Name": "Qualifying"}
    )
    sensor._update_from_coordinator(initial=True)
    return next(
        driver
        for driver in sensor._attr_extra_state_attributes["drivers"]
        if driver["racing_number"] == rn
    )


def _assert_best(driver: dict, idx: int, time: float, lap: int, part: int) -> None:
    name = f"sector_{idx + 1}"
    assert driver[f"best_{name}"] == pytest.approx(time)
    assert driver[f"best_{name}_lap"] == lap
    assert driver[f"best_{name}_session_part"] == part
    best = driver["sectors"]["personal_best"][name]
    assert best["time"] == pytest.approx(time)
    assert best["lap"] == lap
    assert best["session_part"] == part
    assert best["personal_fastest"] is True
    assert best["source"] == "personal_best"


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", [0, 1, 2], ids=["s1", "s2", "s3"])
async def test_split_personal_fastest_updates_best_and_keeps_inherited_flag(
    hass, idx
) -> None:
    """ANT Q2 values at 46:52.300, 48:19.077/.226 and 49:36.439."""
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 2})
    _merge_sector(
        coord,
        "12",
        idx,
        {"Value": "22.336", "OverallFastest": True, "PersonalFastest": True},
        NumberOfLaps=11,
    )
    _merge_sector(
        coord,
        "12",
        idx,
        {"Value": "21.707", "PersonalFastest": False},
        NumberOfLaps=12,
    )
    _merge_sector(coord, "12", idx, {"PersonalFastest": True})

    flagged = _driver_attributes(hass, coord, "12")
    _assert_best(flagged, idx, 21.707, flagged[f"sector_{idx + 1}_lap"], 2)

    _merge_sector(coord, "12", idx, {"Value": "19.759"}, NumberOfLaps=13)
    inherited = _driver_attributes(hass, coord, "12")
    _assert_best(inherited, idx, 19.759, inherited[f"sector_{idx + 1}_lap"], 2)
    assert inherited[f"sector_{idx + 1}_personal_fastest"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", [0, 1, 2], ids=["s1", "s2", "s3"])
async def test_fastest_flag_before_value_survives_empty_sector_delta(hass, idx) -> None:
    """ANT's 48:46.179 clear and 49:07.048 flag precede the faster time."""
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 2})
    _merge_sector(coord, "12", idx, {"Value": "22.336", "PersonalFastest": True})
    _merge_sector(coord, "12", idx, {"Value": "21.707", "PersonalFastest": False})
    _merge_sector(coord, "12", idx, {"Value": "", "PersonalFastest": False})
    _merge_sector(coord, "12", idx, {"PersonalFastest": True})
    # A flag before the next time must not reclassify a cleared old candidate.
    driver = _driver_attributes(hass, coord, "12")
    assert driver[f"best_sector_{idx + 1}"] == pytest.approx(22.336)

    _merge_sector(coord, "12", idx, {"Value": "19.759"}, NumberOfLaps=13)
    driver = _driver_attributes(hass, coord, "12")
    _assert_best(driver, idx, 19.759, driver[f"sector_{idx + 1}_lap"], 2)


@pytest.mark.asyncio
async def test_explicit_non_personal_faster_time_does_not_replace_best(hass) -> None:
    """Keep the feed's fastest marking instead of taking an unqualified minimum."""
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    _merge_sector(coord, "16", 2, {"Value": "22.336", "PersonalFastest": True})
    _merge_sector(coord, "16", 2, {"Value": "19.860", "PersonalFastest": False})
    _merge_sector(coord, "16", 2, {"OverallFastest": True})
    driver = _driver_attributes(hass, coord, "16")
    assert driver["best_sector_3"] == pytest.approx(22.336)


@pytest.mark.asyncio
async def test_previous_value_flag_promotes_leclerc_completed_sector(hass) -> None:
    """LEC Q1's Value and PreviousValue/flag are separate real feed frames."""
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    _merge_sector(coord, "16", 2, {"Value": "30.518", "PersonalFastest": True})
    _merge_sector(
        coord,
        "16",
        2,
        {"Value": "19.860", "PersonalFastest": False},
        NumberOfLaps=5,
        LastLapTime={"Value": "1:17.532", "PersonalFastest": True},
    )
    _merge_sector(coord, "16", 2, {"PreviousValue": "19.860", "PersonalFastest": True})

    driver = _driver_attributes(hass, coord, "16")
    _assert_best(driver, 2, 19.860, 5, 1)
    assert driver["sector_3_lap"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", [0, 1], ids=["s1_flag", "s2_flag"])
async def test_flag_only_message_keeps_other_current_sector_and_progress(
    hass, idx
) -> None:
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    coord._merge_timingdata(
        {
            "Lines": {
                "16": {
                    "NumberOfLaps": 4,
                    "Sectors": {
                        "0": {"Value": "27.000", "PersonalFastest": False},
                        "1": {"Value": "31.000", "PersonalFastest": False},
                    },
                }
            }
        }
    )
    before = _driver_attributes(hass, coord, "16")
    _merge_sector(coord, "16", idx, {"PersonalFastest": True})
    after = _driver_attributes(hass, coord, "16")

    assert after["sector_1"] == before["sector_1"]
    assert after["sector_2"] == before["sector_2"]
    assert after["sector_1_lap"] == before["sector_1_lap"]
    assert after["sector_2_lap"] == before["sector_2_lap"]
    assert after["sector_state"] == "s2_done"
    assert after["sector_current_lap"] == before["sector_current_lap"]
    _assert_best(after, idx, (27.0, 31.0)[idx], 5, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", [0, 1], ids=["s1_flag", "s2_flag"])
async def test_late_flag_after_s3_does_not_restore_cleared_current_sectors(
    hass, idx
) -> None:
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    _merge_sector(
        coord,
        "16",
        0,
        {"Value": "27.000", "PersonalFastest": False},
        NumberOfLaps=4,
    )
    _merge_sector(coord, "16", 1, {"Value": "31.000", "PersonalFastest": False})
    _merge_sector(coord, "16", 2, {"Value": "19.860", "PersonalFastest": False})
    _merge_sector(coord, "16", idx, {"PersonalFastest": True})

    driver = _driver_attributes(hass, coord, "16")
    _assert_best(driver, idx, (27.0, 31.0)[idx], 5, 1)
    assert driver["sector_1"] is None
    assert driver["sector_2"] is None
    assert driver["sector_3"] == pytest.approx(19.860)
    assert driver["sector_state"] == "lap_complete"
    assert driver["last_completed_sector"]["number"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_delta",
    [{"Value": ""}, {"Value": "invalid"}, {"Status": 2048}, {"Stopped": True}],
    ids=["empty_value", "invalid_value", "no_time_status", "stopped"],
)
async def test_invalidated_candidate_is_not_promoted_by_later_flag(
    hass, invalid_delta
) -> None:
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    _merge_sector(coord, "16", 2, {"Value": "22.336", "PersonalFastest": True})
    _merge_sector(coord, "16", 2, {"Value": "19.860", "PersonalFastest": False})
    _merge_sector(coord, "16", 2, invalid_delta)
    _merge_sector(coord, "16", 2, {"PersonalFastest": True})
    driver = _driver_attributes(hass, coord, "16")
    assert driver["best_sector_3"] == pytest.approx(22.336)

    # A new valid time need not repeat Status or the already true fastest flag.
    _merge_sector(coord, "16", 2, {"Value": "19.759"}, NumberOfLaps=5)
    driver = _driver_attributes(hass, coord, "16")
    _assert_best(driver, 2, 19.759, driver["sector_3_lap"], 1)


@pytest.mark.asyncio
async def test_late_flag_keeps_new_lap_and_pending_completed_sector(hass) -> None:
    """A best flag for an older S3 must not consume the next pending S3."""
    coord = _make_coord(hass)
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    _merge_sector(
        coord,
        "16",
        2,
        {"Value": "30.518", "PersonalFastest": False},
        NumberOfLaps=28,
    )
    # LastLapTime corrects S3's initial next-lap attribution from 29 to 28.
    coord._merge_timingdata(
        {"Lines": {"16": {"NumberOfLaps": 28, "LastLapTime": {"Value": "1:30.0"}}}}
    )
    _merge_sector(coord, "16", 0, {"Value": "27.000"})
    coord._merge_timingdata(
        {"Lines": {"16": {"NumberOfLaps": 29, "LastLapTime": {"Value": "1:29.0"}}}}
    )
    _merge_sector(coord, "16", 0, {"Value": "26.500"})
    _merge_sector(coord, "16", 2, {"PersonalFastest": True})

    driver = _driver_attributes(hass, coord, "16")
    assert driver["sector_1"] == pytest.approx(26.5)
    assert driver["sector_1_lap"] == 30
    assert driver["sector_3"] is None
    assert driver["sector_state"] == "s1_done"
    assert driver["sector_current_lap"] == 30
    _assert_best(driver, 2, 30.518, 28, 1)

    _merge_sector(coord, "16", 2, {"Value": "25.000", "PersonalFastest": False})
    driver = _driver_attributes(hass, coord, "16")
    assert driver["sector_3"] == pytest.approx(25.0)
    assert driver["sector_3_lap"] == 29


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reset", ["qualifying_part", "replay", "safety_car", "session"]
)
async def test_resets_do_not_revive_old_sector_from_flag_only_message(
    hass, reset
) -> None:
    coord = _make_coord(hass)
    coord._on_sessioninfo({"Key": 11400})
    coord._merge_timingdata({"Lines": {}, "SessionPart": 1})
    _merge_sector(coord, "16", 2, {"Value": "19.860", "PersonalFastest": False})
    if reset == "qualifying_part":
        coord._merge_timingdata({"Lines": {}, "SessionPart": 2})
    elif reset == "replay":
        coord.reset_for_replay()
    elif reset == "session":
        coord._on_sessioninfo({"Key": 11401})
    else:
        coord._on_trackstatus({"Status": "4"})
        coord._on_trackstatus({"Status": "1"})

    _merge_sector(coord, "16", 2, {"PersonalFastest": True})
    driver = _driver_attributes(hass, coord, "16")
    assert driver["sector_3"] is None
    assert driver["best_sector_3"] is None
    assert driver["sectors"]["personal_best"]["sector_3"]["time"] is None
    assert driver["sector_state"] == "awaiting_s1"
