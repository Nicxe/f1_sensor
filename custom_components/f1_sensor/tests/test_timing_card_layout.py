"""Regression tests for timing-card layout and auth-aware availability UX."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_PATH = (
    ROOT
    / "custom_components"
    / "f1_sensor"
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)


class DummyCoordinator(SimpleNamespace):
    def async_add_listener(self, _listener):
        return lambda: None


NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.TIMING_LAYOUT_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.TIMING_LAYOUT_PATH, "utf8");

function findMatchingBrace(text, openIndex) {
  let depth = 0;
  for (let idx = openIndex; idx < text.length; idx += 1) {
    const ch = text[idx];
    if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        return idx;
      }
    }
  }
  throw new Error(`Unmatched brace starting at ${openIndex}`);
}

function extractConst(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Const signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  const semicolon = source.indexOf(";", end);
  return source.slice(start, semicolon + 1);
}

function extractStatement(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Statement not found: ${signature}`);
  }
  const semicolon = source.indexOf(";", start);
  if (semicolon === -1) {
    throw new Error(`Statement semicolon not found: ${signature}`);
  }
  return source.slice(start, semicolon + 1);
}

function extractClass(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Class signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
}

function extractMethod(text, signature) {
  const start = text.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = text.indexOf("{", start);
  const end = findMatchingBrace(text, braceStart);
  return text.slice(start, end + 1);
}

function extractInstallOptions(className) {
  const signature = `installSectionsAutoHeight(${className}, {`;
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`installSectionsAutoHeight call not found for ${className}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  const objectLiteral = source.slice(braceStart, end + 1);
  return new Function(`return (${objectLiteral});`)();
}

function buildHost(data = {}) {
  const hostWidth = data.hostWidth ?? 0;
  const cardWidth = data.cardWidth ?? 0;
  const contentWidth = data.contentWidth ?? 0;
  const breakpoints = data.breakpoints || null;

  return {
    getBoundingClientRect() {
      return { width: hostWidth };
    },
    renderRoot: {
      querySelector() {
        return {
          clientWidth: cardWidth,
          getBoundingClientRect() {
            return { width: cardWidth };
          },
          firstElementChild: {
            getBoundingClientRect() {
              return { width: contentWidth };
            },
          },
        };
      },
    },
    _responsiveLayoutBreakpoints: breakpoints ? () => breakpoints : undefined,
  };
}

const helperSources = [
  extractConst("const TEAM_LOGO_URLS ="),
  extractConst("const TEAM_LOGO_ALIASES ="),
  extractStatement("const TEAM_LOGO_FORCE_WHITE ="),
  extractConst("const toColorLogoUrl = (url) =>"),
  extractConst("const normalizeTeamName = (team) =>"),
  extractConst("const getTeamLogoUrl = (team, size = 28, variant = 'white') =>"),
  extractConst("const getTeamLogoMeta = (team, size = 28, style = 'color', preferColor = false) =>"),
  extractConst("const resolveEntityIdWithFallback = (hass, entityId) =>"),
  extractConst("const getEntityStateWithFallback = (hass, entityId) =>"),
  extractConst("const isUnavailableLikeEntityState = (entityState) =>"),
  extractStatement("const DEFAULT_F1TV_AUTH_STATUS_ENTITY ="),
  extractStatement("const F1TV_AUTH_ATTENTION_STATES ="),
  extractConst("const findF1TvAuthStatusEntity = (hass) =>"),
  extractConst("const resolveF1TvAuthStatus = (hass, entityId) =>"),
  extractConst("const buildF1DataAvailabilityNotice = (hass, config, feature) =>"),
  extractConst("const resolveF1DataAvailabilityNotice = ("),
  extractConst("const normalizeF1GapMode = (value, fallback = 'ahead') =>"),
  extractConst("const normalizeF1GapValue = (value) =>"),
  extractConst("const formatF1DeltaSeconds = (value, zeroValue = '--') =>"),
  extractConst("const measureRenderedCardWidth = (host) =>"),
  extractConst("const DEFAULT_RESPONSIVE_BREAKPOINTS ="),
  extractConst("const getResponsiveBreakpoints = (host) =>"),
  extractConst("const resolveResponsiveLayoutMode = (width, breakpoints) =>"),
  extractConst("const getResponsiveLayoutMode = (host) =>"),
];

const liveSessionClass = extractClass("class F1LiveSessionCard extends LitElement {");
const driverLapTimesClass = extractClass("class F1DriverLapTimesCard extends LitElement {");
const qualifyingClass = extractClass("class F1QualifyingTimingCard extends LitElement {");
const practiceClass = extractClass("class F1PracticeTimingCard extends LitElement {");
const raceLapClass = extractClass("class F1RaceLapCard extends LitElement {");
const driversClass = extractClass("class F1ChampionshipPredictionDriversCard extends LitElement {");
const driversEditorClass = extractClass("class F1ChampionshipPredictionDriversCardEditor extends LitElement {");
const teamsClass = extractClass("class F1ChampionshipPredictionTeamsCard extends LitElement {");
const teamsEditorClass = extractClass("class F1ChampionshipPredictionTeamsCardEditor extends LitElement {");
const pitStopClass = extractClass("class F1PitStopOverviewCard extends LitElement {");
const pitStopEditorClass = extractClass("class F1PitStopOverviewCardEditor extends LitElement {");
const raceLapEditorClass = extractClass("class F1RaceLapCardEditor extends LitElement {");
const investigationsClass = extractClass("class F1InvestigationsCard extends LitElement {");
const trackLimitsClass = extractClass("class F1TrackLimitsCard extends LitElement {");
const startingGridClass = extractClass("class F1StartingGridCard extends LitElement {");

const Harnesses = new Function(
  `
  const LEGACY_ENTITY_ID_FALLBACKS = {};
  const COMPOUND_FALLBACK = {};

  ${helperSources.join("\n\n")}

  class LiveSessionHarness {
    ${extractMethod(liveSessionClass, "getGridOptions() {")}
  }

  class QualifyingHarness {
    constructor(config = {}) {
      this.config = {
        show_team_logo: false,
        show_full_name: false,
        team_logo_style: 'color',
        ...config,
      };
      this.hass = {};
    }

    ${extractMethod(qualifyingClass, "getGridOptions() {")}
    ${extractMethod(qualifyingClass, "_columns(layoutMode = 'wide', sessionPart = null, showDelta = false) {")}
    ${extractMethod(qualifyingClass, "_buildRows(positionDrivers, tyresDrivers, driverList, currentQPart) {")}
    ${extractMethod(qualifyingClass, "_applyCurrentSegmentDeltas(rows) {")}
    ${extractMethod(qualifyingClass, "_normalizeQualifyingPart(value) {")}
    ${extractMethod(qualifyingClass, "_inferQualifyingPartFromDrivers(drivers) {")}
    ${extractMethod(qualifyingClass, "_normalizeSectorDisplayMode(value) {")}
    ${extractMethod(qualifyingClass, "_resolveSectorDisplay(pos, idx, mode = 'current') {")}
    ${extractMethod(qualifyingClass, "_sectorFromSource(pos, idx, source) {")}
    ${extractMethod(qualifyingClass, "_parseSectorSeconds(value) {")}
    ${extractMethod(qualifyingClass, "_resolveLastLapTime(pos) {")}
    ${extractMethod(qualifyingClass, "_sectorClass(overallFastest, personalFastest, hasTiming) {")}
    ${extractMethod(qualifyingClass, "_statusInfo(pos) {")}
    ${extractMethod(qualifyingClass, "_normalizeColor(value) {")}
    ${extractMethod(qualifyingClass, "_parsePosition(value) {")}
    ${extractMethod(qualifyingClass, "_parseLapTimeSeconds(value) {")}
  }

  class PracticeHarness {
    constructor(config = {}) {
      this.config = {
        show_position: true,
        show_team_logo: true,
        show_full_name: false,
        show_status: true,
        show_tyre: true,
        show_tyre_age: true,
        show_last_lap: true,
        show_fastest_lap: true,
        ...config,
      };
    }

    ${extractMethod(practiceClass, "getGridOptions() {")}
    ${extractMethod(practiceClass, "_columns(layoutMode = 'wide') {")}
  }

  class DriverLapTimesHarness {
    constructor(config = {}) {
      this.config = {
        show_position: true,
        show_team_logo: true,
        show_tla: true,
        show_gap: true,
        show_last_lap: true,
        show_best_lap: true,
        ...config,
      };
    }

    ${extractMethod(driverLapTimesClass, "_columns(lapNumbers = [], layoutMode = 'wide', gapMode = 'ahead') {")}
  }

  class RaceLapHarness {
    constructor(config = {}) {
      this.config = {
        show_position: true,
        show_team_logo: true,
        show_full_name: false,
        show_gap: true,
        show_tyre: true,
        show_tyre_age: true,
        show_pit_count: true,
        show_last_lap: true,
        show_fastest_lap: true,
        ...config,
      };
    }

    ${extractMethod(raceLapClass, "getGridOptions() {")}
    ${extractMethod(raceLapClass, "_columns(layoutMode = 'wide', suppressPit = false, gapMode = 'ahead') {")}
  }

  class PitStopHarness {
    constructor(config = {}) {
      this.config = {
        show_tla: true,
        show_full_name: false,
        show_tyre: true,
        show_pit_count: true,
        show_pit_time: true,
        show_pit_lane_time: true,
        show_pit_delta: true,
        ...config,
      };
    }

    ${extractMethod(pitStopClass, "_columns(rows, layoutMode = 'wide', suppressPit = false) {")}
  }

  return {
    measureRenderedCardWidth,
    getResponsiveLayoutMode,
    resolveF1DataAvailabilityNotice,
    LiveSessionHarness,
    DriverLapTimesHarness,
    QualifyingHarness,
    PracticeHarness,
    RaceLapHarness,
    PitStopHarness,
    normalizeTeamName,
    getTeamLogoMeta,
  };
`,
)();

let result;
if (payload.action === "measure_width") {
  result = Harnesses.measureRenderedCardWidth(buildHost(payload.host || {}));
} else if (payload.action === "layout_mode") {
  result = Harnesses.getResponsiveLayoutMode(buildHost(payload.host || {}));
} else if (payload.action === "grid_options") {
  const className = payload.className;
  const mapping = {
    F1LiveSessionCard: Harnesses.LiveSessionHarness,
    F1QualifyingTimingCard: Harnesses.QualifyingHarness,
    F1PracticeTimingCard: Harnesses.PracticeHarness,
    F1RaceLapCard: Harnesses.RaceLapHarness,
  };
  const Klass = mapping[className];
  if (!Klass) {
    throw new Error(`Unknown className: ${className}`);
  }
  result = new Klass(payload.config || {}).getGridOptions();
} else if (payload.action === "install_options") {
  result = extractInstallOptions(payload.className);
} else if (payload.action === "driver_lap_columns") {
  result = new Harnesses.DriverLapTimesHarness(payload.config || {})._columns(
    payload.lapNumbers || [],
    payload.layoutMode || "wide",
    payload.gapMode || "ahead",
  );
} else if (payload.action === "qualifying_columns") {
  result = new Harnesses.QualifyingHarness(payload.config || {})._columns(
    payload.layoutMode || "wide",
    payload.sessionPart ?? null,
    Boolean(payload.showDelta),
  );
} else if (payload.action === "practice_columns") {
  result = new Harnesses.PracticeHarness(payload.config || {})._columns(
    payload.layoutMode || "wide",
  );
} else if (payload.action === "qualifying_rows") {
  result = new Harnesses.QualifyingHarness(payload.config || {})._buildRows(
    payload.positionDrivers || [],
    payload.tyresDrivers || [],
    payload.driverList || [],
    payload.currentQPart ?? null,
  ).map((row) => ({
    rn: row.rn,
    position: row.position,
    current_segment_best_lap: row.current_segment_best_lap,
    current_segment_delta: row.current_segment_delta,
    current_segment_delta_secs: row.current_segment_delta_secs,
  }));
} else if (payload.action === "race_lap_columns") {
  result = new Harnesses.RaceLapHarness(payload.config || {})._columns(
    payload.layoutMode || "wide",
    Boolean(payload.suppressPit),
    payload.gapMode || "ahead",
  );
} else if (payload.action === "pit_stop_columns") {
  result = new Harnesses.PitStopHarness(payload.config || {})._columns(
    payload.rows || [],
    payload.layoutMode || "wide",
    Boolean(payload.suppressPit),
  );
} else if (payload.action === "availability_notice") {
  result = Harnesses.resolveF1DataAvailabilityNotice(
    { states: payload.hassStates || {} },
    payload.config || {},
    payload.feature || "predicted_points",
    payload.dataUnavailable !== false,
    payload.featureEnabled !== false,
  );
} else if (payload.action === "team_logo_meta") {
  const logo = Harnesses.getTeamLogoMeta(
    payload.team,
    payload.size || 24,
    payload.style || "color",
    Boolean(payload.preferColor),
  );
  result = {
    normalized: Harnesses.normalizeTeamName(payload.team),
    logo,
  };
} else if (payload.action === "source_checks") {
  result = {
    driversCardUsesShortTitle: driversClass.includes("Driver Championship"),
    driversCardAvoidsLongTitle: !driversClass.includes("Championship Standings Drivers"),
    driversEditorUsesShortTitle: driversEditorClass.includes("Driver Championship"),
    driversEditorAvoidsLongTitle: !driversEditorClass.includes("Championship Standings Drivers"),
    teamsCardUsesShortTitle: teamsClass.includes("Constructor Championship"),
    teamsCardAvoidsLongTitle: !teamsClass.includes("Championship Standings Teams"),
    teamsEditorUsesShortTitle: teamsEditorClass.includes("Constructor Championship"),
    teamsEditorAvoidsLongTitle: !teamsEditorClass.includes("Championship Standings Teams"),
    driversOldReplayOnlyCopyRemoved: !driversClass.includes("Predicted points available in Replay Mode only")
      && !driversEditorClass.includes("Replay Mode only"),
    teamsOldReplayOnlyCopyRemoved: !teamsClass.includes("Predicted points available in Replay Mode only")
      && !teamsEditorClass.includes("Replay Mode only"),
    pitStopOldReplayOnlyCopyRemoved: !pitStopClass.includes("Pit stop data is available in Replay Mode only")
      && !pitStopEditorClass.includes("Replay Mode only"),
    raceLapOldReplayOnlyCopyRemoved: !raceLapClass.includes("Pit stop data is available in Replay Mode only")
      && !raceLapEditorClass.includes("Replay Mode only"),
    raceLapAuthNoticePresent: raceLapClass.includes("resolveF1DataAvailabilityNotice("),
    raceLapPitSuppressionCallPresent: raceLapClass.includes(
      "Boolean(this.config.pitstops_entity) && !pitDataAvailable",
    ),
    driverLapTimesGapFieldsPresent: driverLapTimesClass.includes("gap_to_leader")
      && driverLapTimesClass.includes("interval_to_position_ahead")
      && driverLapTimesClass.includes("_renderGapModeToggle(gapMode)"),
    raceLapGapFieldsPresent: raceLapClass.includes("gap_to_leader")
      && raceLapClass.includes("interval_to_position_ahead")
      && raceLapClass.includes("_renderGapModeToggle(gapMode)"),
    qualifyingDeltaPresent: qualifyingClass.includes("_applyCurrentSegmentDeltas(rows)")
      && qualifyingClass.includes("current_segment_delta")
      && qualifyingClass.includes("formatF1DeltaSeconds(delta, '--')"),
    qualifyingDeltaColumnDynamic: qualifyingClass.includes("minmax(58px, 0.72fr)")
      && qualifyingClass.includes(".qt-cell.center .qt-delta"),
    tableCardsAvoidMaxContentTables: [
      pitStopClass,
      driverLapTimesClass,
      practiceClass,
      raceLapClass,
      startingGridClass,
    ].every((cardSource) => !cardSource.includes("min-width: max-content")
      && !cardSource.includes("width: max-content")),
    incidentTablesUseMinmaxColumns: investigationsClass.includes("minmax(90px, 0.85fr)")
      && trackLimitsClass.includes("minmax(90px, 0.7fr)"),
    qualifyingRowHeightPresent: qualifyingClass.includes(".qt-row:not(.header)")
      && qualifyingClass.includes("height: var(--f1-live-table-row-height, 34px);"),
    practiceRowHeightPresent: practiceClass.includes(".pt-row:not(.header)")
      && practiceClass.includes("height: var(--f1-live-table-row-height, 34px);"),
    raceLapRowHeightPresent: raceLapClass.includes(".rl-row:not(.header)")
      && raceLapClass.includes("height: var(--f1-live-table-row-height, 34px);"),
  };
} else {
  throw new Error(`Unknown action: ${payload.action}`);
}

process.stdout.write(JSON.stringify(result));
"""


