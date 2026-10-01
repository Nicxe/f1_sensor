import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { SectorStore } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js';
import { timingRows, scheduleRows, spoilerState, mergeEvents, weatherValues, filterRaceControl, sessionClock, lapChartModel, accentTeams } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
const entry = { entry_id: 'fixture', entities: { driver_positions: 'sensor.positions', driver_list: 'sensor.drivers', current_tyres: 'sensor.tyres', next_race: 'sensor.weekend', weather: 'sensor.weather' }, global_entities: { no_spoiler_mode: 'switch.renamed' } };
const state = (attributes, value = 'live') => ({ state: value, attributes, last_updated: '2026-09-13T13:30:00Z' });

test('weather converts raw measurements into HA temperature and wind units without relabeling unknown units', () => {
  const entry = { entities: { weather: 'sensor.weather', track_weather: 'sensor.track', session_status: 'sensor.status' } };
  const hass = { config: { unit_system: { temperature: '°F', wind_speed: 'mph' } }, states: {
    'sensor.weather': state({ current_temperature: 20, current_wind_speed: 10, race_temperature: 0, race_wind_speed: 0 }),
    'sensor.track': state({ air_temperature: 30, track_temperature: 40, wind_speed: 10 }),
    'sensor.status': state({}, 'live'),
  } };
  const read = content => weatherValues(hass, entry, { type: 'weather', options: { content } }).values;
  assert.equal(read('current_conditions').temperature.value, 68);
  assert.equal(read('current_conditions').temperature.unit, '°F');
  assert.ok(Math.abs(read('current_conditions').wind.value - 22.369362920544) < 1e-9);
  assert.equal(read('automatic_conditions').temperature.value, 86);
  assert.equal(read('automatic_conditions').track_temperature.value, 104);
  assert.equal(read('race_forecast').temperature.value, 32);
  assert.equal(read('race_forecast').wind.value, 0);
  hass.config.unit_system = { temperature: 'K', wind_speed: 'km/h' };
  assert.equal(read('current_conditions').temperature.value, 293.15);
  assert.equal(read('current_conditions').wind.value, 36);
  hass.states['sensor.track'].attributes = { air_temperature: 86, air_temperature_unit: 'fahrenheit', wind_speed: 36, wind_speed_unit: 'km/h' };
  hass.config.unit_system = { temperature: '°C', wind_speed: 'm/s' };
  assert.equal(read('automatic_conditions').temperature.value, 30);
  assert.equal(read('automatic_conditions').wind.value, 10);
  hass.states['sensor.track'].attributes.air_temperature_unit = 'custom';
  assert.equal(read('automatic_conditions').temperature.unit, 'custom');
  assert.equal(read('automatic_conditions').temperature.value, 86);
});

test('team accent choices use the selected available roster and disclose absent or conflicting colors', () => {
  const hass = { states: { 'sensor.drivers': state({ drivers: [null, { team: 'Ferrari', team_color: '#EE0000' }, { team: 'Ferrari', team_color: '#ee0000' }, { team: 'Ferrari' }, { team: 'No color', team_color: 'red;display:none' }, { team: 'Conflict', team_color: '#ffffff' }, { team: 'Conflict', team_color: '#000000' }] }) } };
  assert.deepEqual(accentTeams(hass, entry), [{ name: 'Conflict', color: null }, { name: 'Ferrari', color: '#ee0000' }, { name: 'No color', color: null }]);
  assert.deepEqual(accentTeams(hass, { ...entry, disabled_entities: ['driver_list'] }), []);
  assert.deepEqual(accentTeams(hass, { entities: { driver_list: 'sensor.other' } }), []);
  hass.states['sensor.drivers'].state = 'unavailable';
  assert.deepEqual(accentTeams(hass, entry), []);
});
const timingModule = (options = {}) => normalizeConfig({ modules: [{ type: 'timing', options }] }).modules[0];

