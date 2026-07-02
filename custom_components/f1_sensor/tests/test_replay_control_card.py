"""Regression tests for the replay control card seekbar."""

from __future__ import annotations

import json
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
LIT_MODULE_PATH = CARD_PATH.with_name("f1-lit-3.3.2.js")

NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.F1_REPLAY_CARD_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.F1_REPLAY_CARD_PATH, "utf8");

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

function renderValue(value) {
  if (value === null || value === undefined || value === false) return "";
  if (Array.isArray(value)) return value.map(renderValue).join("");
  return String(value);
}

const constantsStart = source.indexOf("const F1_REPLAY_ENTITY_DEFAULTS =");
const classStart = source.indexOf("class F1ReplayControlCard extends LitElement {", constantsStart);
const constantsSource = source.slice(constantsStart, classStart);
const classSource = extractClass("class F1ReplayControlCard extends LitElement {");

const harnessFactory = new Function(`
const DEFAULT_F1_THEME_MODE = "dark";
const F1_THEME_STYLES = {};
const css = (strings, ...values) => strings.reduce((out, part, index) => out + part + (index < values.length ? renderValue(values[index]) : ""), "");
const html = css;
class LitElement {
  dispatchEvent(event) {
    this.lastEvent = event;
  }
}
const getEntityStateWithFallback = (hass, entityId) => hass?.states?.[entityId] || null;
const applyF1ThemeMode = () => {};
const ensureF1Fonts = () => {};

${renderValue.toString()}
${constantsSource}
${classSource}

return { F1ReplayControlCard };
`);

const { F1ReplayControlCard } = harnessFactory();

function player(features = 2, state = "paused") {
  return {
    state,
    attributes: {
      supported_features: features,
      playback_position_s: 10,
      playback_total_s: 90,
      media_position: 10,
      media_duration: 90,
      selected_session: "Test GP - Race",
    },
  };
}

function buildCard(features = 2, state = "paused", config = {}) {
  const card = new F1ReplayControlCard();
  card.setConfig(config);
  const calls = [];
  card.hass = {
    states: {
      "media_player.f1_replay_player": player(features, state),
      "select.f1_replay_session": { state: "Test GP - Race", attributes: { options: ["Test GP - Race"] } },
    },
    callService: async (...args) => {
      calls.push(args);
    },
  };
  return { card, calls };
}