def _run_probe(payload: dict) -> dict | list | str | int | None:
    """Execute a small Node probe against the actual card source."""
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for timing card layout regression tests")

    env = os.environ.copy()
    env["TIMING_LAYOUT_PATH"] = str(CARD_PATH)
    env["TIMING_LAYOUT_PAYLOAD"] = json.dumps(payload)

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def test_measure_rendered_card_width_prefers_container_over_overflow_content() -> None:
    """Overflowing content must not force the layout engine into wide mode."""
    result = _run_probe(
        {
            "action": "measure_width",
            "host": {
                "hostWidth": 320,
                "cardWidth": 320,
                "contentWidth": 760,
            },
        }
    )

    assert result == 320


def test_overflowing_content_still_uses_narrow_layout_breakpoints() -> None:
    """Layout mode should follow actual card width, not scroll width."""
    result = _run_probe(
        {
            "action": "layout_mode",
            "host": {
                "hostWidth": 320,
                "cardWidth": 320,
                "contentWidth": 760,
                "breakpoints": {"narrow": 560, "medium": 920},
            },
        }
    )

    assert result == "narrow"


@pytest.mark.parametrize(
    "team_name",
    [
        "Cadillac",
        "Cadillac F1 Team",
        "Cadillac Ferrari",
        "Cadillac Formula 1 Team",
    ],
)
def test_team_logo_lookup_resolves_cadillac_constructor_names(team_name: str) -> None:
    """Cadillac should render a team logo for current standings and live feeds."""
    result = _run_probe({"action": "team_logo_meta", "team": team_name})

    assert result["normalized"] == "Cadillac"
    assert result["logo"]["src"].endswith(
        "/common/f1/2026/cadillac/2026cadillaclogowhite.webp"
    )