test('existing driver history fixture yields joined identities, zero laps, tyres and correct best lap', () => {
  const fixture = JSON.parse(readFileSync(new URL('./practice-cases.json', import.meta.url), 'utf8')).test_practice_card_derives_laps_and_status_from_driver_history;
  const hass = { states: { 'sensor.positions': state({ drivers: fixture.position_drivers }), 'sensor.drivers': state({ drivers: fixture.driver_list }), 'sensor.tyres': state({ drivers: fixture.tyres_drivers }) } };
  const result = timingRows(hass, entry, { key: 'practice' }, new SectorStore(), timingModule());
  assert.deepEqual(result.rows.map(row => row.driver), ['SAI', 'RUS', 'COL']);
  assert.equal(result.rows[1].best_lap.time, 80.75);
  assert.equal(result.rows[1].lap_delta.value, -0.25);
  assert.equal(result.rows[1].status, 'in_pit');
  assert.equal(result.rows[1].tyre_age, 13);
  assert.equal(result.rows[2].laps, 0);
  assert.equal(result.rows[2].best_lap.time, null);
  assert.deepEqual(result.rows[1].history, []);
});

test('an official deleted best does not reappear from local history; a late start cannot invent a lap comparison', () => {
  const hass = { states: { 'sensor.positions': state({ drivers: { '16': { tla: 'LEC', completed_laps: 10, best_lap_time: null, laps: { 1: '1:20.000', 10: '1:21.000' } } } }) } };
  const [row] = timingRows(hass, entry, { key: 'race' }, new SectorStore(), timingModule({ history: 5 })).rows;
  assert.equal(row.best_lap.time, null);
  assert.equal(row.lap_delta, null);
  assert.deepEqual(row.history.map(item => item.lap), [10, 1]);
});

test('a pinned module ignores group driver focus and entity joins never cross entries', () => {
  const hass = { states: { 'sensor.positions': state({ drivers: [{ racing_number: '16', tla: 'LEC' }, { racing_number: '4', tla: 'NOR' }] }), 'sensor.other': state({ drivers: [{ racing_number: '16', name: 'Wrong entry' }] }) } };
  const module = { ...timingModule(), driver: '16' };
  const rows = timingRows(hass, entry, { key: 'race' }, new SectorStore(), module, { driver: '4' }).rows;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].driver, 'LEC');
});

test('global renamed spoiler switch protects every entry and unknown state fails closed', () => {
  assert.equal(spoilerState({ states: { 'switch.renamed': { state: 'on' } } }, entry), 'protected');
  assert.equal(spoilerState({ states: { 'switch.renamed': { state: 'off' } } }, entry), 'clear');
  assert.equal(spoilerState({ states: {} }, entry), 'unknown');
  assert.equal(spoilerState({ states: {} }, { entities: {} }), 'unknown');
  assert.equal(spoilerState({ states: {} }, { global_entities: {} }), 'unknown');
  assert.equal(spoilerState({ states: { 'switch.renamed': { state: 'off' } } }, entry, 'hide'), 'protected');
});

test('weekend schedule follows source times and omits absent sprint sessions without fabricating dates', () => {
  const hass = { states: { 'sensor.weekend': state({ season: '2026', round: '15', race_name: 'Azerbaijan Grand Prix', circuit_timezone: 'Asia/Baku', race_start_utc: '2026-09-26T11:00:00Z', qualifying_start_utc: '2026-09-25T12:00:00Z', first_practice_start_utc: '2026-09-24T08:30:00Z', sprint_start_utc: null }) } };
  const module = normalizeConfig({ modules: [{ type: 'calendar' }] }).modules[0];
  const rows = scheduleRows(hass, entry, module).rows;
  assert.deepEqual(rows.map(item => item.session), ['practice_1', 'qualifying', 'race']);
  assert.equal(rows[2].start, '2026-09-26T11:00:00Z');
  assert.equal(rows[2].timezone, 'Asia/Baku');
  assert.equal(new Set(rows.map(item => item.id)).size, 3);
});

