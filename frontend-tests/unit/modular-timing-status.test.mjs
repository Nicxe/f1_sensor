import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { RetainedSources, sessionContext, timingRows } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { SectorStore } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';

const state = (attributes, value = 'live') => ({ state: value, attributes });
function fixture(name = 'Race') {
  const entry = { entry_id: 'timing', entities: Object.fromEntries(['current_session', 'session_status', 'driver_positions', 'driver_list', 'current_tyres', 'starting_grid', 'investigations'].map(key => [key, `sensor.${key}`])) };
  const hass = { states: {
    'sensor.current_session': state({ session_key: 'race-123', meeting_key: 'meeting-1', start: '2026-11-08T17:00:00Z', active: true }, name),
    'sensor.session_status': state({}, 'live'),
    'sensor.driver_positions': state({ drivers: [{ racing_number: '16', tla: 'LEC', current_position: 2, grid_position: 20 }, { racing_number: '4', tla: 'NOR', current_position: 1 }] }),
    'sensor.starting_grid': state({ status: 'confirmed', session_key: 'race-123', meeting_key: 'meeting-1', grid_context: 'race', grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }] }),
    'sensor.investigations': state({ session_key: 'race-123', penalties: [], noted: [], under_investigation: [] }),
  } };
  const base = normalizeConfig({ modules: [{ type: 'timing' }] }).modules[0];
  const read = (options = {}, extra = {}) => timingRows(hass, entry, sessionContext(hass, entry), new SectorStore(), { ...base, ...extra, options: { ...base.options, position_change: 'grid', driver_badges: true, ...options } });
  return { hass, entry, read, attrs: key => hass.states[`sensor.${key}`].attributes };
}

test('sample timing previews use the real incident session identity while a provisional grid cannot show start gains', () => {
  const demo = makeDemo('race'), entry = demo.preview.entries[0];
  const module = normalizeConfig({ modules: [{ type: 'timing', options: { driver_badges: true, position_change: 'grid' } }] }).modules[0];
  const model = timingRows(demo.hass, entry, sessionContext(demo.hass, entry), new SectorStore(), module);
  const verstappen = model.rows.find(row => row.id === '1');
  assert.equal(verstappen.badges.find(badge => badge.type === 'time_penalty')?.seconds, 5);
  assert.ok(verstappen.badges.some(badge => badge.type === 'under_investigation'));
  assert.ok(model.rows.every(row => row.position_change === null));
  assert.equal(demo.hass.states[entry.entities.starting_grid].attributes.status, 'provisional');
});

test('timing position delta uses the confirmed matching start grid, never an observed position fallback', () => {
  const d = fixture(), row = () => d.read().rows.find(item => item.id === '16');
  assert.deepEqual(row().position_change, { value: 3, symbol: '↑', status: 'gain', comparison: 'grid' });
  assert.equal(row().grid_position, 5);
  assert.equal(d.read({ position_change: 'off' }).rows[1].position_change, null);
  for (const patch of [{ status: 'provisional' }, { session_key: 'earlier-race' }, { meeting_key: 'other-meeting' }, { grid_context: 'sprint' }]) {
    const original = { ...d.attrs('starting_grid') };
    Object.assign(d.attrs('starting_grid'), patch);
    assert.equal(row().position_change, null, JSON.stringify(patch));
    Object.assign(d.attrs('starting_grid'), original);
  }
  delete d.attrs('current_session').session_key;
  assert.equal(row().position_change, null);
});

test('unavailable or unknown current sessions cannot reuse retained session identifiers for live joins', () => {
  const d = fixture();
  d.attrs('current_session').last_label = 'Race';
  d.attrs('investigations').penalties = [{ racing_number: '16', penalty: '5 SECOND TIME PENALTY' }];
  for (const value of ['unavailable', 'unknown']) {
    d.hass.states['sensor.current_session'].state = value;
    const row = d.read().rows.find(item => item.id === '16');
    assert.equal(row.position_change, null, value);
    assert.deepEqual(row.badges, [], value);
  }
});

