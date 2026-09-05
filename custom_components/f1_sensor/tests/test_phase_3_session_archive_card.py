"""Regression tests for the Phase 3 archive mode in the results card."""

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
REGISTER_PATH = CARD_PATH.with_name("register.js")
REGISTRY_PATH = CARD_PATH.parent / "platform" / "card-registry.js"

NODE_PROBE = r"""
const fs = require("node:fs");
const action = process.env.F1_ARCHIVE_ACTION;
const source = fs.readFileSync(process.env.F1_ARCHIVE_CARD_PATH, "utf8");

function findMatchingBrace(text, openIndex) {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    if (text[index] === "{") depth += 1;
    if (text[index] === "}") {
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
const F1_THEME_STYLES = {};
const css = (strings, ...values) => strings.reduce((out, part, index) => out + part + (index < values.length ? renderValue(values[index]) : ""), "");
const html = css;
class LitElement {
  constructor() { this.isConnected = true; }
  connectedCallback() {}
  disconnectedCallback() {}
  requestUpdate() {}
}
const normalizeThemeMode = (value) => ["dark", "light", "auto"].includes(value) ? value : "dark";
const normalizeFontStyle = (value) => value || "wide";
const applyF1ThemeMode = () => {};
const ensureF1Fonts = () => {};
const getResponsiveLayoutMode = () => "wide";
const getEntityStateWithFallback = () => null;
const resolveEntityIdWithFallback = () => null;
const asEntityList = (value) => Array.isArray(value) ? value : [];
const hasCollectionEntries = (value) => Array.isArray(value) && value.length > 0;
const isNoSpoilerModeActive = () => false;
const getTeamLogoMeta = () => null;
const isEffectiveLightTheme = () => false;
const handleTeamLogoError = () => {};
${renderValue.toString()}
${extractClass("class F1LastRaceResultsCard extends LitElement {")}
return F1LastRaceResultsCard;
`)();

const catalog = {
  year: 2023,
  meetings: [{
    meeting_key: "jolpica:2023:15",
    round: 15,
    name: "Singapore Grand Prix",
    sessions: [
      {
        session_key: "jolpica:2023:15:practice:Practice 1",
        name: "Practice 1",
        kind: "practice",
        provider: "jolpica",
        final: true,
        coverage: { results: "not_available_from_jolpica" },
      },
      {
        session_key: "jolpica:2023:15:qualifying:Qualifying",
        name: "Qualifying",
        kind: "qualifying",
        provider: "jolpica",
        final: true,
        coverage: { results: "available" },
      },
      {
        session_key: "jolpica:2023:15:race:Race",
        name: "Race",
        kind: "race",
        provider: "jolpica",
        final: true,
        coverage: { results: "available" },
      },
    ],
  }],
  coverage: { provider: "jolpica", historical_source: "jolpica_only" },
  attribution: "Data provided by Jolpica (jolpi.ca)",
};

async function lazyProbe() {
  const messages = [];
  const card = new Card();
  card.setConfig({ history_year: 2023 });
  card.hass = { callWS: async (message) => { messages.push(message); return catalog; } };
  card.connectedCallback();
  await new Promise((resolve) => setImmediate(resolve));
  return { messages, scope: card._resultScope, status: card._archiveStatus };
}

async function requestProbe() {
  const messages = [];
  const card = new Card();
  card.setConfig({ history_year: 2023, history_entry_id: "entry-1" });
  card.hass = { callWS: async (message) => {
    messages.push(message);
    if (message.type.endsWith("/catalog")) return catalog;
    return {
      results: [{ position: 1, driver_acronym: "NOR" }],
      coverage: { provider: "jolpica" },
      attribution: "Data provided by Jolpica (jolpi.ca)",
    };
  } };
  await card._switchResultScope("archive");
  return { messages, status: card._archiveStatus, resultCount: card._archiveResults.results.length };
}

async function staleProbe() {
  let resolveFirst;
  const first = new Promise((resolve) => { resolveFirst = resolve; });
  let catalogCalls = 0;
  const card = new Card();
  card.setConfig({ history_year: 2023 });
  card.hass = { callWS: async (message) => {
    if (!message.type.endsWith("/catalog")) throw new Error("Unexpected request");
    catalogCalls += 1;
    return catalogCalls === 1 ? first : { year: 2023, meetings: [] };
  } };
  const oldRequest = card._loadArchiveCatalog();
  await card._loadArchiveCatalog();
  resolveFirst(catalog);
  await oldRequest;
  return { status: card._archiveStatus, meetingCount: card._archiveCatalog.meetings.length };
}

async function yearNavigationProbe() {
  const messages = [];
  const card = new Card();
  card.setConfig({ history_year: 2023 });
  card.hass = { callWS: async (message) => {
    messages.push(message);
    return { year: message.year, meetings: [] };
  } };
  card._resultScope = "archive";
  await card._changeArchiveYear(-1);
  return {
    selectedYear: card._archiveYear,
    configuredYear: card.config.history_year,
    requestedYear: messages[0].year,
  };
}

async function columnsProbe() {
  const card = new Card();
  card.setConfig({});
  return {
    current: card._columns("wide").map((column) => column.key),
    race: card._archiveColumns("wide", { kind: "race" }).map((column) => column.key),
    qualifying: card._archiveColumns("wide", { kind: "qualifying" }).map((column) => column.key),
    labels: {
      race: card._sessionTypeLabel({ kind: "race" }),
      sprint: card._sessionTypeLabel({ kind: "sprint" }),
      qualifying: card._sessionTypeLabel({ kind: "qualifying" }),
    },
  };
}

const probes = {
  lazy: lazyProbe,
  requests: requestProbe,
  stale: staleProbe,
  year: yearNavigationProbe,
  columns: columnsProbe,
};
probes[action]()
  .then((result) => process.stdout.write(JSON.stringify(result)))
  .catch((error) => { console.error(error); process.exit(1); });
"""