test('forecast and missing measurements stay distinct from measured zero', () => {
  const hass = { states: { 'sensor.weather': state({ current_temperature: 0, current_humidity: null, race_precipitation_probability: 12 }) } };
  const { values } = weatherValues(hass, entry);
  assert.equal(values.temperature.value, 0);
  assert.equal(values.humidity.value, null);
  assert.equal(values.rain_probability.estimated, true);
});

test('Race Control snapshot and event overlap is deduplicated using source identity', () => {
  const event = { event_id: 'stream-id', message: 'YELLOW FLAG', utc: '2026-09-13T13:30:00Z', category: 'Flag', flag: 'YELLOW' };
  const events = mergeEvents([event], [{ ...event, event_id: 'log-id', sequence: 2 }]);
  assert.equal(events.length, 1);
  assert.equal(events[0].sequence, 2);
});

test('Race Control normalizes equivalent UTC strings without merging separate timestamp-free events', () => {
  const base = { message: 'TRACK CLEAR', category: 'Flag' };
  assert.equal(mergeEvents([{ ...base, utc: '2026-09-13T13:30:00Z' }], [{ ...base, utc: '2026-09-13T15:30:00+02:00' }]).length, 1);
  assert.equal(mergeEvents([{ ...base, event_id: 'first' }, { ...base, event_id: 'second' }]).length, 2);
});

test('session profiles distinguish sprint qualifying and preserve custom columns', async () => {
  const { timingFields, sessionKind } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js');
  assert.equal(sessionKind('Sprint Qualifying'), 'sprint_qualifying'); assert.equal(sessionKind('Sprint Shootout'), 'sprint_qualifying');
  assert.equal(sessionKind('Practice 2'), 'practice'); assert.equal(sessionKind('no_session'), null);
  const input = { fields: ['driver', 'last_lap'], options: { profile: 'auto' } };
  assert.ok(timingFields(input, 'Sprint Qualifying').includes('q1_time'));
  assert.ok(timingFields(input, 'Sprint').includes('gap'));
  assert.deepEqual(timingFields(input, 'no_session'), input.fields);
  assert.deepEqual(timingFields({ ...input, options: { profile: 'custom' } }, 'Qualifying'), input.fields);
});

test('qualifying times cannot leak into race rows and theoretical laps require coherent qualifying parts', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const { normalizeConfig } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js');
  const { sessionContext, timingRows } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js');
  const { SectorStore } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js');
  const demo = makeDemo('sprint_qualifying'), entry = demo.preview.entries[0];
  const module = normalizeConfig({ modules: [{ type: 'timing', options: { profile: 'auto' } }] }).modules[0];
  const model = () => timingRows(demo.hass, entry, sessionContext(demo.hass, entry), new SectorStore(), module);
  let rows = model().rows;
  assert.equal(rows[0].q1_time.time, 81.12); assert.equal(rows[0].q1_time.sprint, true); assert.equal(rows[3].q1_time.eliminated, true);
  const part = demo.hass.states[entry.entities.driver_positions].attributes.current_qualifying_part;
  const timed = rows.filter(row => row[`q${part}_time`].time !== null);
  const fastest = Math.min(...timed.map(row => row[`q${part}_time`].time));
  for (const row of timed) assert.ok(Math.abs(row.qualifying_gap - (row[`q${part}_time`].time - fastest)) < .00001);
  assert.ok(rows.filter(row => row[`q${part}_time`].time === null).every(row => row.qualifying_gap === null));
  assert.ok(Math.abs(rows[0].theoretical_lap - 80.774) < .00001);
  demo.hass.states[entry.entities.driver_positions].attributes.drivers[0].sectors.personal_best.sector_3.session_part = 1;
  assert.equal(model().rows[0].theoretical_lap, null);
  demo.hass.states[entry.entities.current_session].state = 'Race';
  rows = model().rows; assert.equal(rows[0].q1_time.time, null); assert.equal(rows[0].q1_position, null);
  assert.equal(rows[0].theoretical_lap, null); assert.equal(rows[0].qualifying_gap, null);
});

