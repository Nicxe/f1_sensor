import assert from 'node:assert/strict';
import test from 'node:test';
import { strategyModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';

const module = content => normalizeConfig({ modules: [{ type: 'strategy', options: { content } }] }).modules[0];
const matched = () => ({ status: 'ready', method: 'matched_lap_differences', drivers: [16, 44], used_pairs: 3, possible_pairs: 4,
  excluded_pairs: 1, excluded_reason_counts: { unknown_tyre_age: 1 }, lap_range: [2, 5], delta_seconds: -1, q1_seconds: -4.5, q3_seconds: -1, faster_driver: 16,
  pairs: [{ lap_number: 2, first_seconds: 90, second_seconds: 91, delta_seconds: -1 }, { lap_number: 3, first_seconds: 91, second_seconds: 99, delta_seconds: -8 }, { lap_number: 5, first_seconds: 100, second_seconds: 101, delta_seconds: -1 }] });

test('strategy displays signed matched differences and supporting pairs without promoting legacy medians', () => {
  const snapshot = makeDemo().preview.analysis;
  snapshot.strategy.teammate_comparisons[0].matched_comparison = matched();
  const row = strategyModel(snapshot, module('teammates')).rows[0];
  assert.equal(row.comparison_gap, -1);
  assert.equal(row.pace_leader, 'LEC');
  assert.equal(row.comparison_evidence.used_pairs, 3);
  assert.deepEqual(row.comparison_evidence.lap_range, [2, 5]);
  assert.deepEqual(row.comparison_evidence.spread, [-4.5, -1]);
  assert.deepEqual(row.comparison_evidence.exclusion_reasons, [{ reason: 'unknown_tyre_age', count: 1 }]);
  assert.equal(row.comparison_evidence.pairs.length, 3);
  assert.equal(row.comparison_evidence.pairs[0].first_time, 90);
  assert.equal(row.comparison_evidence.pairs[0].second_time, 91);
  delete snapshot.strategy.teammate_comparisons[0].matched_comparison;
  const legacy = strategyModel(snapshot, module('teammates')).rows[0];
  assert.equal(legacy.comparison_gap, null);
  assert.equal(legacy.pace_leader, null);
  assert.equal(legacy.comparison_evidence.status, 'descriptive');
  assert.equal(legacy.comparison_pace[0].value, 81.12);
});

test('insufficient matched evidence cannot show a winner or zero spread', () => {
  const snapshot = makeDemo().preview.analysis;
  snapshot.strategy.teammate_comparisons[0].matched_comparison = { ...matched(), status: 'insufficient_data', used_pairs: 2, delta_seconds: null, q1_seconds: null, q3_seconds: null };
  let row = strategyModel(snapshot, module('teammates')).rows[0];
  assert.equal(row.comparison_gap, null); assert.equal(row.pace_leader, null); assert.equal(row.equal_pace, false);
  assert.equal(row.comparison_evidence.spread, null);
  snapshot.strategy.teammate_comparisons[0].matched_comparison = { ...matched(), delta_seconds: 0, q1_seconds: -1, q3_seconds: 1 };
  row = strategyModel(snapshot, module('teammates')).rows[0];
  assert.equal(row.equal_pace, true); assert.equal(row.pace_leader, null);
});

test('strategy trend and stint-change loss need new evidence and preserve negative and zero estimates', () => {
  const snapshot = makeDemo().preview.analysis;
  const raw = snapshot.strategy.stints[0];
  raw.degradation_seconds_per_lap = 9; raw.pit_loss_seconds = 99;
  delete raw.lap_time_trend; delete raw.stint_change_estimate;
  let row = strategyModel(snapshot, module('stints')).rows.find(item => item.number === '16');
  assert.equal(row.degradation, null); assert.equal(row.strategy_pit_loss, null);
  raw.lap_time_trend = { status: 'ready', method: 'ols_lap_time_by_tyre_age', seconds_per_lap: .2, sample_count: 5, age_range: [0, 4], lap_range: [1, 5], laps: [1, 2, 3, 4, 5] };
  for (const value of [-1, 0, 20]) {
    raw.stint_change_estimate = { status: 'ready', method: 'observed_transition_lap_minus_previous_eligible_median', seconds: value, baseline_seconds: 90, baseline_laps: [1, 2, 3], transition_lap: 4, sample_count: 3 };
    row = strategyModel(snapshot, module('stints')).rows.find(item => item.number === '16');
    assert.equal(row.degradation, .2); assert.equal(row.strategy_pit_loss, value);
    assert.deepEqual(row.trend_evidence.laps, [1, 2, 3, 4, 5]);
    assert.deepEqual(row.pit_evidence.baseline_laps, [1, 2, 3]);
  }
});