@pytest.mark.parametrize(
    "class_name",
    [
        "F1LiveSessionCard",
        "F1QualifyingTimingCard",
        "F1PracticeTimingCard",
        "F1RaceLapCard",
    ],
)
def test_timing_cards_use_four_min_columns_for_sections_layout(class_name: str) -> None:
    """Target cards should stay usable in narrower Home Assistant sections."""
    grid_options = _run_probe({"action": "grid_options", "className": class_name})
    install_options = _run_probe({"action": "install_options", "className": class_name})

    assert grid_options["min_columns"] == 4
    assert install_options["min_columns"] == 4


def test_race_lap_columns_hide_pit_count_when_pit_sensor_is_unavailable() -> None:
    """Pit count should be suppressed in live no-auth when pit stop sensor is unavailable."""
    visible_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "suppressPit": False,
        }
    )
    suppressed_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "suppressPit": True,
        }
    )

    assert any(column["key"] == "pit_count" for column in visible_columns)
    assert all(column["key"] != "pit_count" for column in suppressed_columns)


def test_pit_stop_narrow_layout_keeps_tyre_column_readable() -> None:
    """Small Pit Stops cards should protect tyres before shrinking numeric columns."""
    columns = _run_probe(
        {
            "action": "pit_stop_columns",
            "layoutMode": "narrow",
            "rows": [{"pit_lane_time_num": 21.4, "pit_delta_num": 1.2}],
        }
    )

    assert [column["key"] for column in columns] == [
        "tla",
        "tyre",
        "pit_count",
        "pit_time",
        "pit_delta",
    ]
    assert (
        next(column for column in columns if column["key"] == "tla")["width"]
        == "minmax(90px, 1.18fr)"
    )
    assert (
        next(column for column in columns if column["key"] == "tyre")["width"]
        == "minmax(50px, 0.64fr)"
    )
    assert all(
        column["width"].startswith("minmax(")
        for column in columns
        if column["key"] in {"pit_count", "pit_time", "pit_delta"}
    )