test('unavailable roster and tyres cannot relabel current timing using retained attributes', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const demo = makeDemo(), target = demo.preview.entries[0];
  demo.hass.states[target.entities.driver_list].attributes.drivers = [{ racing_number: '16', tla: 'OLD', full_name: 'Previous driver' }];
  demo.hass.states[target.entities.driver_list].state = 'unavailable';
  demo.hass.states[target.entities.current_tyres].state = 'unavailable';
  const result = timingRows(demo.hass, target, { key: 'current', name: 'Race' }, new SectorStore(), timingModule());
  assert.equal(result.rows[0].driver, 'LEC'); assert.equal(result.rows[0].name, 'Charles Leclerc');
  assert.equal(result.rows[0].tyre, null); assert.equal(result.rows[0].tyre_age, null);
});

test('Race Control accepts driver codes or numbers and preserves global messages only when selected', () => {
  const hass = { states: { 'sensor.drivers': state({ drivers: [{ racing_number: '4', tla: 'NOR' }] }) } };
  const rows = mergeEvents([
    { utc: '2026-09-13T13:30:00Z', message: 'TRACK CLEAR' },
    { utc: '2026-09-13T13:29:00Z', message: 'CAR 4 WARNING', car_number: '4' },
    { utc: '2026-09-13T13:28:00Z', message: 'CAR 16 WARNING', car_number: '16' },
    { utc: '2026-09-13T13:27:00Z', message: 'BLUE FLAG', flag: 'BLUE' },
    { utc: '2026-09-13T13:26:00Z', message: 'CAR 4 TRACK LIMITS', car_number: '4' },
  ]);
  const m = normalizeConfig({ modules: [{ type: 'race_control', driver: 'NOR' }] }).modules[0];
  assert.deepEqual(filterRaceControl(rows, hass, entry, m).map(row => row.message), ['TRACK CLEAR', 'CAR 4 WARNING', 'BLUE FLAG', 'CAR 4 TRACK LIMITS']);
  assert.equal(filterRaceControl(rows, hass, entry, { ...m, options: { ...m.options, global_messages: 'hide' } }).length, 2);
  assert.equal(filterRaceControl(rows, hass, entry, { ...m, options: { ...m.options, presentation: 'latest_message', order: 'oldest' } })[0].message, 'TRACK CLEAR');
  assert.deepEqual(filterRaceControl(rows, hass, entry, { ...m, options: { ...m.options, hide_blue_flags: true, hide_track_limits: true } }).map(row => row.message), ['TRACK CLEAR', 'CAR 4 WARNING']);
  hass.states['sensor.drivers'].state = 'unavailable';
  assert.deepEqual(filterRaceControl(rows, hass, entry, m).map(row => row.message), ['TRACK CLEAR', 'BLUE FLAG']);
});

test('clock values remain separate, preserve zero and pause, and reject wrong qualifying parts or unavailable sources', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const demo = makeDemo('qualifying'), entry = demo.preview.entries[0];
  const read = key => sessionClock(demo.hass, entry, key);
  assert.equal(read('session_time_elapsed').value, '0:30:00');
  assert.equal(read('session_time_remaining').value, '1:30:00');
  assert.equal(read('race_time_to_three_hour_limit').value, null);
  const race = makeDemo('race');
  assert.equal(sessionClock(race.hass, race.preview.entries[0], 'race_time_to_three_hour_limit').value, '2:30:00');
  const entity = demo.hass.states[entry.entities.session_time_remaining];
  entity.attributes.value_seconds = 0; entity.attributes.clock_phase = 'paused';
  assert.equal(read('session_time_remaining').value, '0:00:00'); assert.equal(read('session_time_remaining').phase, 'paused');
  entity.attributes.session_part = 1;
  assert.equal(read('session_time_remaining').value, null); assert.equal(read('session_time_remaining').contextMismatch, true);
  entity.attributes.session_part = 2; entity.state = 'unavailable';
  assert.equal(read('session_time_remaining').value, null);
  entity.state = '0:00:00'; entity.attributes.value_seconds = -1;
  assert.equal(read('session_time_remaining').value, null);
});


