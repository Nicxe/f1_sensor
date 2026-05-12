"""Regression tests for live timing card session visibility rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
CARD_PATH = ROOT / "www" / "f1-sensor-live-data-card.js"

NODE_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const payload = JSON.parse(process.env.CARD_VISIBILITY_PAYLOAD || "{}");
const source = fs.readFileSync(process.env.CARD_VISIBILITY_PATH, "utf8");

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

function extractMethod(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Method signature not found: ${signature}`);
  }
  const braceStart = source.indexOf("{", start);
  const end = findMatchingBrace(source, braceStart);
  return source.slice(start, end + 1);
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

const helperSources = [
  extractConst("const resolveEntityIdWithFallback = (hass, entityId) =>"),
  extractConst("const getEntityStateWithFallback = (hass, entityId) =>"),
  extractConst("const getStateAgeSeconds = (state, field = 'last_changed') =>"),
  extractStatement("const POST_SESSION_RETENTION_SECONDS ="),
  extractStatement("const TERMINAL_SESSION_STATUSES ="),
  extractStatement("const isTerminalSessionStatus = (sessionStatusState) =>"),
  extractConst("const getPostSessionAgeSeconds = (sessionState, sessionStatusState, stateMatchesLabel) =>"),
  extractConst("const isSessionWithinPostSessionRetention = ("),
  extractConst("const shouldKeepSessionCardVisible = ("),
];

const methodSources = [
  extractMethod("_isQualifyingSession(sessionState, sessionStatusState) {"),
  extractMethod("_isQualifyingLikeLabel(label) {"),
  extractMethod("_isPracticeSession(sessionState, sessionStatusState) {"),
  extractMethod("_isPracticeLikeLabel(label) {"),
  extractMethod("_isRaceSession(sessionState, sessionStatusState) {"),
  extractMethod("_isRaceLikeLabel(label) {"),
];

const Harness = new Function(
  `
  const LEGACY_ENTITY_ID_FALLBACKS = {};

  ${helperSources.join("\n\n")}

  class Harness {
    constructor(payload) {
      this.hass = { states: payload.hassStates || {} };
      this.config = payload.config || {};
    }

    ${methodSources.join("\n\n")}
  }

  return Harness;
`,
)();

const harness = new Harness(payload);
const result = harness[payload.methodName](
  payload.sessionState,
  payload.sessionStatusState,
);

process.stdout.write(JSON.stringify({ result }));
"""

SNAPSHOT_PROBE_SCRIPT = r"""
const fs = require("node:fs");

const source = fs.readFileSync(process.env.CARD_VISIBILITY_PATH, "utf8");

function extractAssignment(signature) {
  const start = source.indexOf(signature);
  if (start === -1) {
    throw new Error(`Assignment not found: ${signature}`);
  }
  let parens = 0;
  let braces = 0;
  let brackets = 0;
  for (let idx = start; idx < source.length; idx += 1) {
    const ch = source[idx];
    if (ch === "(") parens += 1;
    if (ch === ")") parens -= 1;
    if (ch === "{") braces += 1;
    if (ch === "}") braces -= 1;
    if (ch === "[") brackets += 1;
    if (ch === "]") brackets -= 1;
    if (ch === ";" && parens === 0 && braces === 0 && brackets === 0) {
      return source.slice(start, idx + 1);
    }
  }
  throw new Error(`Assignment semicolon not found: ${signature}`);
}

const HelperHarness = new Function(
  `
  ${extractAssignment("const meaningfulSessionLabel = (value) =>")}
  ${extractAssignment("const resolveSessionSnapshotKey = (sessionState, fallbackLabel = '') =>")}
  ${extractAssignment("const cloneTimingSnapshotRows = (rows) =>")}
  ${extractAssignment("const syncTimingSnapshotSession = (card, sessionKey) =>")}
  ${extractAssignment("const rememberTimingSnapshot = (card, sessionKey, payload) =>")}
  ${extractAssignment("const getRetainedTimingSnapshot = (card, sessionKey, retain) =>")}

  return {
    resolveSessionSnapshotKey,
    syncTimingSnapshotSession,
    rememberTimingSnapshot,
    getRetainedTimingSnapshot,
  };
`,
)();

const card = {};
const key = HelperHarness.resolveSessionSnapshotKey({
  state: "Race",
  attributes: {
    meeting_key: "miami-2026",
    start: "2026-05-03T20:00:00Z",
  },
});
const rows = [{ tla: "VER", team_logo: { src: "logo-a", fallback: "logo-b" } }];
HelperHarness.rememberTimingSnapshot(card, key, { rows, title: "Race Lap 57" });
rows[0].tla = "HAM";
rows[0].team_logo.src = "changed";
const retained = HelperHarness.getRetainedTimingSnapshot(card, key, true);
const retainedBeforeMutation = {
  ...retained,
  rows: retained.rows.map((row) => ({
    ...row,
    team_logo: row.team_logo ? { ...row.team_logo } : row.team_logo,
  })),
};
retained.rows[0].tla = "NOR";
const retainedAgain = HelperHarness.getRetainedTimingSnapshot(card, key, true);
HelperHarness.syncTimingSnapshotSession(card, "Race|other-session|2026-05-04T20:00:00Z");
const mismatched = HelperHarness.getRetainedTimingSnapshot(card, key, true);

process.stdout.write(JSON.stringify({
  key,
  retained: retainedBeforeMutation,
  retainedAgain,
  mismatched,
}));
"""


