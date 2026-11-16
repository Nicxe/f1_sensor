// Documentation for the current modular card registry. One record per module type.
export const cardsCatalog = [
  {
    "id": "overview",
    "title": "Overview",
    "category": "Planning",
    "description": "Show the meeting, circuit and countdown, with optional session status, lap progress and session rain risk.",
    "href": "/cards/cards-overview#overview-module",
    "availability": [
      "Schedule and session context"
    ],
    "keywords": "meeting countdown circuit lap flags session rain risk",
    "sources": [
      "next_race",
      "current_season",
      "current_session",
      "session_status",
      "replay_status",
      "replay_player",
      "race_lap_count",
      "track_status",
      "session_time_elapsed",
      "session_time_remaining",
      "race_time_to_three_hour_limit",
      "session_rain_risk"
    ],
    "nativeAnchor": true
  },
  {
    "id": "calendar",
    "title": "Schedule",
    "category": "Planning",
    "description": "Show weekend or season session times, and choose Home Assistant, circuit or UTC time.",
    "href": "/cards/cards-overview#calendar-module",
    "availability": [
      "Published schedule"
    ],
    "keywords": "calendar schedule timezone weekend season sessions",
    "sources": [
      "next_race",
      "current_season"
    ],
    "nativeAnchor": true
  },
  {
    "id": "weather",
    "title": "Weather",
    "category": "Planning",
    "description": "Compare current conditions, race-start forecasts, track measurements and the session's published rain risk.",
    "href": "/cards/cards-overview#weather-module",
    "availability": [
      "Forecasts and session measurements differ"
    ],
    "keywords": "weather forecast temperature rain wind track session rain risk race control",
    "sources": [
      "weather",
      "track_weather",
      "session_rain_risk"
    ],
    "nativeAnchor": true
  },
  {
    "id": "radar",
    "title": "Precipitation radar (beta)",
    "category": "Planning",
    "description": "Play recent precipitation maps and near-term forecasts around a circuit, using LibreWXR radar, satellite estimates and weather models.",
    "href": "/cards/cards-overview#radar-module",
    "availability": [
      "Current weather; ground radar coverage varies"
    ],
    "keywords": "radar precipitation rain satellite weather map animation librewxr beta",
    "sources": [
      "current_season",
      "next_race",
      "replay_status",
      "live_delay_number"
    ],
    "nativeAnchor": true
  },
  {
    "id": "timing",
    "title": "Timing",
    "category": "Session",
    "description": "Compare positions, laps and sectors, then open driver details or follow push laps.",
    "href": "/cards/timing",
    "availability": [
      "Session timing"
    ],
    "keywords": "positions laps qualifying practice push sectors gaps",
    "sources": [
      "driver_positions",
      "driver_list",
      "current_tyres",
      "current_session",
      "session_status",
      "starting_grid",
      "investigations"
    ]
  },
  {
    "id": "minisectors",
    "title": "Minisectors",
    "category": "Session",
    "description": "Follow provider status blocks within S1, S2 and S3; these are not individual minisector times.",
    "href": "/cards/minisectors",
    "availability": [
      "Provider status, not segment times"
    ],
    "keywords": "minisectors mini sectors segments colors purple green",
    "sources": [
      "driver_positions",
      "driver_list",
      "current_session",
      "session_status"
    ]
  },
  {
    "id": "race_control",
    "title": "Race Control",
    "category": "Session",
    "description": "Read official messages and filter by text, category or driver focus.",
    "href": "/cards/cards-overview#race-control-module",
    "availability": [
      "Published Race Control messages"
    ],
    "keywords": "race control flags yellow safety car stewards",
    "sources": [
      "race_control",
      "current_session"
    ],
    "nativeAnchor": true
  },
  {
    "id": "team_radio",
    "title": "Team Radio (experimental)",
    "category": "Session",
    "description": "Play published radio clips and optionally transcribe the latest clip manually.",
    "href": "/cards/team-radio",
    "availability": [
      "Experimental curated clips"
    ],
    "keywords": "team radio audio transcription speech driver",
    "sources": [
      "team_radio",
      "driver_list"
    ]
  },
  {
    "id": "tyres",
    "title": "Tyres",
    "category": "Session",
    "description": "Choose current tyres per driver or compound statistics, usage and best recorded runs.",
    "href": "/cards/cards-overview#tyres-module",
    "availability": [
      "Session tyre data"
    ],
    "keywords": "tyres tires compounds soft medium hard stints",
    "sources": [
      "current_tyres",
      "tyre_statistics",
      "driver_list"
    ],
    "nativeAnchor": true
  },
  {
    "id": "pit_stops",
    "title": "Pit stops",
    "category": "Session",
    "description": "Follow reported pit visits and available stop times while keeping counts and timed records separate.",
    "href": "/cards/pit-stops",
    "availability": [
      "Counts and detailed times differ"
    ],
    "keywords": "pit stops pitstops stationary lane loss delta",
    "sources": [
      "pitstops",
      "driver_list",
      "driver_positions",
      "f1tv_token_status"
    ]
  },
  {
    "id": "incidents",
    "title": "Incidents",
    "category": "Session",
    "description": "Show steward investigations, penalties or track-limit violations and summaries.",
    "href": "/cards/cards-overview#incidents-module",
    "availability": [
      "Investigations and track limits"
    ],
    "keywords": "incidents investigations penalties steward deleted laps track limits",
    "sources": [
      "investigations",
      "track_limits",
      "driver_list"
    ],
    "nativeAnchor": true
  },
  {
    "id": "results",
    "title": "Results",
    "category": "Results",
    "description": "Choose latest race, race or sprint classifications, or the current weekend starting grid.",
    "href": "/cards/cards-overview#results-module",
    "availability": [
      "Classification and grid sources differ"
    ],
    "keywords": "results classification starting grid sprint race points",
    "sources": [
      "last_race_results",
      "season_results",
      "sprint_results",
      "starting_grid"
    ],
    "nativeAnchor": true
  },
  {
    "id": "standings",
    "title": "Championship",
    "category": "Results",
    "description": "Follow driver or team standings, with prediction fields when the source supplies them.",
    "href": "/cards/cards-overview#standings-module",
    "availability": [
      "Prediction coverage is separate"
    ],
    "keywords": "championship standings drivers constructors teams prediction points",
    "sources": [
      "driver_standings",
      "constructor_standings",
      "championship_prediction_drivers",
      "championship_prediction_teams"
    ],
    "nativeAnchor": true
  },
  {
    "id": "archive",
    "title": "Historical archive",
    "category": "Results",
    "description": "Choose a year and event for published classifications, lap times or lap-position charts.",
    "href": "/features/historical-results#add-the-archive-module",
    "availability": [
      "Archive coverage varies"
    ],
    "keywords": "historical archive history year results laps qualifying charts",
    "sources": [
      "history"
    ]
  },
  {
    "id": "progression",
    "title": "Season progression",
    "category": "Results",
    "description": "Chart cumulative points, points per round or wins for selected drivers or teams.",
    "href": "/cards/cards-overview#progression-module",
    "availability": [
      "Season points and wins"
    ],
    "keywords": "season progression championship chart points cumulative wins",
    "sources": [
      "driver_points_progression",
      "constructor_points_progression"
    ],
    "nativeAnchor": true
  },
  {
    "id": "lap_chart",
    "title": "Lap history chart",
    "category": "Analysis",
    "description": "Compare observed lap times or changes between laps for selected drivers and lap ranges.",
    "href": "/cards/cards-overview#lap-chart-module",
    "availability": [
      "Observed session laps"
    ],
    "keywords": "lap history chart laps time pace change graph",
    "sources": [
      "driver_positions",
      "driver_list",
      "current_session"
    ],
    "nativeAnchor": true
  },
  {
    "id": "timeline",
    "title": "Session timeline",
    "category": "Analysis",
    "description": "Browse observed session events, filter categories and search their text.",
    "href": "/features/weekend-analysis#read-the-session-timeline",
    "availability": [
      "Observed events and interpretations"
    ],
    "keywords": "timeline events race control lap pit weather radio incidents",
    "sources": [
      "analysis"
    ]
  },
  {
    "id": "strategy",
    "title": "Strategy analysis",
    "category": "Analysis",
    "description": "Compare stints, compounds and teammate pace, with clean-sample filters and evidence scores.",
    "href": "/features/weekend-analysis#understand-strategy-estimates",
    "availability": [
      "Clean samples and estimates"
    ],
    "keywords": "strategy tyres tires stints degradation pace compounds crossover pit loss",
    "sources": [
      "analysis"
    ]
  },
  {
    "id": "battles",
    "title": "Battles and position changes",
    "category": "Analysis",
    "description": "Review active battles, their history or detected position exchanges and supporting evidence.",
    "href": "/features/weekend-analysis#understand-battles-and-position-changes",
    "availability": [
      "A position change does not prove an overtake"
    ],
    "keywords": "battles overtake overtakes position exchange gap history",
    "sources": [
      "analysis"
    ]
  },
  {
    "id": "map",
    "title": "Track map",
    "category": "Analysis",
    "description": "Place available car positions on a circuit map with labels and optional track markings.",
    "href": "/features/track-map#add-the-track-map-module",
    "availability": [
      "Usable position data required"
    ],
    "keywords": "track map car positions circuit corners sectors",
    "sources": [
      "track_map",
      "driver_positions",
      "current_session",
      "race_lap_count",
      "track_status"
    ]
  },
  {
    "id": "replay",
    "title": "Replay",
    "category": "Watch later",
    "description": "Select and load a completed session, then control playback, position and sync.",
    "href": "/features/replay-mode#using-replay-mode",
    "availability": [
      "Published session archive"
    ],
    "keywords": "replay playback watch later seek pause sync archive",
    "sources": [
      "replay_status",
      "replay_player",
      "replay_year_select",
      "replay_session_select",
      "replay_start_reference",
      "replay_load",
      "replay_refresh"
    ]
  },
  {
    "id": "telemetry",
    "title": "Replay telemetry",
    "category": "Watch later",
    "description": "Compare recorded telemetry for selected driver/lap pairs from a loaded replay.",
    "href": "/features/weekend-analysis#compare-replay-laps",
    "availability": [
      "Usable samples in a loaded replay"
    ],
    "keywords": "replay telemetry speed throttle brake gear rpm delta comparison",
    "sources": [
      "replay_status",
      "replay_player",
      "analysis/telemetry_catalog",
      "analysis/telemetry_compare"
    ]
  },
  {
    "id": "documents",
    "title": "FIA documents",
    "category": "Officials",
    "description": "List published FIA documents, search titles or show the latest document.",
    "href": "/cards/cards-overview#documents-module",
    "availability": [
      "Published documents"
    ],
    "keywords": "fia documents stewards official pdf decisions",
    "sources": [
      "fia_documents"
    ],
    "nativeAnchor": true
  }
];