test('weather profiles use their own source fields and keep forecast, track and current values separate', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const { fieldDefinition, moduleFields } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js');
  const demo = makeDemo(), target = demo.preview.entries[0];
  const read = content => { const module = normalizeConfig({ modules: [{ type: 'weather', options: { content } }] }).modules[0]; return { module, model: weatherValues(demo.hass, target, module) }; };
  assert.equal(read('current_conditions').model.values.temperature.value, 24.5);
  assert.equal(read('current_conditions').model.values.rain_probability.value, 5);
  demo.hass.states[target.entities.weather].attributes.current_weather_code = 0;
  demo.hass.states[target.entities.weather].attributes.icon = 'mdi:weather-night';
  assert.equal(read('current_conditions').model.values.weather_condition.night, true);
  const forecast = read('race_forecast');
  assert.equal(forecast.model.values.temperature.value, 22.8);
  assert.equal(forecast.model.values.rain_probability.value, 15);
  assert.equal(forecast.model.values.precipitation.unit, 'mm');
  assert.equal(fieldDefinition(forecast.module, 'temperature').path, 'race_temperature');
  const track = read('track_conditions');
  assert.equal(track.model.values.temperature.value, 25.2);
  assert.equal(track.model.values.track_temperature.value, 43.8);
  assert.equal(track.model.values.rainfall.value, false); assert.equal(track.model.values.rainfall.unit, null);
  assert.equal(fieldDefinition(track.module, 'temperature').path, 'air_temperature');
  assert.equal(fieldDefinition(track.module, 'temperature').spoiler, true);
  assert.equal(moduleFields(track.module).includes('rain_probability'), false);
  assert.equal(track.model.context.updated, demo.hass.states[target.entities.track_weather].last_updated);
});

test('rain detection is a strict indicator and weather gaps or out-of-range data cannot become valid zeroes', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const demo = makeDemo(), target = demo.preview.entries[0];
  const module = normalizeConfig({ modules: [{ type: 'weather', options: { content: 'track_conditions' } }] }).modules[0];
  const attrs = demo.hass.states[target.entities.track_weather].attributes;
  for (const [raw, expected] of [[1, true], ['1', true], [true, true], [0, false], ['0', false], [false, false], [null, null], ['', null], [2, null], [-1, null]]) {
    attrs.rainfall = raw;
    assert.equal(weatherValues(demo.hass, target, module).values.rainfall.value, expected, String(raw));
  }
  attrs.humidity = 101; attrs.wind_speed = -1; attrs.wind_from_direction_degrees = 360; attrs.air_temperature = 0;
  let model = weatherValues(demo.hass, target, module);
  assert.equal(model.values.humidity.value, null); assert.equal(model.values.wind.value, null);
  assert.equal(model.values.wind_direction.value, 0); assert.equal(model.values.temperature.value, 0);
  attrs.wind_from_direction_degrees = 361; delete attrs.track_temperature;
  model = weatherValues(demo.hass, target, module);
  assert.equal(model.values.wind_direction.value, null); assert.equal(model.values.track_temperature.value, null);
  demo.hass.connection = { connected: false };
  assert.equal(weatherValues(demo.hass, target, module).source.status, 'unavailable');
});


test('lap charts preserve missing laps, ignore incomplete future laps and compare only adjacent completed laps', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const d = makeDemo(), e = d.preview.entries[0], driver = d.hass.states[e.entities.driver_positions].attributes.drivers[0];
  const m = normalizeConfig({ modules: [{ type: 'lap_chart', options: { selected: ['16'], metric: 'lap_time' } }] }).modules[0];
  driver.laps = { 9: 82, 10: 81.5, 12: 80.5, 13: 80, 900: 1 };
  let model = lapChartModel(d.hass, e, m);
  assert.deepEqual(model.rounds.map(item => item.id), [9, 10, 11, 12]);
  assert.deepEqual(model.series[0].values.map(item => item.value), [82, 81.5, null, 80.5]);
  m.options.metric = 'lap_change'; m.options.start_lap = 10;
  model = lapChartModel(d.hass, e, m);
  assert.deepEqual(model.series[0].values.map(item => item.value), [-.5, null, null]);
  assert.equal(model.context.source, 'TimingData');
  m.options.start_lap = 15; m.options.end_lap = 12;
  assert.equal(lapChartModel(d.hass, e, m).invalidRange, true);
});