def test_driver_positions_sensor_exposes_public_race_gap_fields(hass) -> None:
    """TimingData gaps should be exposed without relying on auth-gated streams."""
    from custom_components.f1_sensor.sensor import F1DriverPositionsSensor

    coord = DummyCoordinator(
        data={
            "lap_current": 12,
            "lap_total": 58,
            "drivers": {
                "16": {
                    "identity": {
                        "tla": "LEC",
                        "name": "Charles Leclerc",
                        "team": "Ferrari",
                    },
                    "lap_history": {
                        "grid_position": "2",
                        "laps": {"12": "1:32.100"},
                        "completed_laps": 12,
                    },
                    "timing": {
                        "position": "2",
                        "gap_to_leader": "+1.234",
                        "interval": "+0.456",
                    },
                    "sectors": {},
                }
            },
        }
    )
    sensor = F1DriverPositionsSensor(coord, "uid", "entry", "F1")
    sensor.hass = hass
    sensor._session_info_coordinator = SimpleNamespace(
        data={"Type": "Race", "Name": "Race"}
    )

    assert sensor._update_from_coordinator(initial=True) is True

    driver = sensor._attr_extra_state_attributes["drivers"][0]
    assert driver["gap_to_leader"] == "+1.234"
    assert driver["interval_to_position_ahead"] == "+0.456"


