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

const helperSources = [
  extractConst("const resolveEntityIdWithFallback = (hass, entityId) =>"),
  extractConst("const getEntityStateWithFallback = (hass, entityId) =>"),
  extractConst("const getStateAgeSeconds = (state, field = 'last_changed') =>"),
  extractConst("const resolveLiveDelaySeconds = (hass, entityIds = []) =>"),
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
    session_state = {
        "state": "unknown",
        "attributes": {"last_label": session_label},
        "last_changed": _iso_seconds_ago(age_seconds),
    }
    session_status_state = {
        "state": session_status,
        "attributes": {},
        "last_changed": _iso_seconds_ago(5),
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


def test_qualifying_card_stays_visible_with_delay_aware_post_finish_grace() -> None:
    """Live delay should extend the qualifying card's post-finish grace window."""
    assert (
        _run_visibility_probe(
            method_name="_isQualifyingSession",
            session_label="Qualifying",
            session_status="finished",
            age_seconds=170,
            live_delay=180,
            prefix="custom_qualifying",
        )
        is True
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


def test_practice_card_hides_after_post_finish_grace_expires() -> None:
    """Practice timing should disappear once the finished grace window has elapsed."""
    assert (
        _run_visibility_probe(
            method_name="_isPracticeSession",
            session_label="Practice 2",
            session_status="finished",
            age_seconds=120,
            live_delay=0,
            prefix="custom_practice",
        )
        is False
    )


def test_race_card_stays_visible_during_finalised_grace() -> None:
    """Race timing should remain visible briefly while finalisation settles."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            session_status="finalised",
            age_seconds=45,
            live_delay=0,
            prefix="custom_race",
        )
        is True
    )


def test_race_card_hides_when_session_reaches_ended() -> None:
    """The late ended marker should not reopen or prolong race card visibility."""
    assert (
        _run_visibility_probe(
            method_name="_isRaceSession",
            session_label="Race",
            session_status="ended",
            age_seconds=10,
            live_delay=180,
            prefix="custom_ended",
        )
        is False
    )
