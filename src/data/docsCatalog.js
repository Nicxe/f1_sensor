// Curated reference metadata. Keep page IDs and standard entity IDs aligned with their reference pages.
export const entityCatalog = [
  {
    "id": "championship-prediction-drivers",
    "title": "Championship Prediction (Drivers)",
    "href": "/entities/championship-prediction-drivers",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_championship_prediction_drivers"
    ],
    "description": "Drivers championship prediction (P1 and list) (Replay Mode or F1TV Auth live timing).",
    "availability": "F1TV Auth / replay",
    "scope": "live",
    "keywords": "Attribute Description predicted_driver_p1 drivers last_update Field racing_number tla points entry RacingNumber CurrentPosition PredictedPosition CurrentPoints PredictedPoints unknown",
    "related": [
      {
        "label": "Constructor championship prediction",
        "href": "/entities/championship-prediction-teams"
      },
      {
        "label": "Current driver standings",
        "href": "/entities/driver-standings"
      },
      {
        "label": "Account and live feed availability",
        "href": "/features/f1tv-auth"
      }
    ]
  },
  {
    "id": "championship-prediction-teams",
    "title": "Championship Prediction (Teams)",
    "href": "/entities/championship-prediction-teams",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_championship_prediction_teams"
    ],
    "description": "Constructors championship prediction (P1 and list) (Replay Mode or F1TV Auth live timing).",
    "availability": "F1TV Auth / replay",
    "scope": "live",
    "keywords": "Attribute Description predicted_team_p1 teams last_update Field team_key team_name points entry TeamKey TeamName CurrentPosition PredictedPosition CurrentPoints PredictedPoints unknown",
    "related": [
      {
        "label": "Driver championship prediction",
        "href": "/entities/championship-prediction-drivers"
      },
      {
        "label": "Current constructor standings",
        "href": "/entities/constructor-standings"
      },
      {
        "label": "Account and live feed availability",
        "href": "/features/f1tv-auth"
      }
    ]
  },
  {
    "id": "constructor-points-progression",
    "title": "Constructor Points Progression",
    "href": "/entities/constructor-points-progression",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_constructor_points_progression"
    ],
    "description": "Follow constructor championship points across race rounds.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season rounds constructors series Field round race_name date name constructorId points_by_round cumulative_points wins_by_round totals labels key data cumulative sensor.f1_constructor_points_progression { points, wins } series.series",
    "related": [
      {
        "label": "Driver points by round",
        "href": "/entities/driver-points-progression"
      },
      {
        "label": "Current constructor standings",
        "href": "/entities/constructor-standings"
      },
      {
        "label": "Season progression dashboard",
        "href": "/cards/modular"
      }
    ]
  },
  {
    "id": "constructor-standings",
    "title": "Constructor Standings",
    "href": "/entities/constructor-standings",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_constructor_standings"
    ],
    "description": "Current constructor standings.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season round constructor_standings sensor.f1_constructor_standings Constructor",
    "related": [
      {
        "label": "Driver standings",
        "href": "/entities/driver-standings"
      },
      {
        "label": "Constructor points by round",
        "href": "/entities/constructor-points-progression"
      }
    ]
  },
  {
    "id": "current-season",
    "title": "Current Season",
    "href": "/entities/current-season",
    "category": "Schedule and weather",
    "entityIds": [
      "sensor.f1_current_season"
    ],
    "description": "Full race schedule.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season races Field country_code country_flag_url circuit_map_url circuit_outline_url scheduled_laps sensor.f1_current_season Sprint",
    "related": [
      {
        "label": "Native calendar and calendar automations",
        "href": "/entities/season-calendar"
      },
      {
        "label": "Next race and session times",
        "href": "/entities/next-race"
      }
    ]
  },
  {
    "id": "current-session",
    "title": "Current Session",
    "href": "/entities/current-session",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_current_session"
    ],
    "description": "Identify the session currently being followed, such as practice, qualifying, or the race.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description type name number session_part meeting_key meeting_name meeting_location Location meeting_country Country circuit_short_name gmt_offset start end live_status active last_label live Practice 1 Practice 2 Practice 3 Qualifying Sprint Qualifying Sprint Race unknown unavailable Type Name SessionStatus Started Finished",
    "related": [
      {
        "label": "Session lifecycle",
        "href": "/entities/session-status"
      },
      {
        "label": "Session clock",
        "href": "/entities/session-time-remaining"
      }
    ]
  },
  {
    "id": "current-tyres",
    "title": "Current Tyres",
    "href": "/entities/current-tyres",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_current_tyres"
    ],
    "description": "See the tyre compound currently fitted to each driver’s car.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description drivers Field racing_number tla team_color team_color_rgb position compound compound_short compound_color compound_color_rgb new stint_laps list [54, 113, 198] [255, 0, 0]",
    "related": [
      {
        "label": "Tyre performance statistics",
        "href": "/entities/tyre-statistics"
      },
      {
        "label": "Weekend analysis and strategy",
        "href": "/features/weekend-analysis"
      }
    ]
  },
  {
    "id": "driver-list",
    "title": "Driver List",
    "href": "/entities/driver-list",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_driver_list"
    ],
    "description": "Look up drivers, team colors, and headshots for your dashboard.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description drivers Field racing_number tla name first_name last_name team team_color team_color_rgb headshot_small headshot_large reference [54, 113, 198]",
    "related": [
      {
        "label": "Follow your favorite driver",
        "href": "/features/favorite-driver"
      },
      {
        "label": "Current driver timing",
        "href": "/entities/driver-positions"
      }
    ]
  },
  {
    "id": "driver-points-progression",
    "title": "Driver Points Progression",
    "href": "/entities/driver-points-progression",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_driver_points_progression"
    ],
    "description": "Follow driver championship points across race rounds.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season rounds drivers series Field round race_name date name code driverId points_by_round cumulative_points wins_by_round totals labels key data cumulative sensor.f1_driver_points_progression { points, wins } series.series",
    "related": [
      {
        "label": "Constructor points by round",
        "href": "/entities/constructor-points-progression"
      },
      {
        "label": "Current driver standings",
        "href": "/entities/driver-standings"
      },
      {
        "label": "Season progression dashboard",
        "href": "/cards/modular"
      }
    ]
  },
  {
    "id": "driver-positions",
    "title": "Driver Positions",
    "href": "/entities/driver-positions",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_driver_positions"
    ],
    "description": "Driver positions and lap times.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description drivers total_laps fastest_lap current_qualifying_part Field racing_number tla name team team_color team_color_rgb grid_position current_position laps completed_laps best_lap_time best_lap_time_secs best_lap_time_source best_lap_lap best_lap_gap status gap_to_leader interval_to_position_ahead in_pit pit_out retired stopped fastest_lap_time fastest_lap_time_secs fastest_lap_lap sector_1 sector_2 sector_3 sector_1_lap sector_2_lap sector_3_lap sector_1_source sector_2_source sector_3_source sector_1_overall_fastest sector_1_personal_fastest sector_2_overall_fastest sector_2_personal_fastest sector_3_overall_fastest sector_3_personal_fastest best_sector_1 best_sector_2 best_sector_3 best_sector_1_lap best_sector_2_lap best_sector_3_lap best_sector_1_session_part best_sector_2_session_part best_sector_3_session_part sector_state sector_current_lap last_completed_sector sectors q1_time q1_knocked_out q1_position q2_time q2_knocked_out q2_position q3_time q3_knocked_out q3_position sensor.f1_driver_positions unknown null [54, 113, 198] {\"1\": \"1:32.456\", \"2\": \"1:31.789\"} official observed on_track pit_in out current personal_best false fastest_lap: false sector_*_lap sector_*_source current.sector_1 current.sector_2 current.sector_3 _knocked_out _position q1_knocked_out: true q2_knocked_out: true",
    "related": [
      {
        "label": "Favorite Driver sensor",
        "href": "/entities/favorite-driver"
      },
      {
        "label": "Current tyres",
        "href": "/entities/current-tyres"
      },
      {
        "label": "Starting Grid",
        "href": "/entities/starting-grid"
      }
    ]
  },
  {
    "id": "driver-standings",
    "title": "Driver Standings",
    "href": "/entities/driver-standings",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_driver_standings"
    ],
    "description": "Current driver championship standings.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season round driver_standings Field position positionText points wins Driver Constructors driverId permanentNumber code url givenName familyName dateOfBirth nationality Nationality constructorId name sensor.f1_driver_standings",
    "related": [
      {
        "label": "Constructor standings",
        "href": "/entities/constructor-standings"
      },
      {
        "label": "Driver points by round",
        "href": "/entities/driver-points-progression"
      },
      {
        "label": "Automatic card data and optional sensors",
        "href": "/features/card-data-and-sensors"
      }
    ]
  },
  {
    "id": "favorite-driver",
    "title": "Favorite Driver",
    "href": "/entities/favorite-driver",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_favorite_driver",
      "select.f1_favorite_driver"
    ],
    "description": "Live position and timing details for a driver selected in select.f1_favorite_driver.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description selected racing_number tla name team team_color team_color_rgb position grid_position gap_to_leader interval_to_position_ahead last_lap best_lap in_pit pit_out pit_stops retired stopped status_code compound stint_laps new_tyres select.f1_favorite_driver sensor.f1_favorite_driver #",
    "related": [
      {
        "label": "Choose and use your favorite driver",
        "href": "/features/favorite-driver"
      },
      {
        "label": "Drivers device triggers",
        "href": "/reference/device-triggers#drivers-device"
      },
      {
        "label": "Favorite Driver event payload",
        "href": "/entities/events#favorite-driver"
      }
    ]
  },
  {
    "id": "fia-decision-documents",
    "title": "FIA Decision Documents",
    "href": "/entities/fia-decision-documents",
    "category": "Officials and incidents",
    "entityIds": [
      "sensor.f1_fia_documents"
    ],
    "description": "FIA decisions and documents for the current weekend.",
    "availability": "FIA documents",
    "scope": "static",
    "keywords": "Attribute Description name url published documents race Field document_number season round race_name race_date race_time circuit_name locality country 0",
    "related": [
      {
        "label": "Investigations and pending penalties",
        "href": "/entities/investigations"
      },
      {
        "label": "Officials device triggers",
        "href": "/reference/device-triggers#officials-device"
      }
    ]
  },
  {
    "id": "formation-start",
    "title": "Formation Start",
    "href": "/entities/formation-start",
    "category": "Session and track",
    "entityIds": [
      "binary_sensor.f1_formation_start"
    ],
    "description": "Indicates when formation start procedure is ready (Replay Mode or F1TV Auth live timing).",
    "availability": "F1TV Auth / replay",
    "scope": "live",
    "keywords": "Attribute Description status scheduled_start formation_start delta_seconds source session_type session_name error on off",
    "related": [
      {
        "label": "Account and live feed availability",
        "href": "/features/f1tv-auth"
      },
      {
        "label": "Session device triggers",
        "href": "/reference/device-triggers#session-device"
      }
    ]
  },
  {
    "id": "investigations",
    "title": "Investigations",
    "href": "/entities/investigations",
    "category": "Officials and incidents",
    "entityIds": [
      "sensor.f1_investigations"
    ],
    "description": "Active steward investigations and pending penalties.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description noted under_investigation no_further_action penalties last_update Field utc lap drivers racing_numbers location reason after_race nfi_utc driver racing_number penalty sensor.f1_investigations",
    "related": [
      {
        "label": "Track limits violations",
        "href": "/entities/track-limits"
      },
      {
        "label": "Official FIA documents",
        "href": "/entities/fia-decision-documents"
      },
      {
        "label": "Official Race Control messages",
        "href": "/entities/race-control"
      }
    ]
  },
  {
    "id": "lap-position-progression",
    "title": "Lap Position Progression",
    "href": "/entities/lap-position-progression",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_lap_position_progression"
    ],
    "description": "Post-race lap position progression.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season source updated_at data_mode session_data_api websocket session_data_type sessions Field key type status reason round race_name date total_laps driver_count sensor.f1_lap_position_progression unsupported jolpica metadata f1_sensor/lap_position/session race:2026:1 sprint:2026:5 race sprint available jolpica_laps jolpica_sprint_results null hass.states",
    "related": [
      {
        "label": "Historical archive and lap position chart",
        "href": "/features/historical-results"
      },
      {
        "label": "Race classification",
        "href": "/entities/season-results"
      }
    ]
  },
  {
    "id": "last-race-results",
    "title": "Last Race Results",
    "href": "/entities/last-race-results",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_last_race_results"
    ],
    "description": "Most recent race results.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description round race_name race_url circuit_id circuit_name circuit_url circuit_lat Latitude circuit_long Longitude circuit_locality circuit_country Country circuit_timezone race_start_utc race_start race_start_local results sensor.f1_last_race_results unknown {number, grid, position, laps, time, points, status, driver{permanentNumber, code, givenName, familyName}, constructor{constructorId, name}} time",
    "related": [
      {
        "label": "All season results",
        "href": "/entities/season-results"
      },
      {
        "label": "Sprint classification",
        "href": "/entities/sprint-results"
      },
      {
        "label": "Browse historical results",
        "href": "/features/historical-results"
      }
    ]
  },
  {
    "id": "next-race-weather",
    "title": "Next Race Weather",
    "href": "/entities/next-race-weather",
    "category": "Schedule and weather",
    "entityIds": [
      "weather.f1_weather"
    ],
    "description": "Native current conditions and forecasts for the next race circuit.",
    "availability": "Forecasts",
    "scope": "static",
    "keywords": "Attribute Description temperature humidity cloud_coverage wind_speed wind_gust_speed wind_bearing visibility race_start race_forecast_available season round race_name circuit_id circuit_name circuit_locality circuit_country Country weather.f1_weather sunny cloudy rainy lightning-rainy sensor.f1_weather",
    "related": [
      {
        "label": "Compact forecast sensor",
        "href": "/entities/weather-summary"
      },
      {
        "label": "Live trackside measurements",
        "href": "/entities/track-weather"
      },
      {
        "label": "Dashboard modules",
        "href": "/cards/modular"
      }
    ]
  },
  {
    "id": "next-race",
    "title": "Next Race",
    "href": "/entities/next-race",
    "category": "Schedule and weather",
    "entityIds": [
      "sensor.f1_next_race"
    ],
    "description": "Next race info.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description season round race_name schedule_source race_start_estimated schedule_source_url scheduled_laps sprint_scheduled_laps race_url circuit_id circuit_name circuit_url circuit_lat Latitude circuit_long Longitude circuit_locality circuit_country Country country_code country_flag_url circuit_map_url circuit_outline_url circuit_timezone race_start_utc race_start race_start_local first_practice_start_utc first_practice_start first_practice_start_local second_practice_start_utc second_practice_start second_practice_start_local third_practice_start_utc third_practice_start third_practice_start_local qualifying_start_utc qualifying_start qualifying_start_local sprint_qualifying_start_utc sprint_qualifying_start sprint_qualifying_start_local sprint_start_utc sprint_start sprint_start_local sensor.f1_next_race unknown jolpica official_calendar_fallback true false null",
    "related": [
      {
        "label": "Choose the right schedule entity",
        "href": "/entities/season-calendar"
      },
      {
        "label": "Race week countdown",
        "href": "/entities/race-week"
      },
      {
        "label": "Your first dashboard",
        "href": "/getting-started/first-dashboard"
      }
    ]
  },
  {
    "id": "on-track-incident",
    "title": "On-track Incident",
    "href": "/entities/on-track-incident",
    "category": "Officials and incidents",
    "entityIds": [
      "binary_sensor.f1_on_track_incident"
    ],
    "description": "Confirmed likely stopped car or on-track incident is active.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description active_count highest_confidence latest_incident_id latest_driver_number latest_driver_tla latest_reason latest_phase session_type session_name data_quality binary_sensor.f1_on_track_incident on off unavailable medium high candidate confirmed updated cleared race sprint qualifying practice live replay stale bootstrap f1_sensor_incident",
    "related": [
      {
        "label": "Possible incidents and candidates",
        "href": "/entities/possible-on-track-incident"
      },
      {
        "label": "Incident detection behavior",
        "href": "/features/incident-detection"
      },
      {
        "label": "Incident notifications blueprint",
        "href": "/blueprints/incident-notifications"
      }
    ]
  },
  {
    "id": "overtake-mode",
    "title": "Overtake Mode",
    "href": "/entities/overtake-mode",
    "category": "Session and track",
    "entityIds": [
      "binary_sensor.f1_overtake_mode"
    ],
    "description": "Check whether track-wide overtake mode is enabled. This 2026 feature is experimental.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description straight_mode restored binary_sensor.f1_overtake_mode on off normal_grip low_grip disabled",
    "related": [
      {
        "label": "Straight mode permissions",
        "href": "/entities/straight-mode"
      },
      {
        "label": "Session device triggers",
        "href": "/reference/device-triggers#session-device"
      }
    ]
  },
  {
    "id": "pit-stops",
    "title": "Pit Stops",
    "href": "/entities/pit-stops",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_pitstops"
    ],
    "description": "Follow reported pit counts and available stop times for each car.",
    "availability": "F1TV Auth / replay",
    "scope": "live",
    "keywords": "Attribute Description cars last_update Field tla name team count stops lap timestamp pit_stop_time pit_lane_time pit_delta source sensor.f1_pitstops 0 unavailable PitStopSeries PitLaneTimeCollection count: 2 stops: [] null",
    "related": [
      {
        "label": "Weekend analysis and strategy",
        "href": "/features/weekend-analysis"
      },
      {
        "label": "Tyres currently fitted",
        "href": "/entities/current-tyres"
      },
      {
        "label": "Account and feed availability",
        "href": "/features/f1tv-auth"
      }
    ]
  },
  {
    "id": "possible-on-track-incident",
    "title": "Possible On-track Incident",
    "href": "/entities/possible-on-track-incident",
    "category": "Officials and incidents",
    "entityIds": [
      "binary_sensor.f1_possible_on_track_incident"
    ],
    "description": "Possible stopped car or on-track incident candidate is active.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description active_count highest_confidence latest_incident_id latest_driver_number latest_driver_tla latest_reason latest_phase session_type session_name data_quality binary_sensor.f1_possible_on_track_incident candidate binary_sensor.f1_on_track_incident on confirmed updated off unavailable low medium high cleared race sprint qualifying practice live replay stale bootstrap",
    "related": [
      {
        "label": "Confirmed incident indicator",
        "href": "/entities/on-track-incident"
      },
      {
        "label": "Incident event phases and confidence",
        "href": "/entities/events#on-track-incident"
      },
      {
        "label": "Conservative notification defaults",
        "href": "/blueprints/incident-notifications"
      }
    ]
  },
  {
    "id": "race-control",
    "title": "Race Control",
    "href": "/entities/race-control",
    "category": "Officials and incidents",
    "entityIds": [
      "sensor.f1_race_control"
    ],
    "description": "Race Control messages feed (flags, incidents, key updates).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description utc received_at category flag scope sector car_number message event_id sequence history raw_message unknown",
    "related": [
      {
        "label": "React to every Race Control message",
        "href": "/entities/events#race-control"
      },
      {
        "label": "Race Control notifications blueprint",
        "href": "/blueprints/race-control-notifications"
      },
      {
        "label": "Investigations and penalties",
        "href": "/entities/investigations"
      }
    ]
  },
  {
    "id": "race-lap",
    "title": "Race Lap",
    "href": "/entities/race-lap",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_race_lap_count"
    ],
    "description": "Current race lap number.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description total_laps unknown",
    "related": [
      {
        "label": "Driver timing and completed laps",
        "href": "/entities/driver-positions"
      },
      {
        "label": "Session clock and race progress",
        "href": "/entities/session-time-remaining"
      }
    ]
  },
  {
    "id": "race-three-hour-limit",
    "title": "Race Three Hour Limit",
    "href": "/entities/race-three-hour-limit",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_race_time_to_three_hour_limit"
    ],
    "description": "Time remaining until the FIA 3-hour race duration cap (beta).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description session_type session_name session_part session_status clock_phase clock_running source_quality session_start_utc reference_utc last_server_utc value_seconds formatted_hms race_start_utc race_three_hour_cap_utc sensor.f1_race_time_to_three_hour_limit H:MM:SS 2:14:30 unavailable idle running paused overtime finished",
    "related": [
      {
        "label": "Elapsed session clock",
        "href": "/entities/session-time-elapsed"
      },
      {
        "label": "Session time remaining",
        "href": "/entities/session-time-remaining"
      },
      {
        "label": "Race lap progress",
        "href": "/entities/race-lap"
      }
    ]
  },
  {
    "id": "race-week",
    "title": "Race Week",
    "href": "/entities/race-week",
    "category": "Schedule and weather",
    "entityIds": [
      "binary_sensor.f1_race_week"
    ],
    "description": "on during race week.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description days_until_next_race next_race_name schedule_source race_start_estimated schedule_source_url binary_sensor.f1_race_week on off jolpica official_calendar_fallback null true false",
    "related": [
      {
        "label": "Next race and estimated start times",
        "href": "/entities/next-race"
      },
      {
        "label": "Device triggers for race week",
        "href": "/reference/device-triggers#race-device"
      }
    ]
  },
  {
    "id": "safety-car",
    "title": "Safety Car",
    "href": "/entities/safety-car",
    "category": "Session and track",
    "entityIds": [
      "binary_sensor.f1_safety_car"
    ],
    "description": "Safety Car (SC) or Virtual Safety Car (VSC) is active.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description track_status on SC VSC off CLEAR YELLOW RED",
    "related": [
      {
        "label": "Track status and flags",
        "href": "/entities/track-status"
      },
      {
        "label": "Make lights follow track flags",
        "href": "/blueprints/track-status-light"
      },
      {
        "label": "Session device triggers",
        "href": "/reference/device-triggers#session-device"
      }
    ]
  },
  {
    "id": "season-calendar",
    "title": "Season Calendar",
    "href": "/entities/season-calendar",
    "category": "Schedule and weather",
    "entityIds": [
      "calendar.f1_season_calendar"
    ],
    "description": "Full season calendar with all sessions.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Field summary description location start end Session Qualifying Sprint Race calendar.f1_season_calendar on off sensor.f1_current_season",
    "related": [
      {
        "label": "Season data for templates",
        "href": "/entities/current-season"
      },
      {
        "label": "Next race timestamps",
        "href": "/entities/next-race"
      },
      {
        "label": "Automation recipes",
        "href": "/automation"
      }
    ]
  },
  {
    "id": "season-results",
    "title": "Season Results",
    "href": "/entities/season-results",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_season_results"
    ],
    "description": "All season race results.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description races sensor.f1_season_results {round, race_name, results:[...]} grid recorder:",
    "related": [
      {
        "label": "Most recent race",
        "href": "/entities/last-race-results"
      },
      {
        "label": "Sprint classification",
        "href": "/entities/sprint-results"
      },
      {
        "label": "Historical archive",
        "href": "/features/historical-results"
      }
    ]
  },
  {
    "id": "session-rain-risk",
    "title": "Session Rain Risk",
    "href": "/entities/session-rain-risk",
    "category": "Schedule and weather",
    "entityIds": [
      "sensor.f1_session_rain_risk"
    ],
    "description": "The rain-risk percentage published by Race Control for the current session.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "rain risk percentage probability session_key meeting_key session_name utc message source race_control practice qualifying sprint forecast unknown unavailable 0 100",
    "related": [
      {
        "label": "Original Race Control messages",
        "href": "/entities/race-control"
      },
      {
        "label": "Track weather observations",
        "href": "/entities/track-weather"
      },
      {
        "label": "Weather provider forecast",
        "href": "/entities/weather-summary"
      }
    ]
  },
  {
    "id": "session-status",
    "title": "Session Status",
    "href": "/entities/session-status",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_session_status"
    ],
    "description": "Current session phase.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description meeting_name meeting_location meeting_country circuit_short_name gmt_offset start end track_grip pre live suspended break finished finalised ended pre → live → suspended ↔ live → finished → finalised → ended",
    "related": [
      {
        "label": "Current session label",
        "href": "/entities/current-session"
      },
      {
        "label": "Session phases explained",
        "href": "/reference/values#session-status"
      },
      {
        "label": "Session device triggers",
        "href": "/reference/device-triggers#session-device"
      }
    ]
  },
  {
    "id": "session-time-elapsed",
    "title": "Session Time Elapsed",
    "href": "/entities/session-time-elapsed",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_session_time_elapsed"
    ],
    "description": "Time elapsed in the current session (beta).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description session_type session_name session_part session_status clock_phase clock_running source_quality session_start_utc reference_utc last_server_utc value_seconds formatted_hms clock_total_s clock_remaining_s Value official official_no_heartbeat sessiondata_fallback unavailable sensor.f1_session_time_elapsed H:MM:SS 0:23:45 idle running paused overtime finished",
    "related": [
      {
        "label": "Time remaining",
        "href": "/entities/session-time-remaining"
      },
      {
        "label": "Race three-hour limit",
        "href": "/entities/race-three-hour-limit"
      },
      {
        "label": "Race lap progress",
        "href": "/entities/race-lap"
      }
    ]
  },
  {
    "id": "session-time-remaining",
    "title": "Session Time Remaining",
    "href": "/entities/session-time-remaining",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_session_time_remaining"
    ],
    "description": "Time remaining in the current session (beta).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description session_type session_name session_part session_status clock_phase clock_running source_quality session_start_utc reference_utc last_server_utc value_seconds formatted_hms clock_total_s sensor.f1_session_time_remaining H:MM:SS 0:36:15 unavailable idle running paused overtime finished sensor.f1_race_lap_count",
    "related": [
      {
        "label": "Elapsed time and source quality",
        "href": "/entities/session-time-elapsed"
      },
      {
        "label": "Race three-hour limit",
        "href": "/entities/race-three-hour-limit"
      },
      {
        "label": "Race lap progress",
        "href": "/entities/race-lap"
      }
    ]
  },
  {
    "id": "sprint-results",
    "title": "Sprint Results",
    "href": "/entities/sprint-results",
    "category": "Results and championship",
    "entityIds": [
      "sensor.f1_sprint_results"
    ],
    "description": "Sprint classification results.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description races Field round race_name results number grid position laps time points status driver constructor 0 { permanentNumber, code, givenName, familyName } { name }",
    "related": [
      {
        "label": "Race results",
        "href": "/entities/season-results"
      },
      {
        "label": "Browse historical results",
        "href": "/features/historical-results"
      }
    ]
  },
  {
    "id": "starting-grid",
    "title": "Starting Grid",
    "href": "/entities/starting-grid",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_starting_grid"
    ],
    "description": "Provisional or confirmed Sprint/Race starting grid.",
    "availability": "Current weekend grid",
    "scope": "live",
    "keywords": "Value waiting_for_sprint_qualifying waiting_for_qualifying collecting provisional confirmed unavailable completed sprint race none live_timing_qualifying live_timing_archive live_timing_gridpos null Attribute Description status grid_context weekend_key weekend_format meeting_name session_key source_session_name target_session_name source source_updated_at cleared_at cleared_reason grid_count grid Field grid_position qualifying_position racing_number tla driver_name team_name team_color qualifying_time qualifying_time_secs qualifying_segment qualifying_lap segment_times grid_delta changed_from_qualifying sensor.f1_starting_grid normal unknown Sprint Qualifying Qualifying Sprint Race new_weekend sprint_completed race_completed ambiguous_grid_position Q3 SQ3",
    "related": [
      {
        "label": "Current driver timing",
        "href": "/entities/driver-positions"
      },
      {
        "label": "Dashboard modules",
        "href": "/cards/modular"
      },
      {
        "label": "Replay Mode",
        "href": "/features/replay-mode"
      }
    ]
  },
  {
    "id": "straight-mode",
    "title": "Straight Mode",
    "href": "/entities/straight-mode",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_straight_mode"
    ],
    "description": "Active aerodynamic straight mode state (2026 regulation, experimental).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Value normal_grip low_grip disabled Attribute Description overtake_enabled restored sensor.f1_straight_mode",
    "related": [
      {
        "label": "Overtake mode enabled",
        "href": "/entities/overtake-mode"
      },
      {
        "label": "State value definitions",
        "href": "/reference/values#straight-mode-2026-regulation"
      }
    ]
  },
  {
    "id": "team-radio",
    "title": "Team Radio",
    "href": "/entities/team-radio",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_team_radio"
    ],
    "description": "Latest team radio clip and rolling history (Replay Mode or F1TV Auth live timing).",
    "availability": "F1TV Auth / replay",
    "scope": "live",
    "keywords": "Attribute Description utc received_at racing_number driver_tla driver_name team_name team_color path clip_url sequence transcription_status transcription_text transcription_segments transcription_ai_task_entity_id transcription_generated_at transcription_error raw_message history Field unknown NOR HAM # processing completed failed A B null",
    "related": [
      {
        "label": "Set up the Team Radio module",
        "href": "/cards/team-radio"
      },
      {
        "label": "Transcribe a team radio clip",
        "href": "/features/team-radio-transcription"
      },
      {
        "label": "Drivers device triggers",
        "href": "/reference/device-triggers#drivers-device"
      }
    ]
  },
  {
    "id": "top-three",
    "title": "Top Three",
    "href": "/entities/top-three",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_top_three_p1",
      "sensor.f1_top_three_p2",
      "sensor.f1_top_three_p3"
    ],
    "description": "Dedicated sensors for current P1, P2 and P3.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description withheld position racing_number tla broadcast_name full_name first_name last_name team team_color team_color_rgb lap_time overall_fastest personal_fastest last_update_ts sensor.f1_top_three_p1 sensor.f1_top_three_p2 sensor.f1_top_three_p3 unknown [54, 113, 198] true",
    "related": [
      {
        "label": "Timing for every driver",
        "href": "/entities/driver-positions"
      },
      {
        "label": "Current session",
        "href": "/entities/current-session"
      }
    ]
  },
  {
    "id": "track-limits",
    "title": "Track Limits",
    "href": "/entities/track-limits",
    "category": "Officials and incidents",
    "entityIds": [
      "sensor.f1_track_limits"
    ],
    "description": "Track limits violations per driver (deletions, warnings, penalties).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description by_driver total_deletions total_warnings total_penalties last_update Field racing_number deletions warning penalty violations utc lap turn type sensor.f1_track_limits time_deleted",
    "related": [
      {
        "label": "Investigations and pending penalties",
        "href": "/entities/investigations"
      },
      {
        "label": "Official Race Control messages",
        "href": "/entities/race-control"
      }
    ]
  },
  {
    "id": "track-status",
    "title": "Track Status",
    "href": "/entities/track-status",
    "category": "Session and track",
    "entityIds": [
      "sensor.f1_track_status"
    ],
    "description": "Current track status.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description CLEAR YELLOW VSC SC RED",
    "related": [
      {
        "label": "Track flag values",
        "href": "/reference/values#track-status"
      },
      {
        "label": "Safety Car indicator",
        "href": "/entities/safety-car"
      },
      {
        "label": "Make lights follow track flags",
        "href": "/blueprints/track-status-light"
      }
    ]
  },
  {
    "id": "track-time",
    "title": "Track Time",
    "href": "/entities/track-time",
    "category": "Schedule and weather",
    "entityIds": [
      "sensor.f1_track_time"
    ],
    "description": "Current local time at the next race circuit.",
    "availability": "Season data",
    "scope": "static",
    "keywords": "Attribute Description timezone utc_offset offset_from_home circuit_name circuit_locality circuit_country Country sensor.f1_track_time HH:MM unknown +HHMM",
    "related": [
      {
        "label": "Next race timestamps",
        "href": "/entities/next-race"
      },
      {
        "label": "Season calendar",
        "href": "/entities/season-calendar"
      }
    ]
  },
  {
    "id": "track-weather",
    "title": "Track Weather",
    "href": "/entities/track-weather",
    "category": "Schedule and weather",
    "entityIds": [
      "sensor.f1_track_weather"
    ],
    "description": "Current on-track weather (air temp, track temp, rainfall, wind speed, etc.).",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description air_temperature air_temperature_unit humidity humidity_unit pressure hPa pressure_unit rainfall mm rainfall_unit track_temperature track_temperature_unit wind_speed wind_speed_unit wind_from_direction_degrees wind_from_direction_unit measurement_inferred unknown",
    "related": [
      {
        "label": "Circuit forecasts",
        "href": "/entities/next-race-weather"
      },
      {
        "label": "Compact forecast attributes",
        "href": "/entities/weather-summary"
      }
    ]
  },
  {
    "id": "tyre-statistics",
    "title": "Tyre Statistics",
    "href": "/entities/tyre-statistics",
    "category": "Drivers and timing",
    "entityIds": [
      "sensor.f1_tyre_statistics"
    ],
    "description": "Aggregated tyre statistics per compound.",
    "availability": "Public live / replay",
    "scope": "live",
    "keywords": "Attribute Description fastest_time fastest_time_secs deltas start_compounds compounds Field best_times total_laps sets_used sets_used_total compound_color compound_color_rgb time racing_number tla compound list sensor.f1_tyre_statistics unknown {\"MEDIUM\": \"+0.342\", \"HARD\": \"+0.891\"} [255, 0, 0]",
    "related": [
      {
        "label": "Tyres currently fitted",
        "href": "/entities/current-tyres"
      },
      {
        "label": "Weekend analysis and strategy",
        "href": "/features/weekend-analysis"
      }
    ]
  },
  {
    "id": "weather-summary",
    "title": "Weather Summary",
    "href": "/entities/weather-summary",
    "category": "Schedule and weather",
    "entityIds": [
      "sensor.f1_weather"
    ],
    "description": "Weather forecast at next race circuit.",
    "availability": "Forecasts",
    "scope": "static",
    "keywords": "Attribute Description season round race_name race_url circuit_id circuit_name circuit_url circuit_lat Latitude circuit_long Longitude circuit_locality circuit_country Country current_temperature current_temperature_unit current_humidity current_humidity_unit current_cloud_cover current_cloud_cover_unit current_precipitation current_precipitation_amount_min current_precipitation_amount_max current_precipitation_probability current_precipitation_probability_unit current_precipitation_unit current_wind_speed current_wind_speed_unit current_wind_direction current_wind_from_direction_degrees current_wind_from_direction_unit current_wind_gusts current_wind_gusts_unit current_visibility current_visibility_unit current_weather_code current_weather_source race_temperature race_temperature_unit race_humidity race_humidity_unit race_cloud_cover race_cloud_cover_unit race_precipitation race_precipitation_amount_min race_precipitation_amount_max race_precipitation_probability race_precipitation_probability_unit race_precipitation_unit race_wind_speed race_wind_speed_unit race_wind_direction race_wind_from_direction_degrees race_wind_from_direction_unit race_wind_gusts race_wind_gusts_unit race_visibility race_visibility_unit race_weather_code race_weather_source race_weather_icon sensor.f1_weather unknown",
    "related": [
      {
        "label": "Native weather entity and forecasts",
        "href": "/entities/next-race-weather"
      },
      {
        "label": "Live trackside measurements",
        "href": "/entities/track-weather"
      }
    ]
  }
];

export function getEntityReference(id) {
  return entityCatalog.find(entry => entry.id === id);
}