def test_driver_lap_times_gap_column_can_switch_mode_and_hide() -> None:
    ahead_columns = _run_probe(
        {
            "action": "driver_lap_columns",
            "layoutMode": "wide",
            "gapMode": "ahead",
        }
    )
    leader_columns = _run_probe(
        {
            "action": "driver_lap_columns",
            "layoutMode": "wide",
            "gapMode": "leader",
        }
    )
    hidden_columns = _run_probe(
        {
            "action": "driver_lap_columns",
            "layoutMode": "wide",
            "config": {"show_gap": False},
        }
    )

    assert (
        next(column for column in ahead_columns if column["key"] == "gap")["label"]
        == "INT"
    )
    assert (
        next(column for column in leader_columns if column["key"] == "gap")["label"]
        == "GAP"
    )
    assert all(column["key"] != "gap" for column in hidden_columns)


def test_race_lap_gap_column_can_switch_mode_and_hide() -> None:
    ahead_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "gapMode": "ahead",
        }
    )
    leader_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "gapMode": "leader",
        }
    )
    hidden_columns = _run_probe(
        {
            "action": "race_lap_columns",
            "layoutMode": "wide",
            "config": {"show_gap": False},
        }
    )

    assert (
        next(column for column in ahead_columns if column["key"] == "gap")["label"]
        == "Int"
    )
    assert (
        next(column for column in leader_columns if column["key"] == "gap")["label"]
        == "Gap"
    )
    assert all(column["key"] != "gap" for column in hidden_columns)


