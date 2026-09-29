import assert from 'node:assert/strict';
import test from 'node:test';
import { hasTimeVisibility, visibilityMediaQueries, visibilityMet } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/visibility.js';

const hass = {
  config: { time_zone: 'UTC' },
  locale: { time_zone: 'server' },
  user: { id: 'user-1' },
  states: {
    'input_boolean.f1': { state: 'on', attributes: {} },
    'sensor.temperature': { state: '22', attributes: { apparent: 24 } },
    'sensor.lower_limit': { state: '20', attributes: {} },
    'person.viewer': { state: 'home', attributes: { user_id: 'user-1' } },
  },
};
const environment = { now: new Date('2026-09-18T12:30:00Z'), matchMedia: query => ({ matches: query === '(min-width: 768px)' }) };

test('Home Assistant-style module conditions use AND at the top level', () => {
  const conditions = [
    { condition: 'state', entity: 'input_boolean.f1', state: 'on' },
    { condition: 'numeric_state', entity: 'sensor.temperature', above: 'sensor.lower_limit', below: 30 },
    { condition: 'numeric_state', entity: 'sensor.temperature', attribute: 'apparent', above: 23 },
    { condition: 'screen', media_query: '(min-width: 768px)' },
    { condition: 'user', users: ['user-1'] },
    { condition: 'location', locations: ['home'] },
    { condition: 'time', after: '12:00', before: '13:00', weekdays: ['fri'] },
  ];
  assert.equal(visibilityMet(conditions, hass, environment), true);
  assert.equal(visibilityMet([...conditions, { condition: 'state', entity: 'input_boolean.f1', state: 'off' }], hass, environment), false);
});

test('nested AND, OR and NOT conditions fail closed for missing state', () => {
  assert.equal(visibilityMet([{ condition: 'or', conditions: [
    { condition: 'state', entity: 'sensor.missing', state: 'ready' },
    { condition: 'and', conditions: [
      { condition: 'state', entity: 'input_boolean.f1', state_not: 'off' },
      { condition: 'not', conditions: [{ condition: 'location', locations: ['away'] }] },
    ] },
  ] }], hass, environment), true);
  assert.equal(visibilityMet([{ condition: 'state', entity: 'sensor.missing', state: 'ready' }], hass, environment), false);
});

test('time ranges can cross midnight and visibility listeners are discoverable recursively', () => {
  assert.equal(visibilityMet([{ condition: 'time', after: '22:00', before: '06:00' }], hass, { ...environment, now: new Date('2026-09-18T23:00:00Z') }), true);
  const conditions = [{ condition: 'or', conditions: [
    { condition: 'screen', media_query: '(max-width: 767px)' },
    { condition: 'screen', media_query: '(max-width: 767px)' },
    { condition: 'time', after: '08:00' },
  ] }];
  assert.deepEqual(visibilityMediaQueries(conditions), ['(max-width: 767px)']);
  assert.equal(hasTimeVisibility(conditions), true);
});
