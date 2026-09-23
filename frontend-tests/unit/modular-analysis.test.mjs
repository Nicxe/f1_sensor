import assert from 'node:assert/strict';
import test from 'node:test';
import { timelineModel, battlesModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
const module = (options = {}, extra = {}) => normalizeConfig({ modules: [{ type: 'timeline', options, ...extra }] }).modules[0];

test('timeline retains corrected revisions, rejects other sessions and labels inferred exchanges', () => {
  const snapshot = makeDemo().preview.analysis;
  snapshot.timeline.events.push({ ...snapshot.timeline.events[1], revision: 1, title: 'Obsolete title' }, { ...snapshot.timeline.events[0], event_id: 'other', session_id: 'old-session', title: 'Old session' });
  const model = timelineModel(snapshot, module());
  assert.equal(model.rows.length, 2); assert.equal(model.rows[0].revision, 2);
  assert.equal(model.rows[0].derived, true); assert.equal(model.rows[0].analysis_quality, .55);
  assert.equal(model.rows[0].incident_drivers, 'LEC / NOR'); assert.equal(model.rows[1].derived, false);
  assert.equal(timelineModel(snapshot, module({}, { driver: 'NOR' })).rows.length, 1);
  assert.equal(timelineModel(snapshot, module({}, { team: 'Ferrari' })).rows.length, 1);
});

test('timeline snapshot replacement handles rewind without resurrecting removed events', () => {
  const snapshot = makeDemo().preview.analysis;
  const original = timelineModel(snapshot, module()); assert.equal(original.total, 2);
  const rewind = { ...snapshot, timeline: { events: [snapshot.timeline.events[0]] } };
  assert.equal(timelineModel(rewind, module()).total, 1);
  assert.equal(timelineModel({ ...snapshot, timeline: { events: [] } }, module()).total, 0);
  assert.equal(timelineModel(null, module()).pending, true); assert.equal(timelineModel({ protocol_version: 9 }, module()).pending, true);
});

test('unknown confidence and missing timestamps stay unknown; category filtering does not reclassify the source', () => {
  const snapshot = makeDemo().preview.analysis;
  snapshot.timeline.events[0].confidence = -1; snapshot.timeline.events[0].occurred_at = null;
  const model = timelineModel(snapshot, module({ categories: ['race_control'] }));
  assert.equal(model.rows[0].analysis_quality, null); assert.equal(model.rows[0].event_time, null);
  assert.equal(model.rows[0].analysis_category, 'race_control');
});

test('strategy separates clean and recorded pace, preserves zero age and sample quality and never filters compound aggregates by driver', async () => {
  const { strategyModel } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js');
  const snapshot = makeDemo().preview.analysis;
  const m = normalizeConfig({ modules: [{ type: 'strategy', driver: '16' }] }).modules[0];
  const model = strategyModel(snapshot, m);
  assert.equal(model.rows.length, 1); assert.equal(model.rows[0].stint_start_age, 0);
  assert.equal(model.rows[0].clean_pace, 81.12); assert.equal(model.rows[0].raw_pace, 81.5);
  assert.equal(model.rows[0].clean_samples, 6); assert.equal(model.rows[0].excluded_samples, 2);
  assert.equal(model.rows[0].strategy_pit_loss, null); assert.equal(model.rows[0].derived, true);
  const compounds = normalizeConfig({ modules: [{ type: 'strategy', driver: '16', options: { content: 'compound_comparison' } }] }).modules[0];
  assert.equal(strategyModel(snapshot, compounds).rows.length, 3);
  assert.equal(strategyModel(snapshot, compounds).rows[0].compound_gap, 0);
});

test('empty and low-coverage strategy remains explicit instead of producing a pace prediction', async () => {
  const { strategyModel } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js');
  const snapshot = makeDemo().preview.analysis, m = normalizeConfig({ modules: [{ type: 'strategy' }] }).modules[0];
  snapshot.strategy.stints[0].adjusted_median_clean_pace = null; snapshot.strategy.stints[0].sample_count = 0;
  snapshot.strategy.stints[0].confidence = 0; snapshot.strategy.stints[0].degradation_seconds_per_lap = null;
  const model = strategyModel(snapshot, m);
  const row = model.rows.find(item => item.number === '16');
  assert.equal(row.clean_pace, null); assert.equal(row.clean_samples, 0); assert.equal(row.analysis_quality, 0); assert.equal(row.degradation, null);
  assert.equal(strategyModel(null, m).pending, true);
  assert.equal(strategyModel(makeDemo('before').preview.analysis, m).rows.length, 0);
});

test('battle history retains distinct start/end observations while replacement snapshots remove obsolete active pairs', () => {
  const snapshot = makeDemo().preview.analysis;
  const active = normalizeConfig({ modules: [{ type: 'battles' }] }).modules[0];
  const history = normalizeConfig({ modules: [{ type: 'battles', options: { content: 'battle_history' } }] }).modules[0];
  const rows = battlesModel(snapshot, history).rows;
  assert.equal(rows.length, 2); assert.notEqual(rows[0].id, rows[1].id);
  assert.deepEqual(rows.map(row => row.kind), ['battle_ended', 'battle_started']);
  assert.equal(battlesModel(snapshot, active).rows[0].battle_status, 'active_battle');
  assert.equal(battlesModel({ ...snapshot, battles: { active: [] } }, active).total, 0);
  assert.equal(battlesModel(null, active).pending, true);
});

test('position exchanges keep source classification, before/after positions and missing evidence distinct', () => {
  const snapshot = makeDemo().preview.analysis;
  const m = normalizeConfig({ modules: [{ type: 'battles', options: { content: 'position_exchanges' } }] }).modules[0];
  const row = battlesModel(snapshot, m).rows[0];
  assert.equal(row.battle_status, 'position_exchange'); assert.equal(row.derived, true);
  assert.deepEqual(row.exchange_positions, [{ driver: 'LEC', before: 1, after: 2 }, { driver: 'NOR', before: 2, after: 1 }]);
  snapshot.position_exchanges[0].confidence = null;
  snapshot.position_exchanges[0].gap_seconds = -1;
  snapshot.position_exchanges[0].positions_after['16'] = 0;
  const missing = battlesModel(snapshot, m).rows[0];
  assert.equal(missing.analysis_quality, null); assert.equal(missing.battle_gap, null); assert.equal(missing.exchange_positions[0].after, null);
  assert.equal(battlesModel(snapshot, { ...m, options: { ...m.options, minimum_score: 1 } }).total, 0);
});

test('battle filters use both drivers, reject wrong sessions and do not fabricate a timestamp', () => {
  const snapshot = makeDemo().preview.analysis;
  const m = normalizeConfig({ modules: [{ type: 'battles', driver: 'NOR', team: 'McLaren', options: { minimum_score: 80 } }] }).modules[0];
  const model = battlesModel(snapshot, m); assert.equal(model.total, 1); assert.equal(model.rows[0].event_time, undefined);
  snapshot.battles.active.push({ ...snapshot.battles.active[0], battle_id: 'old', session_id: 'other' });
  assert.equal(battlesModel(snapshot, m).total, 1);
  assert.equal(battlesModel(snapshot, { ...m, options: { ...m.options, kinds: ['battle_ended'] } }).total, 0);
});

test('strategy comparisons retain both teammates, exact pace, stop laps and observed positions', async () => {
  const { strategyModel } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js');
  const snapshot = makeDemo().preview.analysis;
  const m = content => normalizeConfig({ modules: [{ type: 'strategy', driver: 'HAM', options: { content } }] }).modules[0];
  const comparison = strategyModel(snapshot, m('teammates'));
  assert.equal(comparison.total, 1); assert.equal(comparison.rows[0].incident_drivers, 'LEC / HAM');
  assert.deepEqual(comparison.rows[0].comparison_pace, [{ driver: 'LEC', value: 81.12 }, { driver: 'HAM', value: 81.32 }]);
  assert.equal(comparison.rows[0].pace_leader, 'LEC'); assert.equal(comparison.rows[0].comparison_gap, .2);
  const outcome = strategyModel(snapshot, m('pit_outcomes')).rows[0];
  assert.equal(outcome.strategy_outcome, 'undercut_succeeded');
  assert.deepEqual(outcome.comparison_stops, [{ driver: 'HAM', value: 10 }, { driver: 'LEC', value: 12 }]);
  assert.deepEqual(outcome.exchange_positions[0], { driver: 'HAM', before: 3, after: 2 });
  snapshot.strategy.teammate_comparisons[0].delta_seconds = 0;
  assert.equal(strategyModel(snapshot, m('teammates')).rows[0].equal_pace, true);
  assert.equal(strategyModel(snapshot, m('teammates')).rows[0].pace_leader, null);
});

test('crossover stays within the observed range, preserves zero age and ignores unsupported driver focus', async () => {
  const { strategyModel } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js');
  const snapshot = makeDemo().preview.analysis;
  const m = normalizeConfig({ modules: [{ type: 'strategy', driver: 'unknown', team: 'unknown', options: { content: 'crossover' } }] }).modules[0];
  const raw = snapshot.strategy.compound_crossover_indications[0];
  assert.equal(strategyModel(snapshot, m).rows[0].crossover_age, 8.5);
  raw.estimated_tyre_age_laps = 20; assert.equal(strategyModel(snapshot, m).rows[0].crossover_age, null);
  assert.equal(strategyModel(snapshot, m).rows[0].crossover_pace, null);
  raw.observed_age_range = [0, 12]; raw.estimated_tyre_age_laps = 0;
  assert.equal(strategyModel(snapshot, m).rows[0].crossover_age, 0);
  assert.equal(strategyModel(snapshot, m).rows[0].crossover_pace, 82.13);
  assert.equal(strategyModel(snapshot, { ...m, options: { ...m.options, compounds: ['WET'] } }).total, 0);
});

test('strategy quality filters exclude missing evidence only when the user sets a requirement', async () => {
  const { strategyModel } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js');
  const snapshot = makeDemo().preview.analysis;
  const m = normalizeConfig({ modules: [{ type: 'strategy', driver: '16' }] }).modules[0];
  snapshot.strategy.stints[0].confidence = null;
  assert.equal(strategyModel(snapshot, m).total, 1);
  assert.equal(strategyModel(snapshot, { ...m, options: { ...m.options, minimum_score: 1 } }).total, 0);
  assert.equal(strategyModel(snapshot, { ...m, options: { ...m.options, minimum_clean_laps: 7 } }).total, 0);
  assert.equal(strategyModel(snapshot, { ...m, options: { ...m.options, minimum_clean_laps: 6 } }).total, 1);
});
