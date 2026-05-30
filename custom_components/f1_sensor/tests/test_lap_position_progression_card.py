"""Tests for the native lap position progression card logic."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
BUNDLED_CARD_PATH = (
    ROOT
    / "custom_components"
    / "f1_sensor"
    / "www"
    / "f1-sensor-live-data-card"
    / "f1-sensor-live-data-card.js"
)
RUNTIME_CARD_PATH = ROOT / "www" / "f1-sensor-live-data-card.js"

NODE_CARD_PROBE = r"""
const fs = require("node:fs");

const source = fs.readFileSync(process.env.F1_LAP_CARD_PATH, "utf8");

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

function extractClass(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Class signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
}

const constantsStart = source.indexOf("const DEFAULT_F1_LAP_POSITION_PROGRESSION_CONFIG =");
const constantsEnd = source.indexOf("// ============================================================================\n// F1 Season Progression Card", constantsStart);
const classSource = extractClass("class F1LapPositionProgressionCard extends LitElement {");
const editorSource = extractClass("class F1LapPositionProgressionCardEditor extends LitElement {");

const harnessFactory = new Function(`
const F1_THEME_STYLES = {};
const F1_SEASON_PROGRESSION_FALLBACK_COLORS = ["#111111", "#222222", "#333333", "#444444"];
const css = (strings, ...values) => strings.reduce((out, part, index) => out + part + (index < values.length ? String(values[index]) : ""), "");
const html = css;
const svg = css;
class LitElement {
  dispatchEvent(event) {
    this.lastEvent = event;
  }
}
const asEntityList = (value) => Array.isArray(value) ? value : (value && typeof value === "object" ? Object.values(value) : []);
const getEntityStateWithFallback = (hass, entityId) => hass?.states?.[entityId] || null;
const resolveEntityIdWithFallback = (_hass, entityId) => entityId;
const isUnavailableLikeEntityState = (state) => ["unknown", "unavailable"].includes(String(state?.state || "").toLowerCase());
const getResponsiveLayoutMode = () => "wide";
const isEffectiveLightTheme = () => false;
const getTeamLogoMeta = (team) => team ? ({ src: "logo.png", fallback: "" }) : null;
const handleTeamLogoError = () => {};
const applyF1ThemeMode = () => {};
const ensureF1Fonts = () => {};
const renderEditorSelect = () => "";
const renderThemeModeSelect = () => "";

${source.slice(constantsStart, constantsEnd)}
${classSource}
${editorSource}

return { F1LapPositionProgressionCard, F1LapPositionProgressionCardEditor };
`);

const { F1LapPositionProgressionCard, F1LapPositionProgressionCardEditor } = harnessFactory();