def test_qualifying_medium_layout_distributes_extra_width_across_timing_columns() -> (
    None
):
    """Wider medium cards should not leave all spare width after the driver."""
    columns = _run_probe(
        {
            "action": "qualifying_columns",
            "layoutMode": "medium",
            "sessionPart": 1,
            "showDelta": True,
        }
    )
    widths = {column["key"]: column["width"] for column in columns}

    assert widths["tla"] == "minmax(92px, 0.72fr)"
    assert widths["sector_1"] == "minmax(62px, 0.72fr)"
    assert widths["sector_2"] == "minmax(62px, 0.72fr)"
    assert widths["sector_3"] == "minmax(62px, 0.72fr)"
    assert widths["last_lap"] == "minmax(78px, 0.95fr)"
    assert widths["best_session"] == "minmax(78px, 0.95fr)"
    assert widths["delta"] == "minmax(58px, 0.72fr)"


def test_timing_table_cards_use_dynamic_minmax_columns() -> None:
    """Shared timing tables should distribute available width across data columns."""
    driver_lap_widths = {
        column["key"]: column["width"]
        for column in _run_probe(
            {
                "action": "driver_lap_columns",
                "layoutMode": "wide",
                "lapNumbers": [1, 2, 3],
                "config": {"show_lap_history": True},
            }
        )
    }
    practice_widths = {
        column["key"]: column["width"]
        for column in _run_probe({"action": "practice_columns", "layoutMode": "wide"})
    }
    race_widths = {
        column["key"]: column["width"]
        for column in _run_probe({"action": "race_lap_columns", "layoutMode": "wide"})
    }

    assert driver_lap_widths["tla"] == "minmax(96px, 0.7fr)"
    assert driver_lap_widths["last_lap"] == "minmax(76px, 0.9fr)"
    assert driver_lap_widths["lap_3"] == "minmax(82px, 0.95fr)"
    assert practice_widths["driver"] == "minmax(96px, 0.7fr)"
    assert practice_widths["fastest_lap"] == "minmax(82px, 1fr)"
    assert race_widths["driver"] == "minmax(96px, 0.7fr)"
    assert race_widths["gap"] == "minmax(58px, 0.62fr)"
    assert race_widths["fastest_lap"] == "minmax(82px, 1fr)"


