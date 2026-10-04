import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { seconds, number, formatTime, lapChange, positionChange, SectorStore, timingStatus, PALETTES, statusColors, contrast, safeImageUrl, cardAccent, logoDimensions } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';

const lap = (n, times, completed = n - 1) => ({ racing_number: '16', completed_laps: completed, sector_current_lap: n, sectors: { current: Object.fromEntries(times.map((time, index) => [`sector_${index + 1}`, { time, lap: n }])) } });

test('decorative accents have explicit fallbacks and never modify timing meaning or palettes', () => {
  const original = JSON.stringify(PALETTES), appearance = { style: 'ha', accent: '#2255bb', accent_team: 'Ferrari' };
  assert.deepEqual(cardAccent(appearance), { visible: false, color: '#2255bb', missingTeamColor: false });
  assert.equal(cardAccent({ ...appearance, style: 'f1' }).visible, true);
  assert.equal(cardAccent({ ...appearance, accent_mode: 'f1' }).color, '#e10600');
  assert.equal(cardAccent({ ...appearance, accent_mode: 'custom' }).color, '#2255bb');
  assert.equal(cardAccent({ ...appearance, accent_mode: 'neutral' }).visible, false);
  for (const team of [undefined, { name: 'Ferrari', color: 'red;display:none' }, { name: 'Other', color: '#ff0000' }]) {
    assert.deepEqual(cardAccent({ ...appearance, accent_mode: 'team' }, team ? [team] : [], 'light'), { visible: true, color: '#778397', missingTeamColor: true });
  }
  assert.equal(cardAccent({ ...appearance, accent_mode: 'team' }, [{ name: 'Ferrari', color: '#ff0000' }]).color, '#ff0000');
  assert.equal(JSON.stringify(PALETTES), original);
  assert.deepEqual(['small', 'normal', 'large'].map(logoDimensions).map(v => v.frame), [24, 32, 40]);
});

test('timing parsing never invents a zero or accepts malformed durations', () => {
  for (const value of [null, undefined, '', ' ', false, {}, [], 'unknown', '1:99.123', '2:', -1, 0]) assert.equal(seconds(value), null, String(value));
  assert.equal(number(0), 0);
  assert.equal(number(''), null);
  assert.equal(seconds('1:20.750'), 80.75);
  assert.equal(formatTime(59.9996), '1:00.000');
  assert.equal(formatTime(null), '—');
});

test('#530 lap arrows and position arrows use separate comparisons', () => {
  assert.deepEqual(lapChange('1:20.750', '1:21.000', 12, 11), { value: -0.25, symbol: '▼', status: 'faster', comparison: 'previous_completed_lap', current_lap: 12, reference_lap: 11 });
  assert.equal(lapChange(82, 81).symbol, '▲');
  assert.equal(lapChange(81, 81).symbol, '=');
  assert.equal(lapChange(81, null), null);
  assert.deepEqual(positionChange(2, 5), { value: 3, symbol: '↑', status: 'gain', comparison: 'grid' });
  assert.equal(positionChange(0, 1), null);
});

test('#404 purple, green and yellow retain distinct meanings in existing practice fixture', () => {
  const cases = JSON.parse(readFileSync(new URL('./practice-cases.json', import.meta.url), 'utf8'));
  const driver = cases.test_practice_card_exposes_current_sector_values_and_timing_classes.position_drivers[0];
  const sectors = new SectorStore().select('practice', driver);
  assert.deepEqual(sectors.map(timingStatus), ['overall', 'personal', 'timed']);
  assert.equal(timingStatus({ time: 80, personal_fastest: true, deleted: true }), 'deleted');
  assert.equal(timingStatus({ time: 80, overall_fastest: true, previous_lap: true }), 'previous');
});

test('#566 coherent sectors retain a completed lap until new S1 and never blend laps', () => {
  const store = new SectorStore();
  const previous = store.select('race', lap(10, [25.1, 30.2, 28.3], 10));
  assert.deepEqual(previous.map(timingStatus), ['previous', 'previous', 'previous']);
  const waiting = store.select('race', { racing_number: '16', completed_laps: 10, sector_current_lap: 11 });
  assert.deepEqual(waiting.map(item => item.time), [25.1, 30.2, 28.3]);
  const current = store.select('race', { ...lap(11, [24.9]), sector_state: 's1_done' });
  assert.deepEqual(current.map(item => item.time), [24.9, null, null]);
  assert.deepEqual(current.map(item => item.lap), [11, 11, 11]);
  const latest = store.select('race', lap(11, [24.9]), 'latest');
  assert.deepEqual(latest.map(item => item.lap), [11, 10, 10]);
  assert.deepEqual(latest.map(timingStatus), ['timed', 'previous', 'previous']);
});

test('session changes, replay generation and backward seeks discard sector history', () => {
  const store = new SectorStore();
  store.select('race:live', lap(10, [25, 30, 28]));
  assert.deepEqual(store.select('qualifying:live', lap(1, [26])).map(item => item.time), [26, null, null]);
  store.select('qualifying:live', lap(5, [25, 30, 28]));
  assert.deepEqual(store.select('qualifying:live', lap(2, [27])).map(item => item.time), [27, null, null]);
  assert.deepEqual(store.select('qualifying:seek-2', { racing_number: '16' }).map(item => item.time), [null, null, null]);
});

test('corrections clear values and sectors without a lap do not borrow a different lap ID', () => {
  const store = new SectorStore();
  store.select('race', lap(10, [25, 30, 28]));
  assert.equal(store.select('race', lap(10, [25, null]))[1].time, null);
  const mixed = store.select('race', { racing_number: '16', sectors: { current: { sector_1: { lap: 11, time: 24 }, sector_2: { time: 30 } } } });
  assert.equal(mixed[1].time, null);
  assert.equal(mixed[1].lap, 11);
});

test('each built-in or custom timing badge chooses text with at least 4.5 contrast', () => {
  for (const mode of ['dark', 'light']) for (const status of Object.keys(PALETTES[mode])) {
    const { background, color } = statusColors(status, mode);
    assert.ok(contrast(background, color) >= 4.5, `${mode}:${status}`);
  }
  for (const hex of ['#ffffff', '#000000', '#ff0000', '#777777', '#00ff00', '#0000ff']) {
    const badge = statusColors('personal', 'dark', { personal: hex });
    assert.equal(badge.background, hex);
    assert.ok(contrast(badge.background, badge.color) >= 4.5);
  }
});

test('image fallback rejects scripts, credentials and ambiguous remote schemes', () => {
  for (const url of ['javascript:alert(1)', '//example.com/logo.svg', 'https://user:secret@example.com/x', '/\\evil.example/x', 'data:image/svg+xml,script']) assert.equal(safeImageUrl(url), null);
  assert.equal(safeImageUrl('/local/logo.svg'), '/local/logo.svg');
  assert.equal(safeImageUrl('https://example.com/logo.svg'), 'https://example.com/logo.svg');
});
