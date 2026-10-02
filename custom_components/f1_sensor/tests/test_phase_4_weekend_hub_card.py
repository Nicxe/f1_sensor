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
const normalizeF1GapValue = (value) => value == null ? null : String(value).trim() || null;
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
  card._snapshot = {
    provider: "replay",
    phase: "live",
    drivers: [
      { driver_number: 12, tla: "ANT" },
      { driver_number: 30, tla: "LAW" },
    ],
    timing: [
      { driver_number: 12, position: 6, gap_to_leader: "+64.900", interval_to_ahead: "+0.700" },
      { driver_number: 30, position: 7, gap_to_leader: "+65.598", interval_to_ahead: "+0.698" },
    ],
    capabilities: { telemetry_compare: "ready" },
    timeline: { events: [] },
  };
  card._f1DashboardContext = { driver_number: 30, gap_mode: "leader" };
  const focusedTiming = card._focusedTiming();
  const leaderGap = card._gapReferenceValue(focusedTiming);
  card._f1DashboardContext = { driver_number: 30, gap_mode: "ahead" };
  const aheadGap = card._gapReferenceValue(focusedTiming);
  card._f1DashboardContext = { driver_number: 30, gap_mode: "off" };
  const offGap = card._gapReferenceValue(focusedTiming);
  card._f1DashboardContext = { driver_number: 30, gap_mode: "leader" };
  const telemetryMarkup = card._renderTelemetry();
  const phaseCopy = card._phaseCopy();
  card._telemetrySelections = [{ driver_number: 4, lap_number: 12 }];
  await card._compareTelemetry();
  card.disconnectedCallback();
  return {
    messages,
    activeView: card._activeView,
    status: card._status,
    unsubscribeCalls,
    leaderGap,
    aheadGap,
    offGap,
    telemetryMarkup,
    phaseCopy,
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
    assert "installF1EntityAutoBinding(F1WeekendHubCard, {" in source
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
    assert result["leaderGap"] == "+65.598"
    assert result["aheadGap"] == "+0.698"
    assert result["offGap"] == "Hidden"
    assert "value=30 ?selected=true" in result["telemetryMarkup"]
    assert result["phaseCopy"] == [
        "Replay running",
        "Timing, strategy and race events update from replay",
    ]


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


@pytest.mark.parametrize(
    ("state", "label"),
    [
        ("paused", "Replay paused"),
        ("seeking", "Replay seeking"),
        ("playing", "Replay running"),
    ],
)
def test_weekend_hub_replay_status_matches_playback(state: str, label: str) -> None:
    result = _weekend_scenario(
        f"""
        card._snapshot = {{provider: 'replay', phase: 'live', replay: {{state: '{state}'}}}};
        return {{copy: card._phaseCopy()[0], shell: card._renderShell('')}};
        """
    )
    assert result["copy"] == label
    assert label in result["shell"]
    if state != "playing":
        assert "wh-live-badge live" not in result["shell"]


@pytest.mark.parametrize("driver", [1, 99])
def test_weekend_hub_filters_only_drivers_in_current_session(driver: int) -> None:
    result = _weekend_scenario(
        f"""
        card._f1DashboardContext = {{driver_number: {driver}}};
        card._receiveSnapshot({{status:'ready', provider:'replay', session_id:'new',
          drivers:[{{driver_number:1}}, {{driver_number:2}}],
          timing:[{{driver_number:1, position:1}}],
          timeline:{{events:[{{driver_numbers:[2], title:'Other driver'}}]}},
          strategy:{{stints:[{{driver_number:2}}]}}, capabilities:{{telemetry_compare:'ready'}} }});
        return {{events:card._filteredEvents().length,
          strategyWaiting:card._renderStrategy().includes('waiting for clean completed laps'),
          context:card._renderContext(), telemetry:card._renderTelemetry()}};
        """
    )
    assert result["events"] == (0 if driver == 1 else 1)
    assert result["strategyWaiting"] is (driver == 1)
    if driver == 99:
        assert "?selected=true>All drivers" in result["context"]
        assert "value=1 ?selected=true" in result["telemetry"]


@pytest.mark.parametrize("domain", ["switch", "input_boolean"])
def test_weekend_hub_spoiler_calls_correct_service(domain: str) -> None:
    result = _weekend_scenario(
        f"""
        const calls=[];
        const entity='{domain}.custom_spoiler';
        card.setConfig({{no_spoiler_entity:entity}});
        card.hass={{states:{{[entity]:{{state:'on'}}}}, callService:async(...args)=>calls.push(args)}};
        const hidden=card._spoilerActive();
        await card._toggleSpoiler();
        card.hass.states[entity].state='off';
        await card._toggleSpoiler();
        return {{hidden,calls}};
        """
    )
    assert result["hidden"] is True
    assert result["calls"] == [
        [domain, "turn_off", {"entity_id": f"{domain}.custom_spoiler"}],
        [domain, "turn_on", {"entity_id": f"{domain}.custom_spoiler"}],
    ]


def _weekend_scenario(body: str) -> dict:
    script = NODE_CARD_PROBE.split("async function run()", 1)[0]
    script += "\nconst card = new Card(); card.setConfig({});\n"
    script += f"(async()=>{{{body}}})().then(r=>console.log(JSON.stringify(r)));"
    completed = subprocess.run(
        [_node(), "-e", script],
        check=True,
        capture_output=True,
        text=True,
        env={"F1_CARD_PATH": str(CARD_PATH)},
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, "switch.renamed_spoiler"),
        ("input_boolean.f1_no_spoiler_mode", "input_boolean.f1_no_spoiler_mode"),
        ("switch.custom_spoiler", "switch.custom_spoiler"),
    ],
)
def test_weekend_hub_discovers_spoiler_switch_and_preserves_helpers(
    configured: str | None, expected: str
) -> None:
    result = _weekend_scenario(
        f"""
        const configured={json.dumps(configured)};
        if(configured) card.setConfig({{no_spoiler_entity:configured}});
        const bindingStart=source.indexOf('installF1EntityAutoBinding(F1WeekendHubCard, ');
        const bindingOpen=source.indexOf('{{',bindingStart);
        const bindingSource=source.slice(bindingOpen,findMatchingBrace(source,bindingOpen)+1);
        const bindings=new Function('return ('+bindingSource+')')();
        const {{pathToFileURL}}=require('node:url');
        const {{resolveF1CardEntities}}=await import(pathToFileURL(require('node:path').join(
          require('node:path').dirname(process.env.F1_CARD_PATH),'platform/entity-resolver.js')));
        card.hass={{connection:{{}},callWS:async()=>[{{entry_id:'entry',entities:{{no_spoiler_mode:'switch.renamed_spoiler'}}}}]}};
        const resolved=await resolveF1CardEntities(card.hass,card.config,bindings);
        card.config=resolved;
        card.hass.states={{[resolved.no_spoiler_entity]:{{state:'on'}}}};
        return {{entity:resolved.no_spoiler_entity,hidden:card._spoilerActive()}};
        """
    )
    assert result == {"entity": expected, "hidden": True}
