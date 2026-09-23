import assert from 'node:assert/strict';
import test from 'node:test';
import { source, modelTimestamp } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { FIELDS } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';

const at = '2026-09-13T13:30:00Z';
const now = Date.parse('2026-09-13T13:32:30Z');

test('a Home Assistant update is not the source observation or the last state report', () => {
  const entry = { entities: { driver_positions: 'sensor.renamed' } };
  const hass = { states: { 'sensor.renamed': { state: '0', attributes: {}, last_updated: at, last_changed: '2026-09-13T13:00:00Z', last_reported: '2026-09-13T13:32:00Z' } } };
  const selected = source(hass, entry, 'driver_positions');
  assert.equal(selected.updated_at, at);
  assert.equal(selected.received_at, undefined);
  assert.equal(selected.state, '0');
  assert.deepEqual(modelTimestamp({ source: selected }, now), { kind: 'ha_state', at: '2026-09-13T13:30:00.000Z', ageSeconds: 150, future: false });
  delete hass.states['sensor.renamed'].last_updated;
  assert.equal(modelTimestamp({ source: source(hass, entry, 'driver_positions') }, now).at, null);
});

test('snapshot generation, source update and browser receipt keep their own origins', () => {
  const selected = { updated_at: at };
  for (const kind of ['ha_state', 'generated', 'source_update', 'received']) {
    assert.equal(modelTimestamp({ source: selected, context: { updated: at, updatedKind: kind } }, now).kind, kind);
    const missing = modelTimestamp({ source: selected, context: { updated: null, updatedKind: kind } }, now);
    assert.equal(missing.at, null, 'a missing source timestamp must not borrow a HA update');
    assert.equal(missing.ageSeconds, null);
  }
  assert.equal(modelTimestamp({}, now), null);
});

test('unknown and future ages remain unknown; timezone offsets and epoch zero are valid', () => {
  const info = value => modelTimestamp({ context: { updated: value, updatedKind: 'received' } }, now);
  for (const invalid of [undefined, null, '', '2026-09-13', '2026-09-13T13:30:00', 'yesterday', 0, NaN, {}, true]) {
    assert.equal(info(invalid).at, null);
    assert.equal(info(invalid).ageSeconds, null);
  }
  assert.equal(info('2026-09-13T15:30:00+02:00').ageSeconds, 150);
  assert.equal(info('2026-09-13T13:32:31Z').future, true);
  assert.equal(info('2026-09-13T13:32:31Z').ageSeconds, null);
  assert.equal(info('2026-09-13T13:32:30Z').ageSeconds, 0);
  assert.equal(info('1970-01-01T00:00:00Z').at, '1970-01-01T00:00:00.000Z');
  assert.equal(modelTimestamp({ source: { updated_at: at } }, NaN).ageSeconds, null);
});

test('field contracts distinguish state updates, lap positions and relative telemetry time', () => {
  for (const field of Object.values(FIELDS)) {
    assert.notEqual(field.timestamps.received, 'entity.last_updated', field.id);
    assert.notEqual(field.timestamps.source, 'published', field.id);
    assert.notEqual(field.timestamps.source, 'stream', field.id);
  }
  assert.equal(FIELDS.last_lap.timestamps.source, 'not_provided');
  assert.equal(FIELDS.last_lap.timestamps.updated, 'entity.last_updated');
  assert.equal(FIELDS.lap_series.timestamps.position, 'lap_number');
  assert.equal(FIELDS.telemetry_speed.timestamps.position, 'time_s');
  assert.equal(FIELDS.telemetry_speed.timestamps.source, 'not_provided');
  assert.equal(FIELDS.session_time_remaining.timestamps.source, 'last_server_utc');
  assert.equal(FIELDS.clean_pace.timestamps.received, 'subscription.received_at');
  assert.equal(FIELDS.clean_pace.timestamps.updated, 'not_provided');
  assert.equal(FIELDS.track_map.timestamps.source, 'stream_timestamp');
});