test('lap chart selections and unavailable sources cannot silently substitute another driver or stale roster', async () => {
  const { makeDemo } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js');
  const d = makeDemo(), e = d.preview.entries[0];
  const m = normalizeConfig({ modules: [{ type: 'lap_chart', driver: '16', options: { selected: ['4'] } }] }).modules[0];
  assert.equal(lapChartModel(d.hass, e, m).series.length, 0);
  m.options.selected = [];
  assert.equal(lapChartModel(d.hass, e, m, { driver: '4' }).series[0].id, '16');
  d.hass.states[e.entities.driver_list].attributes.drivers[0].full_name = 'Stale name';
  d.hass.states[e.entities.driver_list].state = 'unavailable';
  assert.equal(lapChartModel(d.hass, e, m).series[0].name, 'Charles Leclerc');
  d.hass.connection = { connected: false };
  assert.equal(lapChartModel(d.hass, e, m).source.status, 'unavailable');
});

test('calendar filters elapsed starts and identifies the next selected session before display decoration', () => {
  const calendarEntry = { entities: { current_season: 'sensor.season' } };
  const hass = { states: { 'sensor.season': state({ races: [
    { round: '1', raceName: 'Past', date: '2026-09-12', time: '12:00:00Z', Circuit: { circuitName: 'First circuit', Location: { locality: 'Town', country: 'Country' } } },
    { round: '2', raceName: 'Next', date: '2026-09-14', time: '12:00:00Z' },
    { round: '3', raceName: 'Later', date: '2026-09-20', time: '12:00:00Z' },
  ] }) } };
  const module = normalizeConfig({ modules: [{ type: 'calendar', options: { range: 'season', sessions: ['race'], past: 'hide' } }] }).modules[0];
  const now = Date.parse('2026-09-14T12:00:00Z');
  assert.deepEqual(scheduleRows(hass, calendarEntry, module, now).rows.map(row => [row.meeting, row.next]), [['Next', true], ['Later', false]]);
  module.options.past = 'dim';
  const rows = scheduleRows(hass, calendarEntry, module, now).rows;
  assert.equal(rows[0].past, true);
  assert.equal(rows[0].circuit, 'First circuit');
  assert.equal(rows[0].location, 'Town, Country');
  assert.equal(rows[1].past, false);
  assert.equal(scheduleRows(hass, calendarEntry, module, now + 1).rows[2].next, true);
});

test('calendar retains date-only sessions without inventing midnight and handles uncertain order conservatively', () => {
  const entry = { entities: { current_season: 'sensor.season' } };
  const hass = { states: { 'sensor.season': state({ races: [
    { round: '1', raceName: 'Past date', date: '2026-09-01' },
    { round: '2', raceName: 'Time pending', date: '2026-09-14' },
    { round: '3', raceName: 'Known time', date: '2026-09-14', time: '15:00:00Z' },
    { round: '4', raceName: 'Invalid date', date: '2026-02-30' },
    { round: '5', raceName: 'Next date', date: '2026-09-15', circuit_timezone: 'UTC' },
  ] }) } };
  const module = normalizeConfig({ modules: [{ type: 'calendar', options: { range: 'season', sessions: ['race'], past: 'hide' } }] }).modules[0];
  const rows = scheduleRows(hass, entry, module, Date.parse('2026-09-14T12:00:00Z')).rows;
  assert.deepEqual(rows.map(row => row.meeting), ['Time pending', 'Known time', 'Next date']);
  assert.equal(rows[0].start, null); assert.equal(rows[0].date, '2026-09-14');
  assert.equal(rows.some(row => row.next), false);
  hass.states['sensor.season'].attributes.races[1].time = '13:00:00Z';
  assert.equal(scheduleRows(hass, entry, module, Date.parse('2026-09-14T12:00:00Z')).rows[0].next, true);
});

