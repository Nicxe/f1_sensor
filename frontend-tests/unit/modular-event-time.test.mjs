import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { timelineModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';

const event = (event_id, occurred_at, extra = {}) => ({ event_id, occurred_at, session_id: '1299:11406:Practice 2', revision: 1, ...extra });
const snapshot = events => ({ protocol_version: 1, session_id: '1299:11406:Practice 2', timeline: { events } });
const module = (options = {}) => normalizeConfig({ modules: [{ type: 'timeline', options }] }).modules[0];
const utcField = { event_time_basis: 'utc_field' };

// Actual Sao Paulo FP2 timestamps: Race Control.txt line 11 and TeamRadio.txt line 7.
const fp2 = [
  event('law-radio', '2026-11-06T19:29:53.53Z', { sequence: 2, category: 'radio' }),
  event('alb-radio', '2026-11-06T19:29:53.762Z', { sequence: 3, category: 'radio' }),
  event('str-lap-deleted', '2026-11-06T19:30:19', { sequence: 4, category: 'lap_control', focus_observation: utcField }),
];

for (const timezone of ['UTC', 'Europe/Stockholm', 'America/New_York']) {
  test(`event times and FP2 chronology do not depend on the browser zone: ${timezone}`, () => {
    const analysisUrl = new URL('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/analysis-data.js', import.meta.url).href;
    const configUrl = new URL('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js', import.meta.url).href;
    const script = `
      import { timelineModel } from ${JSON.stringify(analysisUrl)};
      import { normalizeConfig } from ${JSON.stringify(configUrl)};
      const snapshot = ${JSON.stringify(snapshot(fp2))};
      const module = order => normalizeConfig({ modules: [{ type: 'timeline', options: { order } }] }).modules[0];
      const newest = timelineModel(snapshot, module('newest')).rows;
      const oldest = timelineModel(snapshot, module('oldest')).rows;
      const boundaries = ['2025-07-06T14:05:48', '2026-11-06T19:30:19', '2026-03-29T02:30:00', '2026-03-29T03:00:00', '2026-10-25T02:30:00'];
      const moments = boundaries.map(occurred_at => {
        const candidate = { ...snapshot, timeline: { events: [{ ...snapshot.timeline.events[2], occurred_at }] } };
        return Date.parse(timelineModel(candidate, module('newest')).rows[0].event_time);
      });
      console.log(JSON.stringify({ newest: newest.map(row => row.eventId), oldest: oldest.map(row => row.eventId),
        rcTime: newest.find(row => row.eventId === 'str-lap-deleted').event_time, moments }));
    `;
    const result = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', script], {
      env: { ...process.env, TZ: timezone }, encoding: 'utf8',
    }));
    assert.deepEqual(result.newest, ['str-lap-deleted', 'alb-radio', 'law-radio']);
    assert.deepEqual(result.oldest, ['law-radio', 'alb-radio', 'str-lap-deleted']);
    assert.equal(result.rcTime, '2026-11-06T19:30:19Z');
    assert.deepEqual(result.moments, ['2025-07-06T14:05:48Z', '2026-11-06T19:30:19Z', '2026-03-29T02:30:00Z', '2026-03-29T03:00:00Z', '2026-10-25T02:30:00Z'].map(Date.parse));
  });
}

test('unknown, ambiguous and invalid event times stay unknown without borrowing observation times', () => {
  const values = [null, undefined, '', '2026-11-06T19:30:19', '2026-11-06', '2026-02-30T19:30:19Z',
    '2026-11-06T24:00:00Z', '2026-11-06T19:30:19+24:00', '2026-11-06T19:30Z', '0000-01-01T00:00:00Z', 'invalid', 0, {}];
  const rows = timelineModel(snapshot(values.map((value, index) => event(String(index), value, {
    focus_observation: { event_time_basis: 'single_frame', timing_as_of: { source_time_ms: 1793993419000 } },
  }))), module()).rows;
  assert.equal(rows.length, values.length);
  assert.ok(rows.every(row => row.event_time === null));
  const invalidProvenUtc = ['2026-02-30T19:30:19', '2026-11-06', '2026-11-06T24:00:00', '2026-11-06T19:30'];
  for (const value of invalidProvenUtc) {
    assert.equal(timelineModel(snapshot([event('invalid', value, { focus_observation: utcField })]), module()).rows[0].event_time, null);
  }
});

test('canonical event times preserve offsets and source fractions without reinterpreting them', () => {
  const values = ['2026-11-06T19:19:44.7428222Z', '2025-07-06T16:05:48+02:00', '2025-07-06T09:05:48-05:00', '1970-01-01T00:00:00Z'];
  for (const value of values) {
    assert.equal(timelineModel(snapshot([event('value', value)]), module()).rows[0].event_time, value);
  }
  assert.equal(timelineModel(snapshot([event('fraction', '2026-11-06T19:19:44.7428222', { focus_observation: utcField })]), module()).rows[0].event_time, '2026-11-06T19:19:44.7428222Z');
  assert.equal(timelineModel(snapshot([event('lowercase', '2026-11-06T19:19:44.7428222z')]), module()).rows[0].event_time, '2026-11-06T19:19:44.7428222Z');
});

test('canonical and legacy UTC events share chronology while revisions and same-instant ties keep their identity', () => {
  const events = [
    event('rc', '2026-11-06T19:30:19Z', { sequence: 4, revision: 2, title: 'Corrected event' }),
    event('rc', '2026-11-06T19:30:19', { sequence: 4, title: 'Old event', focus_observation: utcField }),
    event('equivalent', '2026-11-06T20:30:19+01:00', { sequence: 5 }),
    event('radio', '2026-11-06T19:29:53.762Z', { sequence: 3 }),
  ];
  const rows = timelineModel(snapshot(events), module()).rows;
  assert.deepEqual(rows.map(row => row.eventId), ['equivalent', 'rc', 'radio']);
  assert.equal(rows[1].revision, 2);
  assert.equal(rows[1].analysis_title, 'Corrected event');
  assert.equal(rows[1].id, '1299:11406:Practice 2:rc');
});