def _iso_seconds_ago(seconds: int) -> str:
    """Return an ISO timestamp in UTC for a time in the recent past."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def _build_config(prefix: str, method_name: str) -> dict[str, str]:
    """Build a minimal card config matching the tested card kind."""
    base = {
        "session_entity": f"sensor.{prefix}_current_session",
        "session_status_entity": f"sensor.{prefix}_session_status",
        "positions_entity": f"sensor.{prefix}_driver_positions",
    }
    if method_name == "_isRaceSession":
        base["lap_count_entity"] = f"sensor.{prefix}_race_lap_count"
    return base


def _run_visibility_probe(
    *,
    method_name: str,
    session_label: str,
    session_status: str,
    age_seconds: int,
    current_session_state: str = "unknown",
    last_label: str | None = None,
    session_status_age_seconds: int = 5,
    live_delay: int | None = None,
    prefix: str = "f1",
) -> bool:
    """Execute live card session gating directly from the JS source."""
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for live card visibility regression tests")

    config = _build_config(prefix, method_name)
    session_attrs = {}
    if last_label is not None:
        session_attrs["last_label"] = last_label
    elif session_label:
        session_attrs["last_label"] = session_label
    session_state = {
        "state": current_session_state,
        "attributes": session_attrs,
        "last_changed": _iso_seconds_ago(age_seconds),
    }
    session_status_state = {
        "state": session_status,
        "attributes": {},
        "last_changed": _iso_seconds_ago(session_status_age_seconds),
    }
    hass_states = {
        config["session_entity"]: session_state,
        config["session_status_entity"]: session_status_state,
        config["positions_entity"]: {"state": "ready", "attributes": {}},
    }
    if "lap_count_entity" in config:
        hass_states[config["lap_count_entity"]] = {"state": "57", "attributes": {}}
    if live_delay is not None:
        hass_states[f"number.{prefix}_live_delay"] = {
            "state": str(live_delay),
            "attributes": {},
        }

    env = os.environ.copy()
    env["CARD_VISIBILITY_PATH"] = str(CARD_PATH)
    env["CARD_VISIBILITY_PAYLOAD"] = json.dumps(
        {
            "methodName": method_name,
            "config": config,
            "hassStates": hass_states,
            "sessionState": session_state,
            "sessionStatusState": session_status_state,
        }
    )

    completed = subprocess.run(
        [node, "-e", NODE_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    return json.loads(completed.stdout)["result"] is True


def test_qualifying_card_stays_visible_for_post_session_retention() -> None:
    """Finished qualifying should stay visible for the fixed post-session window."""
    assert (
        _run_visibility_probe(
            method_name="_isQualifyingSession",
            session_label="Qualifying",
            session_status="finished",
            age_seconds=599,
            live_delay=0,
            prefix="custom_qualifying",
        )
        is True
    )


def test_qualifying_card_hides_after_post_session_retention_expires() -> None:
    """Finished qualifying should disappear after the fixed retention window."""
    assert (
        _run_visibility_probe(
            method_name="_isQualifyingSession",
            session_label="Qualifying",
            session_status="finished",
            age_seconds=601,
            live_delay=300,
            prefix="custom_qualifying",
        )
        is False
    )


def test_qualifying_card_keeps_break_fallback_behavior() -> None:
    """Qualifying breaks must still keep the card visible after label fallback."""
    assert (
        _run_visibility_probe(
            method_name="_isQualifyingSession",
            session_label="Qualifying",
            session_status="break",
            age_seconds=600,
            live_delay=0,
            prefix="custom_break",
        )
        is True
    )


def test_practice_card_hides_after_post_session_retention_expires() -> None:
    """Practice timing should disappear once the fixed retention window has elapsed."""
    assert (
        _run_visibility_probe(
            method_name="_isPracticeSession",
            session_label="Practice 2",
            session_status="finished",
            age_seconds=601,
            live_delay=0,
            prefix="custom_practice",
        )
        is False
    )


def test_race_card_stays_visible_during_finalised_grace() -> None:
    """Race timing should remain visible during the post-session finalised window."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            session_status="finalised",
            age_seconds=599,
            live_delay=0,
            prefix="custom_race",
        )
        is True
    )


