import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {card} from './card-module.mjs';

const observed = JSON.parse(readFileSync(new URL('./race-control-events.json', import.meta.url)));

test('Race Control merges actual log and entity messages with different IDs and sequences', () => {
  const host = card('f1-race-control-card');
  host._listMessages = observed.backend_items.map(item => host._normalizeListItem(item));
  for (const state of observed.sensor_states) host._syncCurrentEntityIntoList(state);
  assert.equal(host._listMessages.length, 2);
  assert.deepEqual(Array.from(host._listMessages, item => item.sequence), [11, 10]);
  assert.equal(host._listMessages[0].utc, observed.backend_items[0].utc);
});

test('Race Control source identity normalizes UTC but preserves separate incidents', () => {
  const host = card('f1-race-control-card');
  const original = observed.backend_items[0];
  const equivalent = {...original, event_id: 'sensor-id', utc: '2026-09-05T13:20:41+02:00'};
  const distinct = [
    {...original, event_id: 'later', utc: '2026-09-05T11:21:41Z'},
    {...original, event_id: 'car', car_number: '18'},
    {...original, event_id: 'scope', scope: 'Sector'},
    {...original, event_id: 'sector', sector: 2},
    {...original, event_id: 'flag', flag: 'YELLOW'},
    {...original, event_id: 'missing-time-1', utc: null},
    {...original, event_id: 'missing-time-2', utc: null},
  ];
  const result = host._sortListItems([original, equivalent, ...distinct].map(item => host._normalizeListItem(item)));
  assert.equal(result.length, 8);
});

test('Race Control reset and entity scoping retain their existing boundary', () => {
  const host = card('f1-race-control-card');
  const event = observed.backend_items[0];
  host._listMessages = [host._normalizeListItem(event)];
  host._handleRaceControlResetEvent({data:{entity_id:'sensor.other'}}, 'sensor.race_control');
  assert.equal(host._listMessages.length, 1);
  host._handleRaceControlResetEvent({data:{entity_id:'sensor.race_control'}}, 'sensor.race_control');
  assert.equal(host._listMessages.length, 0);
  host._handleRaceControlListEvent({data:{entity_id:'sensor.other',log_item:event}}, 'sensor.race_control');
  assert.equal(host._listMessages.length, 0);
  host._handleRaceControlListEvent({data:{entity_id:'sensor.race_control',log_item:event}}, 'sensor.race_control');
  assert.equal(host._listMessages.length, 1);
});

for (const type of ['f1-practice-timing-card', 'f1-driver-lap-times-card', 'f1-race-lap-card']) {
  test(`${type} uses the integration best lap after joining late and after corrections`, () => {
    const host = card(type);
    const position = {completed_laps:18,laps:{17:'1:41.181',18:'1:41.293'},best_lap_time:'1:23.000',best_lap_time_secs:83,best_lap_lap:8};
    assert.equal(host._buildLapSnapshot(position).best_lap, '1:23.000');
    assert.equal(host._buildLapSnapshot({...position, laps:{...position.laps,7:'1:22.000'}}).best_lap, '1:23.000');
    const cleared = host._buildLapSnapshot({...position,best_lap_time:null,best_lap_time_secs:null,best_lap_lap:null});
    assert.ok(!cleared.best_lap || cleared.best_lap === '--:--.---');
    assert.equal(cleared.last_lap, '1:41.293');
  });
  test(`${type} preserves observed history fallback for older integrations`, () => {
    const host = card(type);
    const result = host._buildLapSnapshot({completed_laps:18,laps:{17:'1:41.181',18:'1:41.293'}});
    assert.equal(result.best_lap, '1:41.181');
    assert.equal(result.last_lap, '1:41.293');
  });
}
