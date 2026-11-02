import assert from 'node:assert/strict';
import test from 'node:test';
import { card } from './card-module.mjs';

const positions = [
  { racing_number: '14', tla: 'ALO', x: -1180, y: -110, status: 'OnTrack' },
  { racing_number: '16', tla: 'LEC', x: 4000, y: -3000, status: 'OnTrack' },
];

function mapWithTiming(timing, entityState = '2', selection = 'explicit') {
  const entity = selection === 'auto' ? 'sensor.f1_driver_positions' : 'sensor.timing';
  const host = card('f1-track-map-card', { driver_positions_entity: selection === 'auto' ? 'auto' : entity });
  host._snapshot = { source: 'live', stream_timestamp: new Date().toISOString(), stale_after_seconds: 10 };
  host.hass.states[entity] = { state: entityState, attributes: { drivers: timing } };
  return host;
}

for (const entityState of ['2', 'unknown']) for (const selection of ['explicit', 'auto']) {
  for (const part of [1, 2]) {
    test(`legacy map uses ${selection} timing with state ${entityState} to hide a Q${part} car in the pits`, () => {
      const timing = { racing_number: '14', tla: 'ALO', in_pit: true, retired: false,
        stopped: false, status: 'pit_in', [`q${part}_knocked_out`]: true };
      const host = mapWithTiming([timing], entityState, selection);
      assert.deepEqual([...host._visibleDrivers(positions)].map(driver => driver.tla), ['LEC']);

      for (const active of [
        { ...timing, in_pit: false, status: 'on_track' },
        { ...timing, [`q${part}_knocked_out`]: false },
      ]) {
        Object.values(host.hass.states)[0].attributes.drivers = [active];
        assert.deepEqual([...host._visibleDrivers(positions)].map(driver => driver.tla), ['ALO', 'LEC']);
      }
    });
  }

  for (const [name, timing] of [['stopped', { stopped: true }], ['retired', { retired: true }], ['out', { status: 'out' }]]) {
    test(`legacy map uses ${selection} timing with state ${entityState} to hide a car reported ${name}`, () => {
      const host = mapWithTiming([{ racing_number: '14', ...timing }], entityState, selection);
      assert.deepEqual([...host._visibleDrivers(positions)].map(driver => driver.tla), ['LEC']);
    });
  }
}

for (const selection of ['explicit', 'auto']) {
  test(`legacy map ignores inactive driver attributes from an unavailable ${selection} timing entity`, () => {
    const host = mapWithTiming([{ racing_number: '14', stopped: true, in_pit: true, q1_knocked_out: true }], 'unavailable', selection);
    assert.deepEqual([...host._visibleDrivers(positions)].map(driver => driver.tla), ['ALO', 'LEC']);
  });
}
