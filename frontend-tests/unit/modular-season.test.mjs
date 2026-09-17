import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { resultsModel, standingsModel, documentsModel, selectRows, chartAxis } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/season-data.js';
import { compoundMeta, trackSignal, contrast } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';
const configModule = (type, options = {}, extra = {}) => normalizeConfig({ modules: [{ type, options, ...extra }] }).modules[0];
function fixture(values) {
  const entry = { entry_id: 'one', entities: {} }, hass = { states: {} };
  for (const [key, attributes] of Object.entries(values)) { entry.entities[key] = `sensor.renamed_${key}`; hass.states[entry.entities[key]] = { state: 'available', attributes, last_updated: '2026-09-13T13:30:00Z' }; }
  return { hass, entry };
}
const result = (number, position, extra = {}) => ({ number, position, grid: '0', time: '+1 LAP', laps: '52', points: '0', status: '+1 Lap', driver: { permanentNumber: number, code: 'OLD', givenName: 'Historic', familyName: 'Driver' }, constructor: { name: 'Historic Team' }, ...extra });

test('classification preserves source time, points zero, pit lane start and historical identity', () => {
  const { hass, entry } = fixture({ last_race_results: { race_name: 'Old GP', round: '2', results: [result('7', '4')] }, driver_list: { drivers: [{ racing_number: '7', tla: 'NEW', name: 'New Driver', team: 'New Team' }] } });
  const [row] = resultsModel(hass, entry, configModule('results')).rows;
  assert.equal(row.name, 'Historic Driver'); assert.equal(row.team, 'Historic Team');
  assert.equal(row.result_time, '+1 LAP'); assert.equal(row.points, 0); assert.equal(row.grid_position, 0); assert.equal(row.position_change, null);
});

test('round selection never falls back to a different event and duplicates have one stable row', () => {
  const { hass, entry } = fixture({ season_results: { races: [{ round: '2', race_name: 'Second', results: [result('7', '4'), null, result('7', '3')] }, { round: '1', race_name: 'First', results: [result('9', '1')] }] } });
  const selected = resultsModel(hass, entry, configModule('results', { content: 'race_results', round: '2' }));
  assert.equal(selected.rows.length, 1); assert.equal(selected.rows[0].result_position, 3);
  assert.deepEqual(selected.choices.map(item => item.id), ['2', '1']);
  assert.equal(resultsModel(hass, entry, configModule('results', { content: 'race_results', round: '99' })).rows.length, 0);
});

test('grid exposes source and qualifying position without pretending to be classified results', () => {
  const { hass, entry } = fixture({ starting_grid: { status: 'provisional', target_session_name: 'Race', source: 'qualifying', grid: [
    { racing_number: '16', tla: 'LEC', driver_name: 'Charles Leclerc', team_name: 'Ferrari', grid_position: 4, qualifying_position: 1, qualifying_time: '1:20.123', qualifying_segment: 'Q3' },
    { racing_number: '44', tla: 'HAM', driver_name: 'Lewis Hamilton', team_name: 'Ferrari', grid_position: 2, qualifying_position: 2, qualifying_time_secs: 80.523 },
  ] } });
  const module = configModule('results', { content: 'starting_grid' }), model = resultsModel(hass, entry, module);
  assert.ok(module.fields.includes('grid_position')); assert.ok(!module.fields.includes('result_position'));
  const leclerc = model.rows.find(row => row.id === '16'), hamilton = model.rows.find(row => row.id === '44');
  assert.equal(leclerc.result_position, null); assert.equal(leclerc.grid_position, 4); assert.equal(leclerc.qualifying_position, 1);
  assert.equal(leclerc.qualifying_time, 80.123); assert.equal(leclerc.grid_delta, 3); assert.equal(leclerc.qualifying_segment, 'Q3');
  assert.equal(leclerc.qualifying_delta, 0); assert.ok(Math.abs(hamilton.qualifying_delta - 0.4) < 1e-9); assert.equal(model.context.status, 'provisional');
});

test('unknown teams stay separate and missing numeric sort values stay last in both directions', () => {
  const rows = [{ id: 'a', team: 'Unknown Team A', points: null }, { id: 'b', team: 'Unknown Team B', points: 0 }, { id: 'c', team: 'Unknown Team A', points: 2 }];
  for (const direction of ['asc', 'desc']) {
    const module = configModule('standings', { sort: 'points', direction });
    assert.equal(selectRows(rows, module).rows.at(-1).id, 'a');
    assert.deepEqual(selectRows(rows, module, { team: 'Unknown Team B' }).rows.map(item => item.id), ['b']);
  }
});

test('live projections use actual F1 fields and never overwrite published positions or points', () => {
  const { hass, entry } = fixture({ driver_standings: { season: '2026', round: '2', driver_standings: [{ position: '2', points: '40', wins: '1', Driver: { permanentNumber: '16', code: 'LEC', givenName: 'Charles', familyName: 'Leclerc' }, Constructors: [{ name: 'Ferrari' }] }] }, driver_list: { drivers: [{ racing_number: '16', tla: 'LEC', headshot_small: 'https://example.com/lec.png' }] }, championship_prediction_drivers: { drivers: { 16: { RacingNumber: '16', Tla: 'LEC', CurrentPosition: 3, CurrentPoints: 39, PredictedPosition: 1, PredictedPoints: 65 } } }, current_session: { active: true }, session_status: {} });
  hass.states[entry.entities.current_session].state = 'Race'; hass.states[entry.entities.session_status].state = 'live';
  const module = configModule('standings', {}, { fields: ['points', 'predicted_points'] });
  const [row] = standingsModel(hass, entry, module).rows;
  assert.equal(row.points, 40); assert.equal(row.result_position, 2); assert.equal(row.predicted_points, 65); assert.equal(row.predicted_position, 1); assert.equal(row.points_change, 26); assert.equal(row.headshot, 'https://example.com/lec.png');
  hass.states[entry.entities.current_session] = { state: 'no_session', attributes: {} }; hass.states[entry.entities.session_status].state = 'finished';
  assert.equal(standingsModel(hass, entry, module).rows[0].predicted_points, null); assert.equal(standingsModel(hass, entry, module).rows[0].points_change, null);
});