test('unknown, pit-lane and ambiguous grid references cannot invent gains', () => {
  const d = fixture(), grid = d.attrs('starting_grid'), row = () => d.read().rows.find(item => item.id === '16');
  for (const reference of [0, null, -1, 'unknown']) {
    grid.grid[0].grid_position = reference;
    assert.equal(row().position_change, null);
  }
  grid.grid[0].grid_position = 1;
  assert.equal(row().position_change, null);
  grid.grid = [{ racing_number: '16', grid_position: 5 }, { racing_number: '16', grid_position: 6 }];
  assert.equal(row().position_change, null);
  d.hass.states['sensor.starting_grid'].state = 'unavailable';
  assert.equal(row().position_change, null);
});

test('sprint grids match sprint timing, while practice and qualifying never receive a race-start delta', () => {
  for (const name of ['Practice 1', 'Qualifying', 'Sprint Qualifying']) {
    const d = fixture(name);
    assert.ok(d.read().rows.every(row => row.position_change === null));
  }
  const d = fixture('Sprint');
  d.attrs('starting_grid').grid_context = 'sprint';
  assert.equal(d.read().rows.find(row => row.id === '16').position_change.value, 3);
});

test('timing joins active penalties and investigations to the right driver within the current session', () => {
  const d = fixture(), incidents = d.attrs('investigations');
  incidents.penalties = [{ driver: 'LEC', racing_number: '16', penalty: '5 SECOND TIME PENALTY', reason: 'Causing a collision', utc: '2026-11-08T17:20:00Z', lap: 12 }];
  incidents.under_investigation = [{ drivers: ['LEC'], racing_numbers: ['16'], reason: 'Leaving the track', after_race: true }];
  incidents.noted = [{ drivers: ['NOR'], racing_numbers: ['4'], reason: 'Track limits' }];
  const leclerc = () => d.read().rows.find(row => row.id === '16');
  let badges = leclerc().badges;
  assert.deepEqual(badges.map(badge => badge.type), ['time_penalty', 'under_investigation']);
  assert.equal(badges[0].seconds, 5); assert.equal(badges[0].reason, 'Causing a collision');
  assert.equal(badges[0].event_time, '2026-11-08T17:20:00.000Z'); assert.equal(badges[0].lap, 12);
  assert.equal(badges[1].after_race, true);
  assert.deepEqual(d.read().rows.find(row => row.id === '4').badges.map(badge => badge.type), ['noted']);
  incidents.penalties = [];
  assert.deepEqual(leclerc().badges.map(badge => badge.type), ['under_investigation']);
  incidents.session_key = 'previous-session';
  assert.deepEqual(leclerc().badges, []);
  incidents.session_key = 'race-123';
  d.hass.states['sensor.investigations'].state = 'unavailable';
  assert.deepEqual(leclerc().badges, []);
});

