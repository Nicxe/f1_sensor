"""Regression tests for the F1 track map card configuration helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

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

NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.TRACK_MAP_CARD_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.TRACK_MAP_CARD_PATH, "utf8");

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

const cardClass = extractClass("class F1TrackMapCard extends LitElement");
const editorClass = extractClass("class F1TrackMapCardEditor extends LitElement");

const Harness = new Function(
  `
  class LitElement {
    constructor() {
      this.dataset = {};
      this.isConnected = true;
    }
    requestUpdate() {}
  }

  const css = () => "";
  const html = () => "";
  const F1_THEME_STYLES = "";
  const DEFAULT_F1_THEME_MODE = "dark";
  const normalizeThemeMode = (mode) => ["dark", "light", "auto"].includes(String(mode || "dark").toLowerCase())
    ? String(mode || "dark").toLowerCase()
    : "dark";
  const applyF1ThemeMode = (element, config, hass = null) => {
    element.dataset.themeMode = normalizeThemeMode(config?.theme_mode);
    element.dataset.effectiveTheme = isEffectiveLightTheme(hass, config) ? "light" : "dark";
  };
  const isEffectiveLightTheme = (_hass, config) => normalizeThemeMode(config?.theme_mode) === "light";
  const measureRenderedCardWidth = (host) => host._testWidth || 0;
  const getEntityStateWithFallback = (hass, entityId) => hass?.states?.[entityId] || null;
  const isUnavailableLikeEntityState = (entityState) => ["unknown", "unavailable"].includes(String(entityState?.state || "").toLowerCase());
  const ensureF1Fonts = () => {};
  const renderThemeModeSelect = () => "";
  const renderEditorSelect = () => "";
  const TRACK_STATUS_COLORS = {
    CLEAR: "#34c759",
    YELLOW: "#ffd60a",
    VSC: "#ff9500",
    SC: "#ff9500",
    RED: "#ff3b30",
  };
  const TRACK_STATUS_LIGHT_COLORS = TRACK_STATUS_COLORS;
  const TRACK_STATUS_LABELS = {
    CLEAR: "Track Clear",
    YELLOW: "Yellow Flag",
    VSC: "Virtual SC",
    SC: "Safety Car",
    RED: "Red Flag",
  };
  const document = {
    createElement(tagName) {
      return { tagName };
    },
  };

  ${cardClass}
  ${editorClass}

  return { F1TrackMapCard, F1TrackMapCardEditor };
`,
)();

const card = new Harness.F1TrackMapCard();
card.hass = payload.hass || { states: {} };
card._testWidth = payload.width || 0;
card.setConfig(payload.config || {});
if (payload.snapshot !== undefined) {
  card._snapshot = payload.snapshot;
  card._status = payload.status || payload.snapshot?.status || "not_loaded";
}

const result = {
  config: card.config,
  stub: Harness.F1TrackMapCard.getStubConfig(),
  editorTag: Harness.F1TrackMapCard.getConfigElement().tagName,
  lapData: card._lapData(),
  trackStatus: card._trackStatusInfo(),
  labelTla: card._driverLabel({ tla: "VER", racing_number: "1" }, "tla"),
  labelNumber: card._driverLabel({ tla: "VER", racing_number: "1" }, "number"),
  labelOff: card._driverLabel({ tla: "VER", racing_number: "1" }, "off"),
  emptyState: card._emptyState(),
  presentation: card._presentationState(),
  layoutMode: card._effectiveLayoutMode(),
  visibleDrivers: card._visibleDrivers(payload.drivers || []).map((driver) => driver.racing_number),
  displayDrivers: card._displayDrivers(payload.drivers || []).map((driver) => driver.racing_number),
};

if (payload.motion) {
  const motion = payload.motion;
  card._snapshot = motion.snapshot || null;
  card._status = motion.status || motion.snapshot?.status || "not_loaded";
  card._driverSamples = new Map(
    (motion.samples || []).map(([key, samples]) => [key, samples]),
  );
  card._renderClockAt = motion.renderClockAt || 0;
  card._nowMs = () => motion.nowMs;
  result.hasActiveDriverMotion = card._hasActiveDriverMotion();
}

process.stdout.write(JSON.stringify(result));
"""


def _run_probe(payload: dict) -> dict:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for track map card config tests")

    env = os.environ.copy()
    env["TRACK_MAP_CARD_PATH"] = str(CARD_PATH)
    env["TRACK_MAP_CARD_PAYLOAD"] = json.dumps(payload)

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    return json.loads(completed.stdout)


