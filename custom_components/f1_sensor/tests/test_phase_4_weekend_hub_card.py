"""Regression tests for the Phase 4 Weekend Hub and dashboard context."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_DIR = ROOT / "custom_components" / "f1_sensor" / "www" / "f1-sensor-live-data-card"
CARD_PATH = CARD_DIR / "f1-sensor-live-data-card.js"
CONTEXT_PATH = CARD_DIR / "platform" / "dashboard-context.js"
REGISTRY_PATH = CARD_DIR / "platform" / "card-registry.js"

NODE_CARD_PROBE = r"""
const fs = require("node:fs");
const source = fs.readFileSync(process.env.F1_CARD_PATH, "utf8");

function findMatchingBrace(text, openIndex) {
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let index = openIndex; index < text.length; index += 1) {
    const char = text[index];
    if (escaped) { escaped = false; continue; }
    if (char === "\\") { escaped = true; continue; }
    if (quote) { if (char === quote) quote = null; continue; }
    if (["'", '"', '`'].includes(char)) { quote = char; continue; }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  throw new Error("Unmatched class brace");
}

function extractClass(signature) {
  const start = source.indexOf(signature);
  if (start < 0) throw new Error(`Missing ${signature}`);
  const brace = source.indexOf("{", start);
  return source.slice(start, findMatchingBrace(source, brace) + 1);
}

function renderValue(value) {
  if (value == null || value === false) return "";
  if (Array.isArray(value)) return value.map(renderValue).join("");
  return String(value);
}

const Card = new Function(`
const DEFAULT_F1_THEME_MODE = "dark";
const DEFAULT_FONT_STYLE = "wide";
const F1_THEME_STYLES = {};
const css = (strings, ...values) => strings.reduce((out, part, index) => out + part + (index < values.length ? renderValue(values[index]) : ""), "");
const html = css;
const svg = css;
class LitElement {
  constructor() { this.isConnected = true; }
  connectedCallback() {}
  disconnectedCallback() { this.isConnected = false; }
  requestUpdate() {}
}
const normalizeThemeMode = (value) => ["dark", "light", "auto"].includes(value) ? value : "dark";
const applyF1ThemeMode = () => {};
const ensureF1Fonts = () => {};
const updateF1DashboardContext = () => {};
${renderValue.toString()}
${extractClass("class F1WeekendHubCard extends LitElement")}
return F1WeekendHubCard;
`)();

async function run() {
  const messages = [];
  let unsubscribeCalls = 0;
  const card = new Card();
  card.setConfig({ entry_id: "entry-4", default_view: "strategy", throttle_ms: 700 });
  card.hass = {
    connection: {
      subscribeMessage: async (callback, message) => {
        messages.push(message);
        callback({ status: "ready", phase: "before", drivers: [], capabilities: {}, timeline: { events: [] } });
        return () => { unsubscribeCalls += 1; };
      },
    },
    callWS: async (message) => {
      messages.push(message);
      return { series: [], coverage: { raw_home_assistant_states: "not_exposed" } };
    },
  };
  card.connectedCallback();
  await new Promise((resolve) => setImmediate(resolve));
  card._telemetrySelections = [{ driver_number: 4, lap_number: 12 }];
  await card._compareTelemetry();
  card.disconnectedCallback();
  return {
    messages,
    activeView: card._activeView,
    status: card._status,
    unsubscribeCalls,
  };
}

run()
  .then((result) => process.stdout.write(JSON.stringify(result)))
  .catch((error) => { console.error(error); process.exit(1); });
"""

NODE_CONTEXT_PROBE = r"""
const { pathToFileURL } = require("node:url");
const storage = new Map();
global.CustomEvent = class CustomEvent { constructor(type, init) { this.type = type; this.detail = init?.detail; } };
global.window = {
  localStorage: {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  },
  dispatchEvent: () => {},
};

class Card {
  constructor() { this.updates = 0; }
  connectedCallback() {}
  disconnectedCallback() {}
  requestUpdate() { this.updates += 1; }
}

async function run() {
  const module = await import(pathToFileURL(process.env.F1_CONTEXT_PATH));
  module.installF1DashboardContext(Card);
  const first = new Card();
  const second = new Card();
  first.connectedCallback();
  second.connectedCallback();
  module.updateF1DashboardContext({ driver_number: 4, gap_mode: "leader" }, "probe");
  const synchronized = [first._f1DashboardContext, second._f1DashboardContext];
  first.disconnectedCallback();
  const firstUpdates = first.updates;
  module.updateF1DashboardContext({ driver_number: 81 }, "probe");
  return {
    synchronized,
    disconnectedStopped: first.updates === firstUpdates,
    secondDriver: second._f1DashboardContext.driver_number,
    stored: JSON.parse(storage.get("f1-sensor-dashboard-context-v1")),
  };
}

run()
  .then((result) => process.stdout.write(JSON.stringify(result)))
  .catch((error) => { console.error(error); process.exit(1); });
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for Weekend Hub frontend tests")
    return node


def test_weekend_hub_registers_full_phase4_experience() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")
    registry = REGISTRY_PATH.read_text(encoding="utf-8")

    assert "class F1WeekendHubCard extends LitElement" in source
    assert "class F1WeekendHubCardEditor extends LitElement" in source
    assert "customElements.define('f1-weekend-hub-card', F1WeekendHubCard)" in source
    assert "'f1-weekend-hub-card'" in registry
    assert "platform/dashboard-context.js" in source
    assert "setInterval(" not in source[source.index("class F1WeekendHubCard") :]
    for method in (
        "_renderOverview",
        "_renderTimeline",
        "_renderStrategy",
        "_renderTelemetry",
        "_renderBattles",
    ):
        assert method in source
    assert "raw telemetry is never exposed as Home Assistant states" in source
    assert "Corner annotations remain unavailable" in source


def test_weekend_hub_uses_subscription_and_selected_telemetry_contracts() -> None:
    completed = subprocess.run(
        [_node(), "-e", NODE_CARD_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env={"F1_CARD_PATH": str(CARD_PATH)},
    )
    result = json.loads(completed.stdout)

    assert result["activeView"] == "strategy"
    assert result["status"] == "ready"
    assert result["unsubscribeCalls"] == 1
    assert result["messages"][0] == {
        "type": "f1_sensor/analysis/subscribe",
        "protocol_version": 1,
        "throttle_ms": 700,
        "entry_id": "entry-4",
    }
    assert result["messages"][1] == {
        "type": "f1_sensor/analysis/telemetry_compare",
        "selections": [{"driver_number": 4, "lap_number": 12}],
        "entry_id": "entry-4",
    }


def test_dashboard_context_synchronizes_cards_and_unsubscribes(tmp_path: Path) -> None:
    module_path = tmp_path / "dashboard-context.mjs"
    shutil.copyfile(CONTEXT_PATH, module_path)
    completed = subprocess.run(
        [_node(), "-e", NODE_CONTEXT_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env={"F1_CONTEXT_PATH": str(module_path)},
    )
    result = json.loads(completed.stdout)

    assert [context["driver_number"] for context in result["synchronized"]] == [4, 4]
    assert [context["gap_mode"] for context in result["synchronized"]] == [
        "leader",
        "leader",
    ]
    assert result["disconnectedStopped"] is True
    assert result["secondDriver"] == 81
    assert result["stored"]["driver_number"] == 81