def _run_probe(action: str) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for results card archive tests")
    completed = subprocess.run(
        [node, "-e", NODE_PROBE],
        check=True,
        capture_output=True,
        text=True,
        env={
            "F1_ARCHIVE_ACTION": action,
            "F1_ARCHIVE_CARD_PATH": str(CARD_PATH),
        },
    )
    return json.loads(completed.stdout)


def test_results_card_does_not_load_history_in_current_season_mode() -> None:
    result = _run_probe("lazy")

    assert result == {"messages": [], "scope": "current", "status": "idle"}


def test_results_card_archive_uses_only_catalog_and_results_contracts() -> None:
    result = _run_probe("requests")

    assert result["status"] == "ready"
    assert result["resultCount"] == 1
    assert [message["type"] for message in result["messages"]] == [
        "f1_sensor/history/catalog",
        "f1_sensor/history/results",
    ]
    assert all(message["entry_id"] == "entry-1" for message in result["messages"])
    assert result["messages"][0]["year"] == 2023
    assert result["messages"][1]["session_key"].endswith(":race:Race")
    assert all("provider" not in message for message in result["messages"])


def test_results_card_archive_ignores_stale_catalog_responses() -> None:
    result = _run_probe("stale")

    assert result == {"status": "empty", "meetingCount": 0}


def test_results_card_archive_navigates_without_overwriting_start_year() -> None:
    result = _run_probe("year")

    assert result == {
        "selectedYear": 2022,
        "configuredYear": 2023,
        "requestedYear": 2022,
    }


def test_results_card_archive_uses_session_specific_columns() -> None:
    result = _run_probe("columns")

    assert result["current"] == [
        "position",
        "logo",
        "tla",
        "grid",
        "delta",
        "laps",
        "time_gap",
        "points",
        "status",
    ]
    assert result["race"] == [
        "position",
        "tla",
        "grid",
        "delta",
        "laps",
        "time_gap",
        "points",
        "status",
    ]
    assert result["qualifying"] == ["position", "tla", "q1", "q2", "q3"]
    assert result["labels"] == {
        "race": "RACE",
        "sprint": "SPRINT",
        "qualifying": "QUALIFYING",
    }


def test_results_card_selects_the_loaded_meeting_and_session_options() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert (
        "?selected=${String(meeting.meeting_key) === "
        "String(this._archiveMeetingKey)}" in source
    )
    assert (
        "?selected=${String(session.session_key) === "
        "String(this._archiveSessionKey)}" in source
    )


def test_separate_archive_card_is_replaced_by_compatibility_alias() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")
    registry = REGISTRY_PATH.read_text(encoding="utf-8")

    assert "class F1SessionArchiveCard extends LitElement" not in source
    assert (
        "class F1SessionArchiveCardCompatibility extends F1LastRaceResultsCard"
        in source
    )
    assert (
        "customElements.define('f1-session-archive-card', F1SessionArchiveCardCompatibility)"
        in source
    )
    assert "f1-session-archive-card-editor" not in source
    assert "['f1-session-archive-card'" not in registry


def test_results_card_archive_hides_raw_history_and_coverage_panels() -> None:
    source = CARD_PATH.read_text(encoding="utf-8")

    assert "Historical lap timing" not in source
    assert "Detailed telemetry coverage" not in source
    assert "Timed records" not in source
    assert "Speed traps</span><strong>Not provided" not in source
    assert "f1_sensor/history/laps" not in source
    assert "Current season" in source
    assert "Archive" in source
    assert (
        "aria-label=${`${meeting?.name || ''} ${session?.name || ''} classification`}"
        in source
    )


def test_card_loader_waits_for_and_cache_busts_the_results_module() -> None:
    source = REGISTER_PATH.read_text(encoding="utf-8")

    assert "new URL(import.meta.url).searchParams.get('v')" in source
    assert "await import(`./f1-sensor-live-data-card.js${cacheSuffix}`)" in source