async function main() {
  const sessionsPayload = [
    {
      key: "race:2026:1",
      type: "race",
      status: "available",
      round: "1",
      race_name: "Australian Grand Prix",
      total_laps: null,
      driver_count: 3
    },
    {
      key: "sprint:2026:2",
      type: "sprint",
      status: "unsupported",
      round: "2",
      race_name: "Chinese Grand Prix",
      driver_count: 3
    },
    {
      key: "race:2026:3",
      type: "race",
      status: "pending",
      round: "3",
      race_name: "Japanese Grand Prix"
    }
  ];
  const fullSessionPayload = {
    key: "race:2026:1",
    type: "race",
    status: "available",
    round: "1",
    race_name: "Australian Grand Prix",
    total_laps: 4,
    driver_count: 3,
    labels: ["L1", "L2", "L3", "L4"],
    drivers: [
      { driver_id: "norris", code: "NOR", name: "Lando Norris", constructor_name: "McLaren", color: "#ff8000", grid: 2, finish_position: 1, positions: [1, 2, null, 1] },
      { driver_id: "verstappen", code: "VER", name: "Max Verstappen", constructor_name: "Red Bull", color: "#3671c6", grid: 1, finish_position: 2, positions: [2, 2, 1, 2] },
      { driver_id: "piastri", code: "PIA", name: "Oscar Piastri", constructor_name: "McLaren", color: "#ff8000", grid: 3, finish_position: 3, positions: [3, 3, 2, 3] }
    ],
    series: {
      labels: ["L1", "L2", "L3", "L4"],
      series: []
    }
  };
  const gappedGridPositions = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22];
  const gappedSessionPayload = {
    key: "race:2026:5",
    type: "race",
    status: "available",
    round: "5",
    race_name: "Canadian Grand Prix",
    total_laps: 2,
    driver_count: 22,
    labels: ["L1", "L2"],
    drivers: [
      ...gappedGridPositions.map((grid, index) => {
        const finish = index + 1;
        const code = `V${String(finish).padStart(2, "0")}`;
        return {
          driver_id: `visible_${finish}`,
          code,
          name: `Visible Driver ${finish}`,
          constructor_name: "Test Team",
          color: "#00a3ff",
          grid,
          finish_position: finish,
          positions: [Math.min(grid, 22), finish],
        };
      }),
      {
        driver_id: "missing_grid_5",
        code: "M05",
        name: "Missing Driver Five",
        constructor_name: "Test Team",
        color: "#ff2800",
        grid: 5,
        finish_position: 21,
        positions: [null, null],
      },
      {
        driver_id: "missing_grid_15",
        code: "M15",
        name: "Missing Driver Fifteen",
        constructor_name: "Test Team",
        color: "#ff2800",
        grid: 15,
        finish_position: 22,
        positions: [null, null],
      },
    ],
    series: {
      labels: ["L1", "L2"],
      series: []
    }
  };

  const wsMessages = [];
  const card = new F1LapPositionProgressionCard();
  card.hass = {
    callWS: async (message) => {
      wsMessages.push(message);
      return { status: "available", session: fullSessionPayload };
    },
    states: {
      "sensor.f1_lap_position_progression": {
        state: "3",
        attributes: { sessions: sessionsPayload }
      },
      "sensor.f1_driver_list": {
        state: "20",
        attributes: {
          drivers: [
            { tla: "NOR", racing_number: "4", team: "McLaren", team_color: "#ff8000" },
            { tla: "VER", racing_number: "1", team: "Red Bull", team_color: "#3671c6" }
          ]
        }
      }
    }
  };
  card.setConfig({ top_limit: 2 });

  const sessions = card._buildSessions(card.hass.states["sensor.f1_lap_position_progression"]);
  const selected = card._resolveSelectedSession(sessions);
  const unsupported = sessions.find((session) => session.type === "sprint");
  card._selectedSessionKey = unsupported.key;
  const selectedUnsupported = card._resolveSelectedSession(sessions);
  card._selectedSessionKey = null;

  await card._ensureSessionData(selected);
  const loadedSession = card._sessionForRender(selected);
  const model = card._buildChartModel(loadedSession);
  const renderedCard = card.render();
  const pathWithGap = card._buildPath([
    { x: 1, y: 1 },
    null,
    { x: 2, y: 2 },
  ]);
  const svgOutput = card._renderSvg(model);
  const firstPathMatch = svgOutput.match(/<path class="lp-series-line" d=([^>]+)>/);
  const firstPath = firstPathMatch ? firstPathMatch[1] : "";
  const coords = firstPath.match(/M\s+[\d.]+\s+([\d.]+)\s+L\s+[\d.]+\s+([\d.]+)/);
  const initialPathCount = [...svgOutput.matchAll(/<path class="lp-series-line"/g)].length;
  const leftSideLabels = [...svgOutput.matchAll(/class="lp-side-label left"[^>]*>([^<]+)<\/text>/g)].map((match) => match[1]);
  const rightSideLabels = [...svgOutput.matchAll(/class="lp-side-label right"[^>]*>([^<]+)<\/text>/g)].map((match) => match[1]);
  const gappedCard = new F1LapPositionProgressionCard();
  gappedCard.hass = card.hass;
  gappedCard.setConfig({ show_round_labels: false });
  const gappedModel = gappedCard._buildChartModel(gappedSessionPayload);
  const gappedSvgOutput = gappedCard._renderSvg(gappedModel);
  const gappedLeftMatches = [...gappedSvgOutput.matchAll(/class="lp-side-label left"[^>]*\sy=([\d.]+)[^>]*>([^<]+)<\/text>/g)];
  const gappedLeftLabels = gappedLeftMatches.map((match) => match[2]);
  const gappedLeftY = gappedLeftMatches.map((match) => Number(match[1]));
  const gappedLeftSteps = gappedLeftY.slice(1).map((y, index) => Number((y - gappedLeftY[index]).toFixed(2)));
  const gappedCurrentLabels = [...gappedSvgOutput.matchAll(/class="lp-side-label right"[^>]*>([^<]+)<\/text>/g)].map((match) => match[1]);
  const gappedPathCount = [...gappedSvgOutput.matchAll(/<path class="lp-series-line"/g)].length;

  const firstSeries = model.series[0];
  card._toggleSeriesVisibility(firstSeries, { stopPropagation() {}, preventDefault() {} });
  const filteredSvgOutput = card._renderSvg(model);
  const filteredPathCount = [...filteredSvgOutput.matchAll(/<path class="lp-series-line"/g)].length;
  const hiddenSideLabels = [...filteredSvgOutput.matchAll(/<g\s+class="lp-side-entry"\s+data-hidden=true[\s\S]*?<text class="lp-side-label (?:left|right)"[^>]*>([^<]+)<\/text>/g)].map((match) => match[1]);
  const hiddenAfterSideToggle = card._isSeriesHidden(firstSeries);
  card._toggleSeriesVisibilityFromKey(firstSeries, { key: "Enter", stopPropagation() {}, preventDefault() {} });
  const restoredSvgOutput = card._renderSvg(model);
  const restoredPathCount = [...restoredSvgOutput.matchAll(/<path class="lp-series-line"/g)].length;
  const hiddenAfterKeyboardToggle = card._isSeriesHidden(firstSeries);
  card._setHoverPoint(firstSeries, { x: 10, y: 20, value: 1, label: "L1" }, loadedSession, 100, 100);

  const editor = new F1LapPositionProgressionCardEditor();
  editor.setConfig({});
  editor._formValueChanged({
    detail: {
      value: {
        top_limit: 5,
        chart_height: 400,
        show_full_name: true
      }
    }
  });

  process.stdout.write(JSON.stringify({
    sessionKeys: sessions.map((session) => session.key),
    defaultSelected: selected.key,
    unsupportedSelected: selectedUnsupported.key,
    unsupportedStatus: selectedUnsupported.status,
    wsMessages,
    gridOptions: card.getGridOptions(),
    defaultChartHeight: card.config.chart_height,
    renderedHasLegend: renderedCard.includes("lp-legend"),
    loadedSessionDrivers: loadedSession.drivers.length,
    seriesCodes: model.series.map((series) => series.code),
    topLimitCount: model.series.length,
    firstPath,
    initialPathCount,
    filteredPathCount,
    restoredPathCount,
    hiddenSideLabels,
    hiddenAfterSideToggle,
    hiddenAfterKeyboardToggle,
    leftSideLabels,
    rightSideLabels,
    gappedTotalSeriesCount: gappedModel.totalSeriesCount,
    gappedSeriesCount: gappedModel.series.length,
    gappedLeftLabels,
    gappedLeftSteps,
    gappedCurrentLabels,
    gappedPathCount,
    p1Y: coords ? Number(coords[1]) : null,
    p2Y: coords ? Number(coords[2]) : null,
    pathWithGap,
    tooltip: card._hoverPoint,
    editorConfig: editor.lastEvent.detail.config
  }));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""


