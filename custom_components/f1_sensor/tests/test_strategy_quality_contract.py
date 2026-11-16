"""Evidence and arithmetic contracts for matched strategy observations."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.f1_sensor.analysis import Phase4AnalysisStore, analyze_strategy
from custom_components.f1_sensor.history import LapAnalysisStore


class _Bus:
    def __init__(self):
        self.callbacks = {}

    def subscribe(self, stream, callback):
        self.callbacks.setdefault(stream, []).append(callback)
        return lambda: self.callbacks[stream].remove(callback)

    def emit(self, stream, payload):
        for callback in tuple(self.callbacks.get(stream, ())):
            callback(payload)


def _store():
    records = {}
    source = SimpleNamespace(
        get_lap=lambda driver, lap: records.get((driver, lap)),
        snapshot=lambda: {"laps": list(records.values())},
        reset_session=Mock(),
    )
    return Phase4AnalysisStore(
        _Bus(), source, source_provider=lambda: "replay"
    ), records


def _lap(driver, lap, duration=90.0, *, age=None, phase="green:1", stint=0):
    return {
        "driver_number": driver,
        "lap_number": lap,
        "lap_duration": duration,
        "stint_index": stint,
        "compound": "HARD",
        "quality": {
            "clean": True,
            "confidence": 1.0,
            "pace_suitability": "eligible",
            "timing_integrity": "consistent",
        },
        "strategy_context": {
            "tyre_age_at_lap_start": age,
            "green_phase_id": phase,
            "stint_index": stint,
            "stint_start_lap": 1,
            "stint_transition_observed": False,
            "compound": "HARD",
        },
    }


def _timing(store, records, lap, *, duration=90.0, driver=4, **extra):
    if lap > 0:
        records[(driver, lap)] = _lap(driver, lap, duration)
    store._on_timing_data({"Lines": {str(driver): {"NumberOfLaps": lap, **extra}}})


def _tyres(store, *, start=0, index=0, changed="0", driver=4):
    stint = {"Compound": "HARD", "TyresNotChanged": changed}
    if start is not None:
        stint["StartLaps"] = start
    store._on_timing_app({"Lines": {str(driver): {"Stints": {str(index): stint}}}})


@pytest.mark.parametrize("starting_age", [0, 3])
def test_strategy_context_anchors_known_start_and_preserves_historical_phase(
    starting_age,
):
    store, records = _store()
    _timing(store, records, 0)
    _tyres(store, start=starting_age)
    store._on_track_status({"Status": "1"})
    _timing(store, records, 1)
    _timing(store, records, 2)
    before = deepcopy(store._strategy_laps[(4, 2)]["strategy_context"])
    assert before["tyre_age_at_lap_start"] == starting_age + 1
    assert before["green_phase_id"] == "green:1"

    store._on_track_status({"Status": "4"})
    _timing(store, records, 3)
    assert store._strategy_laps[(4, 3)]["strategy_context"]["green_phase_id"] is None
    store._on_track_status({"Status": "1"})
    _timing(store, records, 4)
    assert (
        store._strategy_laps[(4, 4)]["strategy_context"]["green_phase_id"] == "green:2"
    )
    records[(4, 2)]["lap_duration"] = 89.5
    store._capture_strategy_laps()
    assert store._strategy_laps[(4, 2)]["strategy_context"] == before


@pytest.mark.parametrize("initial_lap,starting_age", [(12, 0), (0, None)])
def test_strategy_context_does_not_invent_start_or_zero_age(initial_lap, starting_age):
    store, records = _store()
    _timing(store, records, initial_lap)
    _tyres(store, start=starting_age)
    store._on_track_status({"Status": "1"})
    _timing(store, records, initial_lap + 1)
    context = store._strategy_laps[(4, initial_lap + 1)]["strategy_context"]
    assert context["tyre_age_at_lap_start"] is None
    assert context["stint_start_lap"] is None


def test_strategy_context_requires_observed_pit_transition_and_ignores_same_set_placeholder():
    store, records = _store()
    _timing(store, records, 0)
    _tyres(store)
    store._on_track_status({"Status": "1"})
    _timing(store, records, 1)
    _tyres(store, index=1, start=1, changed="1")
    store._on_timing_app({"Lines": {"4": {"Stints": {"0": {"TotalLaps": 2}}}}})
    _timing(store, records, 2, InPit=True)
    _tyres(store, index=2, start=3)
    _timing(store, records, 3, InPit=False)
    context = store._strategy_laps[(4, 3)]["strategy_context"]
    assert context["stint_start_lap"] == 3
    assert context["tyre_age_at_lap_start"] == 3
    assert context["stint_transition_observed"] is True
    assert context["previous_stint_index"] == 0


def test_strategy_context_replay_rebuild_is_deterministic_without_future_context():
    store, records = _store()

    def rebuild():
        _timing(store, records, 0)
        _tyres(store)
        store._on_track_status({"Status": "1"})
        _timing(store, records, 1)
        _timing(store, records, 2)
        return deepcopy(store._strategy_laps)

    expected = rebuild()
    store._on_track_status({"Status": "4"})
    _timing(store, records, 3)
    store.reset_for_replay()
    records.clear()
    assert rebuild() == expected


def test_strategy_context_observed_green_is_not_written_back_to_late_first_lap():
    store, records = _store()
    store._on_track_status({"Status": "1"})
    _timing(store, records, 15)
    assert store._strategy_laps[(4, 15)]["strategy_context"]["green_phase_id"] is None
    _timing(store, records, 16)
    assert (
        store._strategy_laps[(4, 16)]["strategy_context"]["green_phase_id"] == "green:1"
    )


def test_strategy_context_sparse_list_to_delta_preserves_known_same_set_age():
    store, records = _store()
    _timing(store, records, 0)
    store._on_timing_app(
        {
            "Lines": {
                "4": {
                    "Stints": [
                        {"Compound": "HARD", "StartLaps": 3, "TyresNotChanged": "0"}
                    ]
                }
            }
        }
    )
    _timing(store, records, 1)
    store._on_timing_app(
        {
            "Lines": {
                "4": {
                    "Stints": {
                        "0": {"TotalLaps": 4},
                        "1": {
                            "Compound": "UNKNOWN",
                            "TyresNotChanged": "1",
                            "StartLaps": 0,
                        },
                    }
                }
            }
        }
    )
    _timing(store, records, 2)
    context = store._strategy_laps[(4, 2)]["strategy_context"]
    assert context["tyre_age_at_lap_start"] == 4
    assert context["stint_index"] == 0
    assert context["stint_transition_observed"] is False


def test_strategy_context_late_start_age_does_not_invent_an_earlier_anchor():
    store, records = _store()
    _timing(store, records, 0)
    _tyres(store, start=None)
    _timing(store, records, 1)
    _tyres(store, start=0)
    _timing(store, records, 2)
    assert (
        store._strategy_laps[(4, 1)]["strategy_context"]["tyre_age_at_lap_start"]
        is None
    )
    assert (
        store._strategy_laps[(4, 2)]["strategy_context"]["tyre_age_at_lap_start"]
        is None
    )


_DRIVERS = {"4": {"team": "McLaren"}, "81": {"team": "McLaren"}}


def _pair_laps(first=(90, 91, 100), second=(91, 99, 101)):
    return [
        _lap(driver, lap, duration, age=lap - 1)
        for driver, times in ((4, first), (81, second))
        for lap, duration in enumerate(times, 1)
    ]


def _matched(laps):
    return analyze_strategy(laps, _DRIVERS)["teammate_comparisons"][0][
        "matched_comparison"
    ]


def test_strategy_matched_median_uses_explicit_pairs_not_independent_medians():
    laps = _pair_laps()
    unchanged = deepcopy(laps)
    result = _matched(laps)
    assert result["status"] == "ready"
    assert result["delta_seconds"] == -1
    assert result["faster_driver"] == 4
    assert result["lap_range"] == [1, 3]
    assert result["used_pairs"] == result["possible_pairs"] == 3
    assert [pair["delta_seconds"] for pair in result["pairs"]] == [-1, -8, -1]
    assert laps == unchanged
    assert _matched(laps) == result
    laps[1]["lap_duration"] = 100
    assert _matched(laps)["delta_seconds"] == -1
    assert _matched(laps)["pairs"][1]["delta_seconds"] == 1


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("tyre_age_at_lap_start", None, "unknown_tyre_age"),
        ("tyre_age_at_lap_start", 3, "tyre_age_difference"),
        ("compound", "SOFT", "compound_mismatch"),
        ("compound", None, "unknown_compound"),
        ("green_phase_id", None, "unknown_green_phase"),
        ("green_phase_id", "green:2", "different_green_phase"),
    ],
)
def test_strategy_matching_excludes_unlike_or_unknown_context(field, value, reason):
    laps = _pair_laps()
    laps[3]["strategy_context"][field] = value
    result = _matched(laps)
    assert result["used_pairs"] == 2
    assert result["excluded_reason_counts"] == {reason: 1}
    assert result["delta_seconds"] is None
    assert result["faster_driver"] is None


def test_strategy_matching_accepts_two_laps_age_difference_but_not_legacy_clean_alone():
    laps = _pair_laps()
    laps[3]["strategy_context"]["tyre_age_at_lap_start"] = 2
    assert _matched(laps)["used_pairs"] == 3
    for lap in laps:
        lap["quality"].pop("pace_suitability")
    result = _matched(laps)
    assert result["used_pairs"] == 0
    assert result["excluded_reason_counts"] == {"pace_not_eligible": 3}


def test_strategy_disjoint_periods_cannot_produce_matched_winner():
    laps = _pair_laps()
    for lap in laps[3:]:
        lap["lap_number"] += 10
    result = _matched(laps)
    assert result["possible_pairs"] == 6
    assert result["used_pairs"] == 0
    assert result["excluded_pairs"] == 6
    assert result["delta_seconds"] is None
    assert result["faster_driver"] is None


@pytest.mark.parametrize(
    "differences,median_value,q1,q3",
    [
        ([-1, 0, 1, 2, 3], 1, 0, 2),
        ([0, 1, 2, 3], 1.5, 0.75, 2.25),
        ([1, 1, 1, 1, 100], 1, 1, 1),
    ],
)
def test_strategy_quartiles_use_numeric_inclusive_interpolation(
    differences, median_value, q1, q3
):
    result = _matched(
        _pair_laps([90 + value for value in differences], [90] * len(differences))
    )
    assert result["delta_seconds"] == median_value
    assert result["q1_seconds"] == q1
    assert result["q3_seconds"] == q3


@pytest.mark.parametrize("count,expected", [(4, None), (5, 0.2)])
def test_strategy_trend_requires_five_eligible_laps_and_four_laps_age_span(
    count, expected
):
    laps = [_lap(4, n + 1, 90 + n * 0.2, age=n) for n in range(count)]
    trend = analyze_strategy(laps)["stints"][0]["lap_time_trend"]
    assert trend["seconds_per_lap"] == expected
    assert trend["sample_count"] == count
    assert trend["method"] == "ols_lap_time_by_tyre_age"
    if expected is not None:
        laps[-1]["lap_duration"] = 91.8
        assert (
            analyze_strategy(laps)["stints"][0]["lap_time_trend"]["seconds_per_lap"]
            == 0.4
        )


@pytest.mark.parametrize("ages", [[0, 0, 0, 0, 0], [None] * 5, [0, 1, 2, 3, 3]])
def test_strategy_trend_does_not_invent_age_variation(ages):
    laps = [_lap(4, n + 1, 90 + n, age=age) for n, age in enumerate(ages)]
    assert (
        analyze_strategy(laps)["stints"][0]["lap_time_trend"]["seconds_per_lap"] is None
    )


def test_strategy_trend_never_pools_separate_green_phases():
    laps = [
        _lap(4, n + 1, 90 + n * 0.2, age=n, phase="green:1" if n < 3 else "green:2")
        for n in range(6)
    ]
    trend = analyze_strategy(laps)["stints"][0]["lap_time_trend"]
    assert trend["seconds_per_lap"] is None
    assert trend["sample_count"] == 3
    assert trend["green_phase_id"] == "green:2"


@pytest.mark.parametrize(
    "baseline_count,duration,expected",
    [(2, 110, None), (3, 110, 20), (3, 90, 0), (3, 89, -1)],
)
def test_strategy_stint_change_estimate_requires_observed_transition_and_baseline(
    baseline_count, duration, expected
):
    laps = [_lap(4, n + 1, 90, age=n) for n in range(baseline_count)]
    stop_lap = baseline_count + 1
    changed = _lap(4, stop_lap, duration, age=0, stint=1)
    changed["strategy_context"].update(
        stint_start_lap=stop_lap, stint_transition_observed=True, previous_stint_index=0
    )
    changed["quality"]["pace_suitability"] = "excluded"
    laps.append(changed)
    estimate = analyze_strategy(laps)["stints"][-1]["stint_change_estimate"]
    assert estimate["seconds"] == expected
    assert estimate["baseline_laps"] == list(range(1, stop_lap))
    assert estimate["baseline_seconds"] == (90 if baseline_count >= 3 else None)
    changed["strategy_context"]["stint_transition_observed"] = False
    assert (
        analyze_strategy(laps)["stints"][-1]["stint_change_estimate"]["seconds"] is None
    )


def test_strategy_stint_change_late_first_observation_is_not_the_transition_lap():
    first = _lap(4, 10, 110, age=2, stint=1)
    first["strategy_context"].update(
        stint_start_lap=8, stint_transition_observed=True, previous_stint_index=0
    )
    result = analyze_strategy([first])["stints"][0]["stint_change_estimate"]
    assert result["seconds"] is None
    assert result["reason"] == "transition_lap_not_observed"


@pytest.mark.parametrize("integrity", [None, "invalid", "inconsistent", "incomplete"])
def test_strategy_stint_change_requires_consistent_transition_timing(integrity):
    laps = [_lap(4, n + 1, 90, age=n) for n in range(3)]
    changed = _lap(4, 4, 110, age=0, stint=1)
    changed["strategy_context"].update(
        stint_start_lap=4, stint_transition_observed=True, previous_stint_index=0
    )
    changed["quality"]["timing_integrity"] = integrity
    laps.append(changed)
    assert (
        analyze_strategy(laps)["stints"][-1]["stint_change_estimate"]["seconds"] is None
    )


def test_strategy_unknown_later_set_does_not_inherit_the_previous_tyre_age():
    store, records = _store()
    _timing(store, records, 0)
    _tyres(store)
    _timing(store, records, 1)
    store._on_timing_app({"Lines": {"4": {"Stints": {"1": {"Compound": "MEDIUM"}}}}})
    _timing(store, records, 2)
    assert (
        store._strategy_laps[(4, 2)]["strategy_context"]["tyre_age_at_lap_start"]
        is None
    )


def test_strategy_crossover_does_not_treat_unknown_stint_age_as_zero():
    laps = [
        _lap(driver, n + 1, base + n * slope, age=None)
        for driver, base, slope in [(4, 90, 1), (81, 92, 0.5)]
        for n in range(6)
    ]
    for lap in laps:
        lap["compound"] = "HARD" if lap["driver_number"] == 4 else "SOFT"
    assert analyze_strategy(laps)["compound_crossover_indications"] == []


def test_strategy_session_interruption_requires_new_observed_green_phase():
    store, records = _store()
    _timing(store, records, 0)
    _tyres(store)
    store._on_track_status({"Status": "1"})
    _timing(store, records, 1)
    store._on_session_status({"Status": "Aborted"})
    store._on_track_status({"Status": "1"})
    _timing(store, records, 2)
    store._on_session_status({"Status": "Started"})
    _timing(store, records, 3)
    assert store._strategy_laps[(4, 2)]["strategy_context"]["green_phase_id"] is None
    assert store._strategy_laps[(4, 3)]["strategy_context"]["green_phase_id"] is None
    store._on_track_status({"Status": "1"})
    _timing(store, records, 4)
    assert (
        store._strategy_laps[(4, 4)]["strategy_context"]["green_phase_id"] == "green:2"
    )
    assert (
        store._strategy_laps[(4, 1)]["strategy_context"]["green_phase_id"] == "green:1"
    )


def test_strategy_matching_counts_union_once_and_keeps_driver_order_and_ties():
    laps = _pair_laps(first=[90, 90, 90, 90], second=[90, 90, 90])
    result = _matched(list(reversed(laps)))
    assert result["drivers"] == [4, 81]
    assert result["possible_pairs"] == 4
    assert result["used_pairs"] == 3
    assert result["excluded_reason_counts"] == {"missing_driver_lap": 1}
    assert result["possible_pairs"] == result["used_pairs"] + result["excluded_pairs"]
    assert result["delta_seconds"] == 0
    assert result["faster_driver"] is None
    laps[0]["quality"]["pace_suitability"] = "uncertain"
    laps[0]["strategy_context"].update(
        compound=None, tyre_age_at_lap_start=None, green_phase_id=None
    )
    result = _matched(laps)
    assert result["excluded_reason_counts"] == {
        "missing_driver_lap": 1,
        "pace_not_eligible": 1,
    }
    assert sum(result["excluded_reason_counts"].values()) == result["excluded_pairs"]


def test_strategy_median_and_quartiles_keep_fractional_milliseconds_until_display():
    result = _matched(_pair_laps([90, 90.001, 90.002, 90.003], [90] * 4))
    assert result["delta_seconds"] == 0.0015
    assert result["q1_seconds"] == 0.00075
    assert result["q3_seconds"] == 0.00225
    assert result["faster_driver"] == 81


def test_strategy_trend_latest_observed_phase_with_no_eligible_laps_has_no_older_fallback():
    laps = [_lap(4, n + 1, 90 + n * 0.2, age=n) for n in range(5)]
    latest = _lap(4, 6, 100, age=5, phase="green:2")
    latest["quality"]["pace_suitability"] = "excluded"
    laps.append(latest)
    trend = analyze_strategy(laps)["stints"][0]["lap_time_trend"]
    assert trend["green_phase_id"] == "green:2"
    assert trend["sample_count"] == 0
    assert trend["seconds_per_lap"] is None


@pytest.mark.parametrize(
    "latest_count,excluded,expected",
    [(3, False, 20), (2, False, None), (3, True, None)],
)
def test_strategy_pit_baseline_uses_only_previous_stints_last_observed_green_phase(
    latest_count, excluded, expected
):
    laps = [_lap(4, n + 1, 80, age=n) for n in range(5)]
    for n in range(latest_count):
        lap = _lap(4, n + 6, 90, age=n + 5, phase="green:2")
        if excluded:
            lap["quality"]["pace_suitability"] = "excluded"
        laps.append(lap)
    transition_lap = latest_count + 6
    transition = _lap(4, transition_lap, 110, age=0, phase="green:2", stint=1)
    transition["strategy_context"].update(
        stint_start_lap=transition_lap,
        stint_transition_observed=True,
        previous_stint_index=0,
    )
    laps.append(transition)
    estimate = analyze_strategy(laps)["stints"][-1]["stint_change_estimate"]
    assert estimate["seconds"] == expected
    assert estimate["baseline_green_phase_id"] == "green:2"
    assert estimate["baseline_laps"] == (
        [] if excluded else list(range(6, transition_lap))
    )
    transition["quality"]["inferred"] = True
    assert (
        analyze_strategy(laps)["stints"][-1]["stint_change_estimate"]["seconds"] is None
    )


def test_strategy_shared_stream_quality_correction_recomputes_pairs_with_historical_context():
    bus = _Bus()
    history = LapAnalysisStore(bus, source_provider=lambda: "replay")
    strategy = Phase4AnalysisStore(bus, history, source_provider=lambda: "replay")
    bus.emit("SessionInfo", {"Key": 11, "Name": "Race", "Type": "Race"})
    bus.emit(
        "DriverList",
        {
            str(driver): {"RacingNumber": str(driver), "TeamName": "McLaren"}
            for driver in (4, 81)
        },
    )
    bus.emit("TrackStatus", {"Status": "1"})
    bus.emit(
        "TimingData",
        {"Lines": {str(driver): {"NumberOfLaps": 0} for driver in (4, 81)}},
    )
    bus.emit(
        "TimingAppData",
        {
            "Lines": {
                str(driver): {
                    "Stints": {
                        "0": {
                            "Compound": "HARD",
                            "StartLaps": 3,
                            "TyresNotChanged": "0",
                        }
                    }
                }
                for driver in (4, 81)
            }
        },
    )
    for lap in range(1, 4):
        lines = {}
        for driver, duration in ((4, 89 + lap), (81, 90 + lap)):
            lines[str(driver)] = {
                "NumberOfLaps": lap,
                "LastLapTime": {"Value": str(duration)},
                "Sectors": {
                    str(index): {"Value": f"{duration / 3:.3f}"} for index in range(3)
                },
            }
        bus.emit("TimingData", {"Lines": lines})
    before = strategy.snapshot()["strategy"]["teammate_comparisons"][0][
        "matched_comparison"
    ]
    assert before["used_pairs"] == 3
    assert before["delta_seconds"] == -1
    assert before["pairs"][0]["tyre_age_laps"] == [3, 3]
    bus.emit("TrackStatus", {"Status": "4"})
    bus.emit(
        "RaceControlMessages",
        {
            "Messages": {
                "1": {"Message": "CAR 4 LAP TIME 1:31.000 DELETED - TRACK LIMITS"}
            }
        },
    )
    corrected = strategy.snapshot()["strategy"]["teammate_comparisons"][0][
        "matched_comparison"
    ]
    assert corrected["used_pairs"] == 2
    assert corrected["delta_seconds"] is None
    assert corrected["excluded_reason_counts"] == {"pace_not_eligible": 1}
    bus.emit(
        "RaceControlMessages",
        {"Messages": {"2": {"Message": "CAR 4 LAP TIME 1:31.000 REINSTATED"}}},
    )
    assert (
        strategy.snapshot()["strategy"]["teammate_comparisons"][0]["matched_comparison"]
        == before
    )


def test_strategy_context_recovers_at_a_later_observed_change_after_late_join():
    store, records = _store()
    _timing(store, records, 12)
    _tyres(store, start=0)
    _timing(store, records, 13, InPit=True)
    _tyres(store, start=3, index=1)
    _timing(store, records, 14, InPit=False)
    context = store._strategy_laps[(4, 14)]["strategy_context"]
    assert context["stint_start_lap"] == 14
    assert context["tyre_age_at_lap_start"] == 3
    assert context["stint_transition_observed"] is True
    assert (
        store._strategy_laps[(4, 13)]["strategy_context"]["tyre_age_at_lap_start"]
        is None
    )


def test_strategy_context_intervening_unknown_set_cannot_point_back_to_an_older_baseline():
    store, records = _store()
    _timing(store, records, 0)
    _tyres(store)
    _timing(store, records, 1)
    store._on_timing_app({"Lines": {"4": {"Stints": {"1": {"Compound": "MEDIUM"}}}}})
    _timing(store, records, 2, InPit=True)
    _tyres(store, start=0, index=2)
    _timing(store, records, 3, InPit=False)
    context = store._strategy_laps[(4, 3)]["strategy_context"]
    assert context["stint_start_lap"] == 3
    assert context["previous_stint_index"] == 1
    assert context["tyre_age_at_lap_start"] == 0
