import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig, importConfig, exportConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';

const configure = options => normalizeConfig({ modules: [{ type: 'lap_chart', options }] });

test('Race Trace selection and anchor survive configuration round trips without mutating their input', () => {
  const options = { metric: 'cumulative_lap_delta', reference_driver: '04', selected: ['4', '016', '63', '1'], anchor_lap: 24, start_lap: 30, end_lap: 80 };
  const original = structuredClone(options);
  const config = configure(options), saved = config.modules[0].options;
  assert.equal(saved.reference_driver, '4');
  assert.deepEqual(saved.selected, ['16', '63', '1']);
  assert.equal(saved.anchor_lap, 24);
  assert.equal(saved.start_lap, 30);
  assert.equal(saved.end_lap, 80);
  assert.deepEqual(importConfig(exportConfig(config)), config);
  assert.deepEqual(options, original);
});

test('Race Trace never fills an empty reference or comparison list from session order', () => {
  const options = configure({ metric: 'cumulative_lap_delta' }).modules[0].options;
  assert.equal(options.reference_driver, '');
  assert.equal(options.anchor_lap, 0);
  assert.deepEqual(options.selected, []);
  assert.deepEqual(configure({ ...options, reference_driver: '99' }).modules[0].options.selected, []);
});

test('Race Trace rejects a fifth distinct driver and normalizes equivalent saved driver numbers', () => {
  assert.throws(() => configure({ metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['1', '16', '63', '99'] }), /options.selected:/);
  const saved = configure({ metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['01', '1', '16', '63'] }).modules[0].options;
  assert.deepEqual(saved.selected, ['1', '16', '63']);
  assert.equal(saved.reference_driver, '4');
});

test('Race Trace rejects malformed driver and anchor values with precise paths', () => {
  for (const reference_driver of ['0', '100', '-1', 'VER', '4.0', '4 ', 4, true]) {
    assert.throws(() => configure({ metric: 'cumulative_lap_delta', reference_driver }), /options.reference_driver:/);
  }
  for (const selected of [['0'], ['100'], ['VER'], [''], [true]]) {
    assert.throws(() => configure({ metric: 'cumulative_lap_delta', reference_driver: '4', selected }), /options.selected/);
  }
  for (const anchor_lap of [-1, 501, 1.5, '24', true]) {
    assert.throws(() => configure({ metric: 'cumulative_lap_delta', anchor_lap }), /options.anchor_lap:/);
  }
  assert.equal(configure({ metric: 'cumulative_lap_delta', anchor_lap: 500 }).modules[0].options.anchor_lap, 500);
});

test('existing lap chart measures retain defaults and their broader driver selection', () => {
  for (const metric of ['lap_time', 'lap_change']) {
    const saved = configure({ metric, selected: ['LEC', '4', '63', '1', '14'], series_limit: 12 }).modules[0].options;
    assert.equal(saved.metric, metric);
    assert.deepEqual(saved.selected, ['LEC', '4', '63', '1', '14']);
    assert.equal(saved.series_limit, 12);
  }
  const defaults = configure({}).modules[0].options;
  assert.equal(defaults.metric, 'lap_time');
  assert.equal(defaults.series_limit, 5);
  assert.equal(defaults.start_lap, 0);
  assert.equal(defaults.end_lap, 0);
});

test('Race Trace event markers are opt-in and survive configuration round trips', () => {
  for (const metric of ['lap_time', 'lap_change', 'cumulative_lap_delta']) {
    assert.deepEqual(configure({ metric }).modules[0].options.event_markers, []);
  }
  const source = { metric: 'cumulative_lap_delta', reference_driver: '4', event_markers: ['pit', 'sc', 'vsc', 'red_flag'] };
  const before = structuredClone(source), config = configure(source);
  assert.deepEqual(config.modules[0].options.event_markers, source.event_markers);
  assert.deepEqual(importConfig(exportConfig(config)), config);
  assert.deepEqual(source, before);
  assert.deepEqual(configure({ metric: 'lap_time', event_markers: ['pit'] }).modules[0].options.event_markers, ['pit']);
});

test('Race Trace marker configuration rejects invalid categories and duplicate selections', () => {
  for (const event_markers of [true, 'pit', ['future_kind'], ['pit', 'pit'], [1], [null]]) {
    assert.throws(() => configure({ metric: 'cumulative_lap_delta', event_markers }), /options.event_markers:/);
  }
});