test('badge UTC fields retain their instant in every browser timezone and reject invalid or unproven timestamps', () => {
  const originalTimezone = process.env.TZ;
  const cases = [
    [{ utc: '2026-11-08T17:20:00' }, '2026-11-08T17:20:00.000Z'],
    [{ utc: '2026-11-08T17:20:00.125' }, '2026-11-08T17:20:00.125Z'],
    [{ utc: '2026-11-08T19:20:00+02:00' }, '2026-11-08T17:20:00.000Z'],
    [{ utc: '2026-11-08T17:20:00Z' }, '2026-11-08T17:20:00.000Z'],
    [{ utc: 'not-a-timestamp' }, null],
    [{ utc: '2026-02-30T17:20:00' }, null],
    [{ utc: '2026-11-08T25:20:00' }, null],
    [{ event_time: '2026-11-08T17:20:00' }, null],
  ];
  try {
    for (const timezone of ['UTC', 'Europe/Stockholm', 'America/Los_Angeles']) {
      process.env.TZ = timezone;
      const d = fixture();
      for (const [timestamp, expected] of cases) {
        d.attrs('investigations').penalties = [{ racing_number: '16', penalty: '5 SECOND TIME PENALTY', ...timestamp }];
        const badge = d.read().rows.find(row => row.id === '16').badges[0];
        assert.equal(badge.event_time, expected, `${timezone}: ${JSON.stringify(timestamp)}`);
      }
    }
  } finally {
    if (originalTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = originalTimezone;
  }
});

test('driver numbers take precedence over ambiguous codes and duplicate or served decisions do not add extra badges', () => {
  const d = fixture(), incidents = d.attrs('investigations');
  const penalty = { driver: 'LEC', racing_number: '4', penalty: '5 SECOND TIME PENALTY' };
  incidents.penalties = [penalty, { ...penalty }, { driver: 'LEC', penalty: '10 SECOND TIME PENALTY', service_status: 'served' }];
  assert.deepEqual(d.read().rows.find(row => row.id === '16').badges, []);
  assert.equal(d.read().rows.find(row => row.id === '4').badges.length, 1);
  incidents.penalties = [{ driver: 'LEC', penalty: '0 SECOND TIME PENALTY' }];
  const badge = d.read().rows.find(row => row.id === '16').badges[0];
  assert.equal(badge.type, 'penalty'); assert.equal(badge.seconds, null);
});

test('direct data from another generation or an explicitly stale incident source cannot supply live badges or grid deltas', () => {
  const d = fixture();
  d.attrs('investigations').penalties = [{ racing_number: '16', penalty: '5 SECOND TIME PENALTY' }];
  d.entry.data_api = { enabled: [...Object.keys(d.entry.entities), 'session_context'] };
  d.entry.card_data = Object.fromEntries(Object.entries(d.entry.entities).map(([key, entityId]) => [key, { status: 'ready', data: {
    source: 'live', generation: 'current', status: 'ready', context: {}, payload: d.hass.states[entityId] ?? state({}),
  } }]));
  d.entry.card_data.session_context = { status: 'ready', data: { source: 'live', generation: 'current', status: 'ready', context: {}, payload: state({}) } };
  const row = () => d.read().rows.find(item => item.id === '16');
  assert.equal(row().badges[0].seconds, 5); assert.equal(row().position_change.value, 3);
  d.entry.card_data.investigations.data.generation = 'previous';
  d.entry.card_data.starting_grid.data.generation = 'previous';
  assert.deepEqual(row().badges, []); assert.equal(row().position_change, null);
  d.entry.card_data.investigations.data.generation = 'current';
  d.entry.card_data.investigations.data.status = 'stale';
  assert.deepEqual(row().badges, []);
  d.entry.card_data.investigations.data.status = 'ready';
  d.entry.card_data.starting_grid.data.generation = 'current';
  assert.equal(row().badges[0].seconds, 5); assert.equal(row().position_change.value, 3);
  d.entry.card_data.current_session.data.status = 'stale';
  assert.deepEqual(row().badges, []); assert.equal(row().position_change, null);
});

test('retained timing keeps captured penalty and start-grid dependencies together with the saved positions', () => {
  const d = fixture();
  d.entry.global_entities = { no_spoiler_mode: 'switch.spoilers' };
  d.entry.entities.replay_status = 'sensor.replay';
  d.hass.states['switch.spoilers'] = state({}, 'off');
  d.hass.states['sensor.replay'] = state({}, 'idle');
  d.attrs('investigations').penalties = [{ racing_number: '16', penalty: '5 SECOND TIME PENALTY' }];
  const config = normalizeConfig({ modules: [{ type: 'timing', unavailable: 'retain' }] }), module = config.modules[0];
  const store = new RetainedSources();
  store.update(d.hass, d.entry, config); store.select(d.hass, d.entry, module, { spoiler: true });
  d.hass.states['sensor.driver_positions'] = state({}, 'unavailable');
  d.hass.states['sensor.investigations'] = state({ session_key: 'race-123', penalties: [] });
  d.hass.states['sensor.starting_grid'] = state({ status: 'confirmed', session_key: 'race-123', grid_context: 'race', grid: [{ racing_number: '16', grid_position: 20 }] });
  store.update(d.hass, d.entry, config);
  const saved = store.select(d.hass, d.entry, module, { spoiler: true });
  assert.equal(saved.retained, true);
  const model = timingRows(saved.hass, d.entry, sessionContext(saved.hass, d.entry), new SectorStore(), { ...module, options: { ...module.options, position_change: 'grid', driver_badges: true } });
  const row = model.rows.find(item => item.id === '16');
  assert.equal(row.position_change.value, 3); assert.equal(row.badges[0].seconds, 5);
});

test('time penalties, drive-through and stop-go keep their distinct meanings and uncertain service never promises seconds', () => {
  const d = fixture(), penalties = d.attrs('investigations').penalties;
  for (const penalty of ['5 SECOND TIME PENALTY', '10 SECOND TIME PENALTY', 'DRIVE THROUGH PENALTY', '10 SECOND STOP/GO PENALTY', 'REPRIMAND']) penalties.push({ racing_number: '16', driver: 'LEC', penalty });
  const badges = () => d.read().rows.find(row => row.id === '16').badges;
  assert.deepEqual(badges().map(badge => badge.type), ['time_penalty', 'time_penalty', 'drive_through', 'stop_go', 'penalty']);
  assert.deepEqual(badges().slice(0, 2).map(badge => badge.seconds), [5, 10]);
  penalties[0].service_status = 'unknown';
  assert.ok(badges().every(badge => badge.type === 'penalty' && badge.seconds === null && badge.service_status === 'unknown'));
  assert.deepEqual(d.read({ driver_badges: false }).rows.find(row => row.id === '16').badges, []);
});

test('status badges preserve the difference between retired, temporarily stopped and pit exit', () => {
  const d = fixture(), driver = d.attrs('driver_positions').drivers[0];
  for (const [field, type] of [['in_pit', 'in_pit'], ['pit_out', 'pit_out'], ['stopped', 'stopped'], ['retired', 'retired']]) {
    Object.assign(driver, { in_pit: false, pit_out: false, stopped: false, retired: false, [field]: true, status: 'out' });
    const row = d.read().rows.find(item => item.id === '16');
    assert.equal(row.badges[0].type, type);
    assert.equal(row.retired, field === 'retired');
    assert.equal(row.stopped, field === 'stopped');
  }
  delete driver.retired; delete driver.in_pit; delete driver.pit_out; delete driver.stopped;
  const row = d.read().rows.find(item => item.id === '16');
  assert.equal(row.retired, null); assert.deepEqual(row.badges, []);
});

test('qualifying gaps and fastest flags use each part across the entire roster before focus filters', () => {
  const d = fixture('Qualifying'), positions = d.attrs('driver_positions');
  positions.current_qualifying_part = 2;
  Object.assign(positions.drivers[0], { q1_time: '1:20.300', q1_position: 2, q2_time: '1:19.500', q2_position: 1 });
  Object.assign(positions.drivers[1], { q1_time: '1:20.000', q1_position: 1, q2_time: '1:19.700', q2_position: 2 });
  const result = d.read({}, { driver: '16' }), row = result.rows[0];
  assert.equal(row.q1_gap, .3); assert.equal(row.q2_gap, 0); assert.equal(row.q3_gap, null);
  assert.equal(row.q1_time.overall_fastest, false); assert.equal(row.q2_time.overall_fastest, true);
  assert.equal(row.q2_time.source, 'qualifying_best');
  assert.equal(row.qualifying_gap, 0); assert.equal(result.qualifying_part, 2);
  assert.equal(d.read({}, { driver: '4' }).rows[0].qualifying_gap, .2);
  positions.drivers[0].q2_position = null;
  assert.equal(d.read().rows.find(item => item.id === '16').q2_time.overall_fastest, false);
  positions.current_qualifying_part = 4;
  assert.equal(d.read().qualifying_part, null); assert.equal(d.read().rows[0].qualifying_gap, null);
});