def _read_card(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"card JS not found at {path}")
    return path.read_text(encoding="utf-8")


def _run_card_probe(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"card JS not found at {path}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for lap position card regression tests")

    env = os.environ.copy()
    env["F1_LAP_CARD_PATH"] = str(path)
    completed = subprocess.run(
        [node, "-e", NODE_CARD_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize("card_path", (BUNDLED_CARD_PATH, RUNTIME_CARD_PATH))
def test_lap_position_card_source_registration(card_path: Path) -> None:
    source = _read_card(card_path)

    assert "class F1LapPositionProgressionCard extends LitElement" in source
    assert "class F1LapPositionProgressionCardEditor extends LitElement" in source
    assert "DEFAULT_F1_LAP_POSITION_PROGRESSION_CONFIG" in source
    assert (
        "customElements.define('f1-lap-position-progression-card', F1LapPositionProgressionCard)"
        in source
    )
    assert (
        "customElements.define('f1-lap-position-progression-card-editor', "
        "F1LapPositionProgressionCardEditor)"
    ) in source
    assert "type: 'f1-lap-position-progression-card'" in source

    overlay_start = source.index("const F1_NO_SPOILER_CARD_CLASSES = [")
    overlay_end = source.index("F1_NO_SPOILER_CARD_CLASSES.forEach", overlay_start)
    assert "F1LapPositionProgressionCard" in source[overlay_start:overlay_end]


@pytest.mark.parametrize("card_path", (BUNDLED_CARD_PATH, RUNTIME_CARD_PATH))
def test_lap_position_card_model_and_interactions(card_path: Path) -> None:
    result = _run_card_probe(card_path)

    assert result["sessionKeys"] == [
        "race:2026:3",
        "sprint:2026:2",
        "race:2026:1",
    ]
    assert result["defaultSelected"] == "race:2026:1"
    assert result["unsupportedSelected"] == "sprint:2026:2"
    assert result["unsupportedStatus"] == "unsupported"
    assert result["wsMessages"] == [
        {
            "type": "f1_sensor/lap_position/session",
            "entity_id": "sensor.f1_lap_position_progression",
            "session_key": "race:2026:1",
        }
    ]
    assert result["gridOptions"] == {
        "columns": 12,
        "max_columns": 12,
        "min_columns": 6,
        "rows": 8,
        "min_rows": 6,
    }
    assert result["defaultChartHeight"] == 420
    assert result["renderedHasLegend"] is False
    assert result["loadedSessionDrivers"] == 3
    assert result["seriesCodes"] == ["NOR", "VER"]
    assert result["topLimitCount"] == 2
    assert result["leftSideLabels"] == ["VER", "NOR"]
    assert result["rightSideLabels"] == ["NORRIS", "VERSTAPPEN"]
    assert result["p2Y"] < result["p1Y"]
    assert result["firstPath"].startswith("M ")
    assert result["firstPath"].count("M ") == 2
    assert result["initialPathCount"] == 2
    assert result["filteredPathCount"] == 1
    assert result["restoredPathCount"] == 2
    assert result["hiddenAfterSideToggle"] is True
    assert result["hiddenAfterKeyboardToggle"] is False
    assert result["hiddenSideLabels"] == ["NOR", "NORRIS"]
    assert result["pathWithGap"].startswith("M 1.00 1.00 M 2.00 2.00")
    assert result["gappedTotalSeriesCount"] == 22
    assert result["gappedSeriesCount"] == 22
    assert result["gappedLeftLabels"][:6] == ["V01", "V02", "V03", "V04", "M05", "V05"]
    assert result["gappedLeftLabels"][14:17] == ["M15", "V14", "V15"]
    assert result["gappedLeftLabels"][-1] == "V20"
    assert len(set(result["gappedLeftSteps"])) == 1
    assert len(result["gappedCurrentLabels"]) == 22
    assert result["gappedPathCount"] == 20
    assert result["tooltip"]["name"] == "Lando Norris"
    assert result["tooltip"]["lap"] == "L1"
    assert result["tooltip"]["position"] == 1
    assert result["editorConfig"]["top_limit"] == 5
    assert result["editorConfig"]["chart_height"] == 400
    assert result["editorConfig"]["show_full_name"] is True