def test_qualifying_delta_column_is_optional_and_uses_current_q_part() -> None:
    hidden_columns = _run_probe(
        {
            "action": "qualifying_columns",
            "layoutMode": "wide",
            "sessionPart": 2,
            "showDelta": False,
        }
    )
    visible_columns = _run_probe(
        {
            "action": "qualifying_columns",
            "layoutMode": "wide",
            "sessionPart": 2,
            "showDelta": True,
        }
    )
    rows = _run_probe(
        {
            "action": "qualifying_rows",
            "currentQPart": 2,
            "positionDrivers": [
                {
                    "racing_number": "1",
                    "tla": "VER",
                    "current_position": "1",
                    "q2_time": "1:10.000",
                    "q2_position": 1,
                },
                {
                    "racing_number": "16",
                    "tla": "LEC",
                    "current_position": "2",
                    "q2_time": "1:10.345",
                    "q2_position": 2,
                },
                {
                    "racing_number": "44",
                    "tla": "HAM",
                    "current_position": "3",
                },
            ],
        }
    )

    assert all(column["key"] != "delta" for column in hidden_columns)
    assert any(column["key"] == "delta" for column in visible_columns)
    assert rows[0] == {
        "rn": "1",
        "position": 1,
        "current_segment_best_lap": "1:10.000",
        "current_segment_delta": "--",
        "current_segment_delta_secs": 0,
    }
    assert rows[1]["rn"] == "16"
    assert rows[1]["position"] == 2
    assert rows[1]["current_segment_best_lap"] == "1:10.345"
    assert rows[1]["current_segment_delta"] == "+0.345"
    assert rows[1]["current_segment_delta_secs"] == pytest.approx(0.345)
    assert rows[2] == {
        "rn": "44",
        "position": None,
        "current_segment_best_lap": None,
        "current_segment_delta": None,
        "current_segment_delta_secs": None,
    }


