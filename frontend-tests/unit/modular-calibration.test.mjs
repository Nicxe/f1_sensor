import assert from 'node:assert/strict';
import test from 'node:test';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { viewingModel, viewingCommand } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
import { callEntityService } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js';

const fixture = (scene = 'race') => { const demo = makeDemo(scene); demo.hass.connection = { connected: true }; return { ...demo, entry: demo.preview.entries[0] }; };
const read = (d, local) => viewingModel(d.hass, d.entry, local).calibration;
const command = (d, kind, value, context = read(d).context, local) => viewingCommand(d.hass, d.entry, `calibration_${kind}`, value, context, local);
const control = d => d.hass.states[d.entry.entities.delay_calibration_switch];
function running(d, extra = {}) {
  control(d).state = 'on'; Object.assign(control(d).attributes, { mode: 'running', reference: 'session_live', started_at: '2026-09-14T01:00:00Z', timeout_at: '2026-09-14T01:02:00Z', elapsed: 0, ...extra });
}

test('calibration offers only discovered references, waits for a coherent selection and uses renamed controls', () => {
  const d = fixture();
  assert.ok(command(d, 'start'));
  assert.equal(command(d, 'reference', 'unknown'), null);
  assert.equal(command(d, 'reference', 'Session live'), null);
  assert.equal(command(d, 'reference', 'Lap sync (race/sprint)').service, 'select_option');
  d.hass.states[d.entry.entities.live_delay_reference].state = 'Lap sync (race/sprint)';
  assert.equal(command(d, 'start'), null);
  control(d).attributes.reference = 'lap_sync';
  const old = d.entry.entities.delay_calibration_switch;
  d.entry.entities.delay_calibration_switch = 'switch.renamed_calibration'; d.hass.states[d.entry.entities.delay_calibration_switch] = d.hass.states[old]; delete d.hass.states[old];
  assert.deepEqual(command(d, 'start'), { domain: 'switch', service: 'turn_on', data: { entity_id: 'switch.renamed_calibration' } });
  d.hass.states[d.entry.entities.current_session].state = 'Qualifying';
  assert.equal(command(d, 'start'), null);
});

test('matching needs a running reference, permits a never-used button and ignores elapsed-only ticks', () => {
  const d = fixture(); assert.equal(command(d, 'match'), null);
  running(d); const context = read(d).context;
  assert.equal(read(d).elapsed, 0); assert.equal(command(d, 'match').service, 'press');
  control(d).attributes.elapsed = 21.4; control(d).last_updated = '2026-09-14T01:00:21Z';
  assert.ok(command(d, 'match', null, context));
  control(d).attributes.started_at = '2026-09-14T01:00:20Z';
  assert.equal(command(d, 'match', null, context), null);
  d.entry.disabled_entities = ['delay_calibration_match'];
  assert.equal(command(d, 'match'), null); assert.ok(command(d, 'cancel'));
});

test('lap sync identifies the completed lap and requires a valid recorded reference', () => {
  const d = fixture();
  d.hass.states[d.entry.entities.live_delay_reference].state = 'Lap sync (race/sprint)';
  running(d, { reference: 'lap_sync', recorded_lap: 0 });
  assert.equal(read(d).recordedLap, 0); assert.ok(command(d, 'match'));
  control(d).attributes.recorded_lap = 52;
  assert.equal(read(d).recordedLap, 52); const context = read(d).context;
  control(d).attributes.recorded_lap = 53;
  assert.equal(command(d, 'match', null, context), null);
  control(d).attributes.recorded_lap = null;
  assert.equal(read(d).recordedLap, null); assert.equal(command(d, 'match'), null);
});

test('selected replay and spoiler protection block calibration while cancellation remains possible', () => {
  const d = fixture();
  for (const state of ['selected', 'loading', 'ready', 'playing', 'paused', 'seeking', 'unknown', 'unavailable']) {
    d.hass.states[d.entry.entities.replay_status].state = state;
    assert.equal(command(d, 'start'), null); assert.equal(command(d, 'reference', 'Lap sync (race/sprint)'), null);
  }
  d.hass.states[d.entry.entities.replay_status].state = 'idle';
  running(d, { elapsed: 15 });
  for (const [global, local] of [['on', 'inherit'], ['unknown', 'inherit'], ['off', 'hide']]) {
    d.hass.states[d.entry.global_entities.no_spoiler_mode].state = global;
    const model = read(d, local);
    assert.equal(model.elapsed, null); assert.equal(model.recordedLap, null);
    assert.equal(command(d, 'match', null, model.context, local), null);
    assert.ok(command(d, 'cancel', null, model.context, local));
  }
  d.hass.connection.connected = false;
  assert.equal(command(d, 'cancel'), null);
});

test('structured outcomes do not infer success from an old result or raw backend message', () => {
  const d = fixture();
  d.hass.states[d.entry.entities.live_delay_number].attributes.calibration_last_result = { seconds: 32, completed_at: '2026-09-14T01:00:00Z', source: 'button' };
  control(d).attributes.last_result = { seconds: 32, completed_at: '2026-09-14T01:00:00Z', source: 'button' };
  control(d).attributes.idle_reason = 'timeout'; control(d).attributes.message = 'Live delay updated to 99 seconds.';
  assert.equal(read(d).outcome, 'timeout'); assert.equal(read(d).lastResult.seconds, 32);
  control(d).attributes.idle_reason = 'completed';
  control(d).attributes.last_result = { seconds: 17, completed_at: '2026-09-14T01:05:00Z', source: 'button' };
  assert.equal(read(d).lastResult.seconds, 17);
  assert.equal(read(d).lastResult.completedAt, '2026-09-14T01:05:00Z');
  running(d); assert.equal(read(d).outcome, null);
  control(d).state = 'off'; assert.equal(read(d).mode, 'unknown'); assert.equal(command(d, 'match'), null);
});

test('calibration and manual controls share an installation lock across distinct entities', async () => {
  const d = fixture(); let resolve;
  d.hass.callService = () => new Promise(yes => { resolve = yes; });
  const key = `live-delay:${d.entry.entry_id}`;
  const pending = callEntityService(d.hass, command(d, 'start'), key);
  const reference = command(d, 'reference', 'Lap sync (race/sprint)');
  assert.equal(await callEntityService({ ...d.hass }, reference, key), false);
  resolve(); assert.equal(await pending, true);
});