async function main() {
  let result;
  if (payload.action === "render_supported") {
    const { card } = buildCard(2);
    const rendered = card.render();
    result = {
      hasSeekInput: rendered.includes('class="rc-seek-input"') && rendered.includes('type="range"'),
      hasPassiveTrack: rendered.includes('class="rc-progress-track"'),
    };
  } else if (payload.action === "render_unsupported") {
    const { card } = buildCard(0);
    const rendered = card.render();
    result = {
      hasSeekInput: rendered.includes('class="rc-seek-input"'),
      hasPassiveTrack: rendered.includes('class="rc-progress-track"'),
    };
  } else if (payload.action === "show_progress_false") {
    const { card } = buildCard(2, "paused", { show_progress: false });
    const rendered = card.render();
    result = {
      hasSeekInput: rendered.includes('class="rc-seek-input"'),
      hasProgress: rendered.includes('class="rc-progress"'),
    };
  } else if (payload.action === "drag_behavior") {
    const { card, calls } = buildCard(2);
    const playerEntity = card.hass.states["media_player.f1_replay_player"];
    const playback = card._playback(null, playerEntity);
    card._handleSeekInput({ target: { value: "55" } }, playback);
    const callsAfterInput = calls.length;
    await card._handleSeekChange({ target: { value: "42" } }, playback, "paused");
    result = {
      previewAfterInput: card._clampPlaybackPosition(55, playback.total),
      callsAfterInput,
      callCount: calls.length,
      call: calls[0],
      previewCleared: card._seekPreviewPosition === null,
    };
  } else if (payload.action === "busy_suppresses_seek") {
    const { card, calls } = buildCard(2);
    const playback = card._playback(null, card.hass.states["media_player.f1_replay_player"]);
    card._seekBusy = true;
    await card._handleSeekChange({ target: { value: "42" } }, playback, "paused");
    card._seekBusy = false;
    await card._handleSeekChange({ target: { value: "42" } }, playback, "seeking");
    result = { callCount: calls.length };
  } else {
    throw new Error(`Unknown action: ${payload.action}`);
  }
  process.stdout.write(JSON.stringify(result));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
"""

NODE_MODULE_IMPORT_PROBE_SCRIPT = r"""
globalThis.window = globalThis;
globalThis.HTMLElement = class {};
globalThis.Document = function Document() {};
globalThis.Document.prototype = {};
globalThis.document = {
  createTreeWalker() {
    return {
      nextNode() {
        return null;
      },
    };
  },
  createComment() {
    return {};
  },
  createElement() {
    return {
      content: {},
      appendChild() {},
      setAttribute() {},
    };
  },
  head: {
    appendChild() {},
  },
  querySelector() {
    return null;
  },
};
globalThis.customElements = {
  defined: [],
  define(name) {
    this.defined.push(name);
  },
  get() {
    return undefined;
  },
};

import(`file://${process.argv[1]}/f1-sensor-live-data-card.js`)
  .then(() => {
    process.stdout.write(JSON.stringify({
      customCards: window.customCards.map((card) => card.type),
      defined: customElements.defined,
    }));
  })
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
"""


def _run_probe(action: str) -> dict:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for replay control card tests")

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env={
            "F1_REPLAY_CARD_PATH": str(CARD_PATH),
            "F1_REPLAY_CARD_PAYLOAD": json.dumps({"action": action}),
        },
    )
    return json.loads(completed.stdout)


def test_replay_control_card_uses_bundled_lit_module() -> None:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")

    source = CARD_PATH.read_text(encoding="utf-8")

    assert LIT_MODULE_PATH.is_file()
    assert "import { LitElement, html, css, svg } from './f1-lit-3.3.2.js';" in source
    assert "Home Assistant Lit globals are unavailable" not in source


def test_replay_control_card_module_loads_with_bundled_lit(tmp_path: Path) -> None:
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for replay control card tests")

    shutil.copyfile(CARD_PATH, tmp_path / CARD_PATH.name)
    shutil.copyfile(LIT_MODULE_PATH, tmp_path / LIT_MODULE_PATH.name)
    (tmp_path / "package.json").write_text('{"type":"module"}', encoding="utf-8")

    completed = subprocess.run(
        [node, "-e", NODE_MODULE_IMPORT_PROBE_SCRIPT, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert "f1-replay-control-card" in result["defined"]
    assert "f1-replay-control-card" in result["customCards"]


def test_replay_control_card_renders_seekbar_when_media_seek_supported() -> None:
    result = _run_probe("render_supported")

    assert result == {"hasSeekInput": True, "hasPassiveTrack": False}


def test_replay_control_card_falls_back_without_media_seek() -> None:
    result = _run_probe("render_unsupported")

    assert result == {"hasSeekInput": False, "hasPassiveTrack": True}


def test_replay_control_card_hides_progress_when_configured() -> None:
    result = _run_probe("show_progress_false")

    assert result == {"hasSeekInput": False, "hasProgress": False}


def test_replay_control_card_seeks_only_on_release() -> None:
    result = _run_probe("drag_behavior")

    assert result["callsAfterInput"] == 0
    assert result["callCount"] == 1
    assert result["call"] == [
        "media_player",
        "media_seek",
        {"entity_id": "media_player.f1_replay_player", "seek_position": 42},
    ]
    assert result["previewAfterInput"] == 55
    assert result["previewCleared"] is True


def test_replay_control_card_suppresses_seek_while_busy_or_seeking() -> None:
    result = _run_probe("busy_suppresses_seek")

    assert result == {"callCount": 0}