def _auth_state(
    state: str, *, configured: bool, used_for_live_timing: bool = False
) -> dict:
    return {
        "state": state,
        "attributes": {
            "auth_configured": configured,
            "used_for_live_timing": used_for_live_timing,
        },
    }


def test_prediction_notice_explains_missing_auth_by_default() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "predicted_points",
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state(
                    "not_configured", configured=False
                )
            },
        }
    )

    assert result == {
        "tone": "info",
        "message": "Predicted points are hidden because F1TV access is not configured. They are still available in Replay Mode.",
    }


def test_pit_stop_notice_explains_missing_auth_by_default() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "pit_stops",
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state(
                    "not_configured", configured=False
                )
            },
        }
    )

    assert result == {
        "tone": "info",
        "message": "Pit stop data is hidden because F1TV access is not configured. It is still available in Replay Mode.",
    }


def test_availability_notice_can_hide_non_actionable_info() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "predicted_points",
            "config": {"show_availability_notice": False},
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state(
                    "not_configured", configured=False
                )
            },
        }
    )

    assert result is None


def test_availability_notice_keeps_auth_attention_visible_when_hidden() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "predicted_points",
            "config": {"show_availability_notice": False},
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state("rejected", configured=True)
            },
        }
    )

    assert result == {
        "tone": "warning",
        "message": "F1TV access needs attention, so live predicted points are hidden. Replay data remains available.",
    }


def test_availability_notice_is_hidden_for_valid_auth() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "predicted_points",
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state(
                    "valid", configured=True, used_for_live_timing=True
                )
            },
        }
    )

    assert result is None


def test_availability_notice_auto_detects_prefixed_auth_status_entity() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "pit_stops",
            "hassStates": {
                "sensor.f1_system_f1_f1tv_token_status": _auth_state(
                    "valid", configured=True, used_for_live_timing=True
                )
            },
        }
    )

    assert result is None


def test_availability_notice_handles_missing_auth_status_sensor() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "predicted_points",
            "hassStates": {},
        }
    )

    assert result == {
        "tone": "info",
        "message": "Predicted points are available in Replay Mode or live when F1TV access is active.",
    }


def test_availability_notice_is_not_rendered_when_data_is_available() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "predicted_points",
            "dataUnavailable": False,
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state("valid", configured=True)
            },
        }
    )

    assert result is None


def test_availability_notice_is_not_rendered_when_feature_is_disabled() -> None:
    result = _run_probe(
        {
            "action": "availability_notice",
            "feature": "pit_stops",
            "featureEnabled": False,
            "hassStates": {
                "sensor.f1_f1tv_token_status": _auth_state(
                    "not_configured", configured=False
                )
            },
        }
    )

    assert result is None


def test_timing_card_source_keeps_auth_aware_notices_and_short_titles() -> None:
    """Lock the auth-aware availability UX and shorter default headers."""
    result = _run_probe({"action": "source_checks"})

    assert result == {
        "driversCardUsesShortTitle": True,
        "driversCardAvoidsLongTitle": True,
        "driversEditorUsesShortTitle": True,
        "driversEditorAvoidsLongTitle": True,
        "teamsCardUsesShortTitle": True,
        "teamsCardAvoidsLongTitle": True,
        "teamsEditorUsesShortTitle": True,
        "teamsEditorAvoidsLongTitle": True,
        "driversOldReplayOnlyCopyRemoved": True,
        "teamsOldReplayOnlyCopyRemoved": True,
        "pitStopOldReplayOnlyCopyRemoved": True,
        "raceLapOldReplayOnlyCopyRemoved": True,
        "raceLapAuthNoticePresent": True,
        "raceLapPitSuppressionCallPresent": True,
        "driverLapTimesGapFieldsPresent": True,
        "raceLapGapFieldsPresent": True,
        "qualifyingDeltaPresent": True,
        "qualifyingDeltaColumnDynamic": True,
        "tableCardsAvoidMaxContentTables": True,
        "incidentTablesUseMinmaxColumns": True,
        "qualifyingRowHeightPresent": True,
        "practiceRowHeightPresent": True,
        "raceLapRowHeightPresent": True,
    }