def test_track_map_card_defaults_are_backward_compatible() -> None:
    """A bare card config should still work and now expose editor defaults."""
    result = _run_probe({"config": {}})

    assert result["config"]["title"] == "F1 Track Map"
    assert result["config"]["entry_id"] == "auto"
    assert result["config"]["throttle_ms"] == 100
    assert result["config"]["interpolation_ms"] == "auto"
    assert result["config"]["invert_y"] is True
    assert result["config"]["driver_label_mode"] == "tla"
    assert result["config"]["show_labels"] is True
    assert result["config"]["lap_count_entity"] == "auto"
    assert result["config"]["driver_positions_entity"] == "auto"
    assert result["config"]["track_status_entity"] == "auto"
    assert result["config"]["track_status_line_mode"] == "accent"
    assert result["config"]["layout_mode"] == "auto"
    assert result["stub"]["type"] == "custom:f1-track-map-card"
    assert result["stub"]["driver_positions_entity"] == "auto"
    assert result["editorTag"] == "f1-track-map-card-editor"
    assert result["labelTla"] == "VER"
    assert result["labelNumber"] == "1"
    assert result["labelOff"] == ""


def test_track_map_card_keeps_legacy_show_labels_false() -> None:
    """Old YAML using show_labels: false should map to the new label mode."""
    result = _run_probe({"config": {"show_labels": False}})

    assert result["config"]["driver_label_mode"] == "off"
    assert result["config"]["show_labels"] is False


def test_track_map_card_normalizes_invalid_display_options() -> None:
    """Numeric and option inputs should be clamped to safe values."""
    result = _run_probe(
        {
            "config": {
                "throttle_ms": 9000,
                "interpolation_ms": -50,
                "driver_label_mode": "bad",
                "track_status_line_mode": "bad",
                "layout_mode": "bad",
                "theme_mode": "bad",
            }
        }
    )

    assert result["config"]["throttle_ms"] == 5000
    assert result["config"]["interpolation_ms"] == 0
    assert result["config"]["driver_label_mode"] == "tla"
    assert result["config"]["track_status_line_mode"] == "accent"
    assert result["config"]["layout_mode"] == "auto"
    assert result["config"]["theme_mode"] == "dark"


def test_track_map_card_resolves_auto_lap_and_track_status_entities() -> None:
    """The card should pick common F1 Sensor entity ids when set to auto."""
    result = _run_probe(
        {
            "config": {},
            "hass": {
                "states": {
                    "sensor.f1_session_f1_race_lap_count": {
                        "state": "12",
                        "attributes": {"total_laps": 57},
                    },
                    "sensor.f1_session_f1_track_status": {
                        "state": "YELLOW",
                        "attributes": {},
                    },
                }
            },
        }
    )

    assert result["lapData"] == {"current": 12, "total": 57}
    assert result["trackStatus"]["status"] == "YELLOW"
    assert result["trackStatus"]["label"] == "Yellow Flag"
    assert result["trackStatus"]["color"] == "#ffd60a"
    assert result["trackStatus"]["alert"] is True


def test_track_map_card_empty_entity_values_disable_optional_context() -> None:
    """An explicitly empty optional entity should disable auto lookup."""
    result = _run_probe(
        {
            "config": {
                "lap_count_entity": "",
                "track_status_entity": "",
            },
            "hass": {
                "states": {
                    "sensor.f1_session_f1_race_lap_count": {
                        "state": "12",
                        "attributes": {"total_laps": 57},
                    },
                    "sensor.f1_session_f1_track_status": {
                        "state": "RED",
                        "attributes": {},
                    },
                }
            },
        }
    )

    assert result["lapData"] is None
    assert result["trackStatus"] is None


def test_track_map_card_reports_specific_empty_states() -> None:
    """Empty states should distinguish missing live positions from no session."""
    no_session = _run_probe(
        {
            "snapshot": {
                "source": "live",
                "status": "no_session",
                "session": None,
                "drivers": [],
                "track": None,
            }
        }
    )
    waiting_positions = _run_probe(
        {
            "snapshot": {
                "source": "live",
                "status": "no_position_data",
                "session": {"meeting_name": "Miami Grand Prix", "session_name": "Race"},
                "drivers": [],
                "track": {"points": [[0, 0], [1, 1]]},
            }
        }
    )

    assert no_session["emptyState"]["title"] == "No live timing session loaded"
    assert waiting_positions["emptyState"]["title"] == "Waiting for live car positions"