test('date-only filtering uses the circuit date or waits until the date is past in every timezone', () => {
  const entry = { entities: { next_race: 'sensor.weekend' } };
  const module = normalizeConfig({ modules: [{ type: 'calendar', options: { sessions: ['race'], past: 'hide' } }] }).modules[0];
  const attributes = { date: '2026-09-14', circuit_timezone: 'America/Los_Angeles' };
  const hass = { states: { 'sensor.weekend': state(attributes) } };
  assert.equal(scheduleRows(hass, entry, module, Date.parse('2026-09-15T06:00:00Z')).rows.length, 1);
  assert.equal(scheduleRows(hass, entry, module, Date.parse('2026-09-15T07:00:00Z')).rows.length, 0);
  attributes.circuit_timezone = 'invalid';
  assert.equal(scheduleRows(hass, entry, module, Date.parse('2026-09-15T11:59:00Z')).rows.length, 1);
  assert.equal(scheduleRows(hass, entry, module, Date.parse('2026-09-15T12:00:00Z')).rows.length, 0);
  attributes.date = '2026-09-16'; attributes.race_start_utc = '2026-09-16';
  for (const candidate of ['2026-09-16', '2026-09-16T12:00:00', 17, { slice: 17 }]) {
    attributes.race_start_utc = candidate;
    const row = scheduleRows(hass, entry, module, Date.parse('2026-09-15T12:00:00Z')).rows[0];
    assert.equal(row.start, null);
    assert.equal(row.date, '2026-09-16');
  }
});

test('automatic weather selects one current source, keeps missing fields missing and ignores unknown session status', () => {
  const entry = { entities: { weather: 'sensor.weather', track_weather: 'sensor.track', session_status: 'sensor.status' } };
  const hass = { states: {
    'sensor.weather': state({ current_temperature: 12, current_humidity: 70, race_temperature: 24 }),
    'sensor.track': state({ air_temperature: 30, rainfall: 0 }),
    'sensor.status': state({}, 'live'),
  } };
  const module = { type: 'weather', fields: ['temperature', 'humidity', 'rainfall'], options: { content: 'automatic_conditions' } };
  const live = weatherValues(hass, entry, module);
  assert.equal(live.track, true); assert.equal(live.values.temperature.value, 30);
  assert.equal(live.values.humidity.value, null); assert.equal(live.values.rainfall.value, false);
  hass.connection = { connected: false };
  const disconnected = weatherValues(hass, entry, module);
  assert.equal(disconnected.track, true, 'disconnect must not silently choose forecast');
  assert.equal(disconnected.source.status, 'unavailable', 'offline measurements must not appear live');
  assert.equal(disconnected.values.humidity.value, null);
  hass.connection.connected = true;
  for (const phase of ['pre', 'live', 'suspended', 'break']) {
    hass.states['sensor.status'].state = phase;
    assert.equal(weatherValues(hass, entry, module).track, true);
  }
  for (const phase of ['idle', 'unknown', 'unavailable']) {
    hass.states['sensor.status'].state = phase;
    const current = weatherValues(hass, entry, module);
    assert.equal(current.track, false); assert.equal(current.values.temperature.value, 12);
    assert.equal(current.values.rainfall.value, null);
  }
  delete hass.states['sensor.status'];
  assert.equal(weatherValues(hass, entry, module).track, false);
  hass.states['sensor.status'] = state({}, 'live'); hass.states['sensor.track'] = state({ air_temperature: null });
  assert.equal(weatherValues(hass, entry, module).track, false);
  assert.equal(weatherValues(hass, entry, { ...module, options: { content: 'race_forecast' } }).values.temperature.value, 24);
});