test('documents merge the latest item, reject executable links and preserve unspecified publication zones', () => {
  const document = { name: 'Doc 2 · Decision', document_number: 2, url: 'https://www.fia.com/example.pdf', published: '2026-09-12T13:00:00Z' };
  const { hass, entry } = fixture({ fia_documents: { ...document, documents: [document, { name: 'Notes', url: 'javascript:alert(1)', published: '12/09/2026 13:00' }] } });
  const model = documentsModel(hass, entry, configModule('documents'));
  assert.equal(model.rows.length, 2); assert.equal(model.rows[1].url, null); assert.equal(model.rows[1].timestamp, null);
  assert.equal(model.rows[1].document_time, '12/09/2026 13:00');
  assert.equal(documentsModel(hass, entry, configModule('documents', { search: 'decision' })).rows.length, 1);
});

test('compound and track graphics retain readable identities independently of color', () => {
  for (const [input, letter] of [['soft', 'S'], ['M', 'M'], ['HARD', 'H'], ['INTER', 'I'], ['FULL WET', 'W']]) {
    const meta = compoundMeta(input); assert.equal(meta.letter, letter); assert.ok(meta.asset); assert.ok(meta.label.sv);
  }
  assert.equal(compoundMeta('experimental').asset, null); assert.equal(compoundMeta(null).letter, '?');
  for (const value of ['CLEAR', 'YELLOW', 'RED', 'SC', 'VSC', 'BLUE', 'CHEQUERED']) {
    const flag = trackSignal(value); assert.ok(flag.symbol); assert.ok(flag.label.sv); assert.ok(contrast(flag.color, flag.ink) >= 4.5);
  }
  assert.equal(trackSignal('unexpected'), null); assert.notEqual(trackSignal('YELLOW').label.en, 'Recorded time');
});

test('progression retains actual round alignment, zero points and gaps instead of bridging missing results', async () => {
  const { progressionModel, seriesSegments } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/season-data.js');
  const { hass, entry } = fixture({ driver_points_progression: { season: '2026', rounds: [{ round: 3, race_name: 'Third' }, { round: 1, race_name: 'First' }, { round: 2, race_name: 'Second' }, { round: 4, race_name: 'Future' }], drivers: { OLD: { identity: { code: 'OLD', name: 'Historic Driver' }, cumulative_points: [15, 0, null, null], points_per_round: [15, 0, null, null], totals: { points: 15 } }, NEW: { identity: { code: 'NEW', name: 'Other Driver' }, cumulative_points: [20, 10, 15, null], totals: { points: 20 } } } } });
  const model = progressionModel(hass, entry, configModule('progression', { selected: ['OLD'] }));
  assert.deepEqual(model.series[0].values.map(item => item.value), [0, null, 15, null]);
  assert.deepEqual(seriesSegments(model.series[0].values), [[{ index: 0, round: 1, value: 0 }], [{ index: 2, round: 3, value: 15 }]]);
  const range = progressionModel(hass, entry, configModule('progression', { start_round: '2', end_round: '3' }));
  assert.deepEqual(range.rounds.map(item => item.id), [2, 3]); assert.deepEqual(range.series[0].values.map(item => item.value), [15, 20]);
  const completed = progressionModel(hass, entry, configModule('progression', { show_future_rounds: false }));
  assert.deepEqual(completed.rounds.map(item => item.id), [1, 2, 3]);
  assert.deepEqual(completed.series.find(item => item.id === 'OLD').values.map(item => item.value), [0, null, 15]);
  assert.equal(progressionModel(hass, entry, configModule('progression', { start_round: '3', end_round: '1' })).rounds.length, 0);
});

test('chart axes use readable intervals while preserving negative corrections and discrete wins', async () => {
  const { chartAxis } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/season-data.js');
  assert.deepEqual(chartAxis([0, 267]).ticks, [0, 100, 200, 300]);
  const correction = chartAxis([-2, 25]); assert.ok(correction.low <= -2); assert.ok(correction.high >= 25);
  assert.deepEqual(chartAxis([0, 1], true).ticks, [0, 1]);
  assert.ok(chartAxis([null, null]).ticks.length > 1);
});


test('lap duration axes show small differences without forcing a zero baseline or collapsing a flat series', () => {
  const axis = chartAxis([81.5, 81.6], false, false);
  assert.ok(axis.low > 80); assert.ok(axis.high >= 81.6); assert.ok(axis.high - axis.low < 1);
  const flat = chartAxis([81.5, 81.5], false, false);
  assert.ok(flat.low < flat.high); assert.ok(flat.ticks.every(Number.isFinite));
  assert.ok(chartAxis([81.5, 81.6]).low === 0);
});
