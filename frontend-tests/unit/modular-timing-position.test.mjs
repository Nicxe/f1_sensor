import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, exportConfig, importConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { TIMING_PROFILES, timingFields } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { sessionContext, timingRows } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { SectorStore } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';

const config = module => normalizeConfig({ modules: [{ type: 'timing', ...module }] });

test('position remains plain by default while the combined position field is independently selectable', () => {
  const plain = config({}).modules[0];
  assert.ok(plain.fields.includes('position'));
  assert.ok(!plain.fields.includes('position_with_change'));
  for (const fields of Object.values(TIMING_PROFILES)) {
    assert.ok(fields.includes('position'));
    assert.ok(!fields.includes('position_with_change'));
  }
  const combined = config({ fields: ['driver', 'position_with_change', 'last_lap'] });
  assert.deepEqual(combined.modules[0].fields, ['driver', 'position_with_change', 'last_lap']);
  assert.equal(combined.modules[0].options.position_change, 'off');
  assert.deepEqual(importConfig(exportConfig(combined)), combined);
});

test('saved grid-change options migrate table and detail positions in place exactly once', () => {
  const original = { type: 'timing', fields: ['driver', 'position', 'last_lap'],
    detail_fields: ['tyre_age', 'position', 'best_lap'],
    options: { position_change: 'grid', profile: 'custom', detail_laps: 3, driver_badges: true } };
  const before = structuredClone(original);
  const migrated = config(original), module = migrated.modules[0];
  assert.deepEqual(module.fields, ['driver', 'position_with_change', 'last_lap']);
  assert.deepEqual(module.detail_fields, ['tyre_age', 'position_with_change', 'best_lap']);
  assert.equal(module.options.position_change, 'off');
  assert.equal(module.options.profile, 'custom');
  assert.equal(module.options.detail_laps, 3);
  assert.equal(module.options.driver_badges, true);
  assert.deepEqual(original, before);
  assert.deepEqual(normalizeConfig(migrated), migrated);
  assert.deepEqual(importConfig(exportConfig(migrated)), migrated);

  const plainAgain = structuredClone(migrated);
  plainAgain.modules[0].fields[1] = 'position';
  plainAgain.modules[0].detail_fields[1] = 'position';
  assert.deepEqual(normalizeConfig(plainAgain).modules[0].fields, original.fields);
  assert.deepEqual(normalizeConfig(plainAgain).modules[0].detail_fields, original.detail_fields);
});

test('migration never inserts a position column that the saved custom view omitted', () => {
  const module = config({ fields: ['driver', 'last_lap'], detail_fields: ['tyre_age'],
    options: { position_change: 'grid', profile: 'custom' } }).modules[0];
  assert.deepEqual(module.fields, ['driver', 'last_lap']);
  assert.deepEqual(module.detail_fields, ['tyre_age']);
  assert.equal(module.options.position_change, 'off');
});

test('advanced JSON can retain both position columns without normalization dropping or reordering either', () => {
  const fields = ['driver', 'position', 'last_lap', 'position_with_change'];
  const detail_fields = ['position_with_change', 'best_lap', 'position'];
  const value = config({ fields, detail_fields, options: { profile: 'custom' } });
  assert.deepEqual(value.modules[0].fields, fields);
  assert.deepEqual(value.modules[0].detail_fields, detail_fields);
  assert.deepEqual(importConfig(exportConfig(value)), value);
});

test('session profiles retain the combined choice in the normal position slot', () => {
  for (const [profile, session] of [['race', 'Race'], ['sprint', 'Sprint'],
    ['practice', 'Practice 3'], ['qualifying', 'Qualifying'], ['sprint_qualifying', 'Sprint Qualifying']]) {
    for (const selected of ['auto', profile]) {
      const module = config({ fields: ['position_with_change', 'driver'], options: { profile: selected } }).modules[0];
      assert.equal(module.options.profile, selected);
      assert.deepEqual(timingFields(module, session), TIMING_PROFILES[profile].map(field => field === 'position' ? 'position_with_change' : field));
    }
  }
});