def test_race_card_stays_visible_when_session_reaches_ended() -> None:
    """The late ended marker should retain race timing during the fixed window."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            session_status="ended",
            age_seconds=599,
            live_delay=180,
            prefix="custom_ended",
        )
        is True
    )


def test_race_card_hides_when_live_delay_would_exceed_retention() -> None:
    """Live delay must not extend card visibility beyond the fixed retention."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            session_status="finished",
            age_seconds=601,
            live_delay=300,
            prefix="custom_delay_ignored",
        )
        is False
    )


def test_race_card_uses_status_age_when_session_label_is_still_active() -> None:
    """Active session labels should use terminal status age for post-session retention."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            current_session_state="Race",
            last_label=None,
            session_status="finished",
            age_seconds=5000,
            session_status_age_seconds=599,
            live_delay=0,
            prefix="custom_status_age",
        )
        is True
    )


def test_race_card_hides_after_status_age_retention_expires() -> None:
    """Active session labels should not keep terminal sessions visible forever."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            current_session_state="Race",
            last_label=None,
            session_status="finished",
            age_seconds=5,
            session_status_age_seconds=601,
            live_delay=0,
            prefix="custom_status_age_expired",
        )
        is False
    )


def test_card_does_not_retain_mismatched_last_label() -> None:
    """A terminal status should not keep a different session card visible."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Qualifying",
            session_status="finished",
            age_seconds=120,
            live_delay=0,
            prefix="custom_mismatch",
        )
        is False
    )


def test_card_does_not_retain_without_last_label() -> None:
    """A cleared session without last_label should not reopen a timing card."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="",
            current_session_state="unknown",
            last_label=None,
            session_status="finished",
            age_seconds=120,
            live_delay=0,
            prefix="custom_missing_label",
        )
        is False
    )


def test_timing_snapshot_helpers_clone_and_clear_by_session() -> None:
    """Post-session snapshots should be immutable and scoped to one session."""
    if not CARD_PATH.exists():
        pytest.skip(f"card JS not found at {CARD_PATH}")
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for live card snapshot regression tests")

    env = os.environ.copy()
    env["CARD_VISIBILITY_PATH"] = str(CARD_PATH)
    completed = subprocess.run(
        [node, "-e", SNAPSHOT_PROBE_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    result = json.loads(completed.stdout)
    assert result["key"] == "Race|miami-2026|2026-05-03T20:00:00Z"
    assert result["retained"]["title"] == "Race Lap 57"
    assert result["retained"]["rows"][0]["tla"] == "VER"
    assert result["retained"]["rows"][0]["team_logo"]["src"] == "logo-a"
    assert result["retainedAgain"]["rows"][0]["tla"] == "VER"
    assert result["mismatched"] is None