def test_track_map_card_keeps_live_driver_motion_active_until_latest_sample() -> None:
    """Live snapshots should keep redrawing while visual smoothing is in flight."""
    samples = [
        [
            "1",
            [
                {"x": 100, "y": 50, "arrivalAt": 1000},
                {"x": 200, "y": 150, "arrivalAt": 2000},
            ],
        ]
    ]
    active_live = _run_probe(
        {
            "motion": {
                "nowMs": 2200,
                "samples": samples,
                "snapshot": {
                    "source": "live",
                    "status": "active",
                    "stale": False,
                    "replay_state": None,
                },
            },
        }
    )
    stale_live = _run_probe(
        {
            "motion": {
                "nowMs": 2200,
                "samples": samples,
                "snapshot": {
                    "source": "live",
                    "status": "stale",
                    "stale": True,
                    "replay_state": None,
                },
            },
        }
    )
    paused_replay = _run_probe(
        {
            "motion": {
                "nowMs": 2200,
                "samples": samples,
                "snapshot": {
                    "source": "replay",
                    "status": "active",
                    "stale": False,
                    "replay_state": "paused",
                },
            },
        }
    )

    assert active_live["hasActiveDriverMotion"] is True
    assert stale_live["hasActiveDriverMotion"] is False
    assert paused_replay["hasActiveDriverMotion"] is False


def test_track_map_card_hides_stale_live_positions() -> None:
    """Stale live snapshots should not leave old cars visible on the map."""
    result = _run_probe(
        {
            "snapshot": {
                "source": "live",
                "status": "stale",
                "stale": True,
                "session": {
                    "meeting_name": "Monaco Grand Prix",
                    "session_name": "Qualifying",
                },
                "drivers": [
                    {"racing_number": "1", "status": "OnTrack"},
                    {"racing_number": "4", "status": "OnTrack"},
                ],
                "track": {"points": [[0, 0], [1, 1]]},
            },
            "drivers": [
                {"racing_number": "1", "status": "OnTrack"},
                {"racing_number": "4", "status": "OnTrack"},
            ],
        }
    )

    assert result["emptyState"]["title"] == "No active live session"
    assert result["emptyState"]["detail"] == (
        "Live timing is waiting for the next active session."
    )
    assert result["presentation"] == {
        "hide_live_metadata": True,
        "session": {},
        "show_badges": False,
        "show_footer": False,
        "show_session_info": False,
    }
    assert result["visibleDrivers"] == []
    assert result["displayDrivers"] == []


def test_track_map_card_hides_retired_drivers() -> None:
    """Drivers marked OUT should not remain visible on the track map."""
    result = _run_probe(
        {
            "drivers": [
                {"racing_number": "1", "status": "OnTrack"},
                {"racing_number": "2", "status": "OUT"},
                {"racing_number": "3", "status": "retired"},
                {"racing_number": "4", "retired": True},
                {"racing_number": "5", "status": "Stopped"},
            ],
        }
    )

    assert result["visibleDrivers"] == ["1", "5"]
    assert result["displayDrivers"] == ["1", "5"]


def test_track_map_card_uses_driver_positions_status_for_out_filter() -> None:
    """Driver positions OUT status should remove the matching car from the map."""
    result = _run_probe(
        {
            "drivers": [
                {"racing_number": "1", "status": "OnTrack"},
                {"racing_number": "2", "status": "OnTrack"},
                {"racing_number": "3", "tla": "SAI", "status": "OnTrack"},
            ],
            "hass": {
                "states": {
                    "sensor.f1_drivers_f1_driver_positions": {
                        "state": "25",
                        "attributes": {
                            "drivers": [
                                {
                                    "racing_number": "2",
                                    "status": "out",
                                    "retired": True,
                                },
                                {"tla": "SAI", "status": "out"},
                            ]
                        },
                    },
                }
            },
        }
    )

    assert result["visibleDrivers"] == ["1"]
    assert result["displayDrivers"] == ["1"]


def test_track_map_card_is_registered_as_configurable() -> None:
    """The custom card registry should expose the editor in Lovelace."""
    source = CARD_PATH.read_text()
    marker = "type: 'f1-track-map-card'"
    start = source.index(marker)
    end = source.index("});", start)
    block = source[start:end]

    assert (
        "customElements.define('f1-track-map-card-editor', F1TrackMapCardEditor)"
        in source
    )
    assert "configurable: true" in block
    assert "configurable: false" not in block


def test_track_map_editor_uses_ha_form_for_visible_inputs() -> None:
    """The editor should not rely on raw textfield elements hidden in HA."""
    source = CARD_PATH.read_text()
    start = source.index("class F1TrackMapCardEditor extends LitElement")
    end = source.index("installSectionsAutoHeight", start)
    editor_block = source[start:end]

    assert "ha-textfield" not in editor_block
    assert "Visual motion smoothing for car markers" in editor_block
    assert "{ text: {} }" in editor_block
    assert "{ number: { min: 0, max: 5000, mode: 'box' } }" in editor_block