test('a saved automatic profile keeps its position-change choice even when its stored custom fields omit position', () => {
  const module = config({ fields: ['driver', 'last_lap'], options: { profile: 'auto', position_change: 'grid' } }).modules[0];
  assert.equal(module.options.profile, 'auto');
  assert.equal(module.options.position_change, 'off');
  assert.deepEqual(module.fields, ['position_with_change', 'driver', 'last_lap']);
  assert.equal(timingFields(module, 'Race')[0], 'position_with_change');
  assert.deepEqual(normalizeConfig({ modules: [module] }).modules[0], module);
  const narrow = config({ fields: ['driver', 'last_lap'], options: { profile: 'custom', narrow_layout: true, position_change: 'grid' } }).modules[0];
  assert.deepEqual(narrow.fields, ['position_with_change', 'driver', 'last_lap']);
  assert.equal(narrow.options.position_change, 'off');
  assert.equal(narrow.options.narrow_layout, true);
});

const state = (attributes, value = 'live') => ({ state: value, attributes });
function replayFixture(name = 'Race') {
  const context = { session_id: '2026:meeting-1:race-123', replay_generation: 2, delay_seconds: 0, qualifying_part: null };
  const resource = (attributes, value = 'live') => ({ status: 'ready', data: {
    source: 'replay', generation: 'replay-generation-2', context: { ...context }, status: 'ready', payload: state(attributes, value),
  } });
  const current = { session_key: 'race-123', meeting_key: 'meeting-1', season: 2026, start: '2026-11-08T17:00:00Z', active: true };
  const reference = { source: 'TimingAppData.GridPos', session_key: 'race-123',
    grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }] };
  const positions = { drivers: [
    { racing_number: '16', tla: 'LEC', current_position: 2, completed_laps: 12, grid_position: 20 },
    { racing_number: '4', tla: 'NOR', current_position: 1, completed_laps: 12, grid_position: 19 },
  ], starting_grid_reference: reference };
  const entry = { entry_id: 'replay-timing', entities: {
    current_session: 'sensor.session', session_status: 'sensor.status', driver_positions: 'sensor.positions',
    starting_grid: 'sensor.live_grid', replay_status: 'sensor.replay',
  }, data_api: { enabled: ['session_context', 'current_session', 'driver_positions'] }, card_data: {
    session_context: resource({}), current_session: resource(current, name), driver_positions: resource(positions, '12'),
  } };
  const hass = { states: {
    'sensor.session': state(current, name), 'sensor.status': state({}, 'live'),
    'sensor.positions': state(positions, '12'), 'sensor.replay': state({ selected_session_key: 'race-123' }, 'paused'),
    // The independent live-season coordinator deliberately retains another session.
    'sensor.live_grid': state({ status: 'confirmed', session_key: 'another-race', meeting_key: 'another-meeting',
      grid_context: 'race', grid: [{ racing_number: '16', grid_position: 10 }, { racing_number: '4', grid_position: 2 }] }),
  } };
  const module = config({ fields: ['position_with_change', 'driver'] }).modules[0];
  const read = () => timingRows(hass, entry, sessionContext(hass, entry), new SectorStore(), module);
  const leclerc = () => read().rows.find(row => row.id === '16');
  return { entry, hass, reference, positions, current, read, leclerc };
}

test('replay timing uses its explicit GridPos reference instead of the independent live grid or raw driver grid', () => {
  const d = replayFixture();
  assert.deepEqual(d.leclerc().position_change, { value: 3, symbol: '↑', status: 'gain', comparison: 'grid' });
  assert.equal(d.leclerc().grid_position, 5);
  assert.equal(d.read().rows.find(row => row.id === '4').position_change.status, 'equal');
  d.positions.drivers[0].current_position = 6;
  assert.deepEqual(d.leclerc().position_change, { value: -1, symbol: '↓', status: 'loss', comparison: 'grid' });
  assert.equal(d.reference.grid[0].grid_position, 5);
});

