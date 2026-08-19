"""Declarative feature and live-stream dependency planning."""

from __future__ import annotations

from dataclasses import dataclass

from .signalr import AUTH_GATED_LIVE_STREAMS, PUBLIC_LIVE_STREAMS


@dataclass(frozen=True, slots=True)
class FeatureDependency:
    """Runtime dependencies for one user-facing feature."""

    coordinators: frozenset[str] = frozenset()
    streams: frozenset[str] = frozenset()


def _dependency(
    *streams: str,
    coordinators: tuple[str, ...] = (),
) -> FeatureDependency:
    return FeatureDependency(
        coordinators=frozenset(coordinators),
        streams=frozenset(streams),
    )


_DRIVER_STREAMS = (
    "DriverList",
    "TimingData",
    "TimingAppData",
    "LapCount",
    "SessionStatus",
    "LapHistory",
    "DriverRaceInfo",
    "TrackStatus",
)
_INCIDENT_STREAMS = (
    "DriverList",
    "SessionInfo",
    "SessionData",
    "SessionStatus",
    "TrackStatus",
    "RaceControlMessages",
    "TimingData",
    "CarData.z",
)


FEATURE_DEPENDENCIES: dict[str, FeatureDependency] = {
    "current_session": _dependency("SessionInfo", coordinators=("session_info",)),
    "track_weather": _dependency("WeatherData", coordinators=("weather_data",)),
    "race_lap_count": _dependency("LapCount", coordinators=("lap_count",)),
    "driver_list": _dependency(*_DRIVER_STREAMS, coordinators=("drivers",)),
    "current_tyres": _dependency(*_DRIVER_STREAMS, coordinators=("drivers",)),
    "tyre_statistics": _dependency(*_DRIVER_STREAMS, coordinators=("drivers",)),
    "driver_positions": _dependency(*_DRIVER_STREAMS, coordinators=("drivers",)),
    "track_status": _dependency("TrackStatus", coordinators=("track_status",)),
    "safety_car": _dependency("TrackStatus", coordinators=("track_status",)),
    "session_status": _dependency(
        "SessionStatus",
        "SessionInfo",
        "SessionData",
        coordinators=("session_status",),
    ),
    "session_time_remaining": _dependency(
        "ExtrapolatedClock",
        "Heartbeat",
        "SessionStatus",
        "SessionInfo",
        "SessionData",
        coordinators=("session_clock",),
    ),
    "session_time_elapsed": _dependency(
        "ExtrapolatedClock",
        "Heartbeat",
        "SessionStatus",
        "SessionInfo",
        "SessionData",
        coordinators=("session_clock",),
    ),
    "race_time_to_three_hour_limit": _dependency(
        "ExtrapolatedClock",
        "Heartbeat",
        "SessionStatus",
        "SessionInfo",
        "SessionData",
        coordinators=("session_clock",),
    ),
    "race_control": _dependency(
        "RaceControlMessages",
        "SessionInfo",
        "SessionStatus",
        coordinators=("race_control", "session_info", "session_status"),
    ),
    "track_limits": _dependency(
        "RaceControlMessages",
        "SessionInfo",
        "SessionStatus",
        coordinators=("race_control", "session_info", "session_status"),
    ),
    "investigations": _dependency(
        "RaceControlMessages",
        "SessionInfo",
        "SessionStatus",
        coordinators=("race_control", "session_info", "session_status"),
    ),
    "on_track_incident": _dependency(
        *_INCIDENT_STREAMS,
        coordinators=("incident",),
    ),
    "possible_on_track_incident": _dependency(
        *_INCIDENT_STREAMS,
        coordinators=("incident",),
    ),
    "formation_start": _dependency(
        "SessionInfo",
        "SessionStatus",
        "CarData.z",
        coordinators=("formation_start",),
    ),
    "top_three": _dependency("TopThree", coordinators=("top_three",)),
    "team_radio": _dependency("TeamRadio", coordinators=("team_radio",)),
    "pitstops": _dependency(
        "PitStopSeries",
        "DriverList",
        coordinators=("pitstops",),
    ),
    "championship_prediction": _dependency(
        "ChampionshipPrediction",
        "DriverList",
        coordinators=("championship_prediction",),
    ),
    "starting_grid": _dependency(
        "SessionInfo",
        "SessionStatus",
        "DriverList",
        "TimingData",
        "TimingAppData",
        coordinators=("starting_grid",),
    ),
    "overtake_mode": _dependency(
        "RaceControlMessages",
        "SessionStatus",
        "SessionInfo",
        "SessionData",
        coordinators=("live_mode", "race_control", "session_status"),
    ),
    "straight_mode": _dependency(
        "RaceControlMessages",
        "SessionStatus",
        "SessionInfo",
        "SessionData",
        coordinators=("live_mode", "race_control", "session_status"),
    ),
}

TRACK_MAP_STREAMS = frozenset({"SessionInfo", "DriverList", "Position.z"})


@dataclass(frozen=True, slots=True)
class FeaturePlan:
    """Resolved runtime plan for one config entry."""

    requested_features: frozenset[str]
    active_live_features: frozenset[str]
    coordinators: frozenset[str]
    requested_streams: frozenset[str]
    public_streams: frozenset[str]
    auth_streams: frozenset[str]
    stream_reasons: dict[str, tuple[str, ...]]
    live_required: bool

    def needs(self, coordinator: str) -> bool:
        """Return whether a coordinator belongs to this plan."""
        return coordinator in self.coordinators


def build_feature_plan(
    enabled_features: set[str] | frozenset[str],
    *,
    live_enabled: bool,
    development_mode: bool = False,
) -> FeaturePlan:
    """Build the exact coordinator and stream plan for enabled features."""
    requested_features = frozenset(enabled_features)
    live_allowed = live_enabled or development_mode
    active_live_features = frozenset(
        feature
        for feature in requested_features
        if live_allowed and feature in FEATURE_DEPENDENCIES
    )

    coordinators: set[str] = set()
    reasons: dict[str, set[str]] = {}
    for feature in sorted(active_live_features):
        dependency = FEATURE_DEPENDENCIES[feature]
        coordinators.update(dependency.coordinators)
        for stream in dependency.streams:
            reasons.setdefault(stream, set()).add(feature)

    if reasons:
        reasons.setdefault("Heartbeat", set()).add("live_transport_health")

    requested_streams = frozenset(reasons)
    public_streams = requested_streams & frozenset(PUBLIC_LIVE_STREAMS)
    auth_streams = requested_streams & frozenset(AUTH_GATED_LIVE_STREAMS)
    return FeaturePlan(
        requested_features=requested_features,
        active_live_features=active_live_features,
        coordinators=frozenset(coordinators),
        requested_streams=requested_streams,
        public_streams=public_streams,
        auth_streams=auth_streams,
        stream_reasons={
            stream: tuple(sorted(stream_reasons))
            for stream, stream_reasons in sorted(reasons.items())
        },
        live_required=bool(requested_streams),
    )
