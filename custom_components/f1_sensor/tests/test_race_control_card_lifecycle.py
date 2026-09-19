"""Exercise Race Control card history recovery with the bundled JavaScript."""

from pathlib import Path
import shutil
import subprocess

import pytest

CARD_PATH = (
    Path(__file__).resolve().parents[1]
    / "www/f1-sensor-live-data-card/f1-sensor-live-data-card.js"
)

PROBE = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('class F1RaceControlCard extends LitElement {');
const end = source.indexOf('class F1RaceControlCardEditor', start);
class LitElement {
  connectedCallback() {}
  disconnectedCallback() {}
  requestUpdate() {}
}
const Card = new Function('LitElement', 'css', 'F1_THEME_STYLES',
  'ensureF1Fonts', 'resolveEntityIdWithFallback', 'getEntityStateWithFallback',
  source.slice(start, end) + '; return F1RaceControlCard;'
)(LitElement, () => '', [], () => {}, (h, e) => e, (h, e) => h?.states[e]);
const entityId = 'sensor.test_race_control';
const message = n => ({event_id: String(n), message: `Message ${n}`,
  utc: `2026-09-13T12:00:0${n}Z`, sequence: n});
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
};
function connection() {
  const events = new Set();
  const ready = new Set();
  return {
    events, ready,
    async subscribeEvents(cb, type) {
      const sub = {cb, type}; events.add(sub);
      return () => events.delete(sub);
    },
    addEventListener(type, cb) { if (type === 'ready') ready.add(cb); },
    removeEventListener(type, cb) { if (type === 'ready') ready.delete(cb); },
    reconnect() { for (const cb of [...ready]) cb(); },
    emit(n) {
      for (const {cb, type} of events) {
        if (type === 'f1_sensor_race_control_event')
          cb({data: {entity_id: entityId, log_item: message(n)}});
      }
    },
  };
}
function setup() {
  const card = new Card();
  const server = {items: [message(1)], loads: 0};
  card.config = {entity: entityId, display_mode: 'list'};
  card.isConnected = true;
  card.hass = {
    states: {[entityId]: {state: 'Message 1', attributes: message(1)}},
    connection: connection(),
    callWS: async () => { server.loads++; return {items: [...server.items]}; },
  };
  return {card, server};
}
function detach(card) { card.isConnected = false; card.disconnectedCallback(); }
const ids = card => card._listMessages.map(item => item.event_id);
async function run(scenario) {
  const {card, server} = setup();
  try {
    if (scenario === 'subscription_before_snapshot') {
      const gate = deferred();
      const subscribe = card.hass.connection.subscribeEvents;
      card.hass.connection.subscribeEvents = async (...args) => {
        await gate.promise; return subscribe(...args);
      };
      card.connectedCallback(); await tick();
      assert.equal(server.loads, 0, 'Snapshot must wait for event subscriptions');
      server.items.push(message(2)); gate.resolve(); await tick();
      assert.deepEqual(ids(card), ['2', '1']);
      return;
    }
    card.connectedCallback(); await tick();
    assert.deepEqual(ids(card), ['1']);
    if (scenario === 'detached_update') {
      detach(card);
      card.willUpdate(new Map([['hass', true]])); await tick();
      server.items.push(message(2));
      card.isConnected = true; card.connectedCallback(); await tick();
      assert.deepEqual(ids(card), ['2', '1'], 'Return must fetch missed messages');
      assert.equal(card.hass.connection.events.size, 2);
      card.hass.connection.emit(3);
      assert.deepEqual(ids(card), ['3', '2', '1']);
    } else if (scenario === 'websocket_ready' || scenario === 'connection_replaced') {
      for (let n = 2; n <= 8; n++) server.items.push(message(n));
      const oldConnection = card.hass.connection;
      if (scenario === 'websocket_ready') oldConnection.reconnect();
      else {
        card.hass = {...card.hass, connection: connection()};
        card.willUpdate(new Map([['hass', true]]));
      }
      await tick();
      assert.deepEqual(ids(card), ['8', '7', '6', '5', '4', '3', '2', '1']);
      assert.equal(server.loads, 2);
      assert.equal(card.hass.connection.events.size, 2);
      if (scenario === 'connection_replaced') {
        assert.equal(oldConnection.events.size, 0);
        assert.equal(oldConnection.ready.size, 0);
      }
      detach(card);
      assert.equal(card.hass.connection.ready.size, 0);
      assert.equal(card.hass.connection.events.size, 0);
    } else if (scenario === 'stale_snapshot') {
      const gate = deferred();
      card.hass.callWS = () => gate.promise;
      detach(card); card.isConnected = true; card.connectedCallback(); await tick();
      for (const {cb, type} of card.hass.connection.events) {
        if (type === 'f1_sensor_race_control_log_reset_event')
          cb({data: {entity_id: entityId}});
      }
      card.hass.connection.emit(2);
      gate.resolve({items: [message(1)]}); await tick();
      assert.deepEqual(ids(card), ['2'], 'A cleared log must not return from an old request');
    } else if (scenario === 'history_failure') {
      detach(card);
      card.hass.callWS = async () => { throw new Error('connection lost'); };
      card.isConnected = true; card.connectedCallback(); await tick();
      assert.ok(card._listRetryTimer, 'Failed history fetch must schedule recovery');
      server.items.push(message(2));
      card.hass.callWS = async () => ({items: [...server.items]});
      card.hass.connection.reconnect(); await tick();
      assert.deepEqual(ids(card), ['2', '1']);
      assert.equal(card._listRetryTimer, null);
    }
  } finally { detach(card); }
}
run(process.argv[2]).catch(err => { console.error(err); process.exitCode = 1; });
"""


@pytest.mark.parametrize(
    "scenario",
    [
        "detached_update",
        "websocket_ready",
        "connection_replaced",
        "subscription_before_snapshot",
        "stale_snapshot",
        "history_failure",
    ],
)
def test_race_control_card_recovers_history(scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for card lifecycle tests")
    result = subprocess.run(
        [node, "-e", PROBE, str(CARD_PATH), scenario],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