test('only explicit GridPos provenance from the matching replay session can establish a replay start reference', () => {
  for (const patch of [{ source: 'TimingData.Position' }, { source: 'DriverList.Line' },
    { source: 'unknown' }, { session_key: 'earlier-session' }, { session_key: null }]) {
    const d = replayFixture();
    Object.assign(d.reference, patch);
    assert.equal(d.leclerc().position_change, null, JSON.stringify(patch));
  }
  for (const key of ['driver_positions', 'session_context']) {
    const d = replayFixture();
    d.entry.card_data[key].data.source = 'live';
    assert.equal(d.leclerc().position_change, null, `${key} is not a replay source`);
  }
  const entityOnly = replayFixture();
  delete entityOnly.entry.data_api;
  assert.equal(entityOnly.leclerc().position_change, null, 'entity attributes do not prove replay transport ownership');
});

test('replay start references cannot cross generations, session identifiers or stale direct resources', () => {
  for (const key of ['driver_positions', 'current_session', 'session_context']) {
    for (const [field, value] of [['status', 'stale'], ['generation', 'old-generation']]) {
      const d = replayFixture();
      d.entry.card_data[key].data[field] = value;
      assert.ok(d.read().rows.every(row => row.position_change === null), `${key}.${field}`);
    }
    const d = replayFixture();
    d.entry.card_data[key].data.context.session_id = 'previous-recording';
    assert.ok(d.read().rows.every(row => row.position_change === null), `${key}.context.session_id`);
    const olderSeek = replayFixture();
    olderSeek.entry.card_data[key].data.context.replay_generation = 1;
    assert.ok(olderSeek.read().rows.every(row => row.position_change === null), `${key}.context.replay_generation`);
  }
  const wrongIdentity = replayFixture();
  wrongIdentity.current.session_key = 'previous-session';
  assert.equal(wrongIdentity.leclerc().position_change, null);
});

test('missing, pit-lane and ambiguous replay references remain unknown without inferring from observed positions', () => {
  for (const grid of [[], [{ racing_number: '16', grid_position: 0 }],
    [{ racing_number: '16', grid_position: null }],
    [{ racing_number: '16', grid_position: 5 }, { racing_number: '16', grid_position: 6 }],
    [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 5 }]]) {
    const d = replayFixture();
    d.reference.grid = grid;
    assert.equal(d.leclerc().position_change, null, JSON.stringify(grid));
  }
  for (const completed_laps of [0, 1, 12]) {
    const d = replayFixture();
    delete d.positions.starting_grid_reference;
    Object.assign(d.positions.drivers[0], { completed_laps, current_position: 2 });
    assert.equal(d.leclerc().position_change, null, `${completed_laps} completed laps are not a grid observation`);
    assert.equal(d.leclerc().grid_position, null);
  }
});

test('a replay generation change with no fresh GridPos reference cannot reuse the prior reference', () => {
  const d = replayFixture();
  assert.equal(d.leclerc().position_change.value, 3);
  for (const resource of Object.values(d.entry.card_data)) {
    resource.data.generation = 'replay-generation-3';
    resource.data.context.replay_generation = 3;
  }
  delete d.positions.starting_grid_reference;
  d.positions.drivers[0].current_position = 5;
  assert.equal(d.leclerc().position_change, null);
  assert.equal(d.leclerc().grid_position, null);
});

test('explicit replay start references are race and sprint comparisons, never qualifying or practice gains', () => {
  for (const session of ['Practice 3', 'Qualifying', 'Sprint Qualifying']) {
    const d = replayFixture(session);
    assert.equal(d.leclerc().position_change, null, session);
  }
  assert.equal(replayFixture('Sprint').leclerc().position_change.value, 3);
});
