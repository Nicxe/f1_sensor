import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { replayModel, replayCommand } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';
const fixture = (scene = 'replay') => { const demo = makeDemo(scene); return { ...demo, entry: demo.preview.entries[0], module: normalizeConfig({ modules: [{ type: 'replay' }] }).modules[0] }; };
const read = d => replayModel(d.hass, d.entry);
const command = (d, action, value, context = read(d).controlContext) => replayCommand(d.hass, d.entry, d.module, action, value, context);

test('replay uses media-relative progress and requires matching loaded session and state before playback', () => {
  const d = fixture(), player = d.hass.states[d.entry.entities.replay_player];
  d.hass.states[d.entry.entities.replay_status].attributes.playback_position_s = 100;
  player.attributes.session_start_offset_s = 600;
  assert.equal(read(d).position, 1800); assert.equal(read(d).duration, 7200);
  assert.equal(read(d).allowed.play, true); assert.equal(read(d).allowed.pause, false); assert.equal(read(d).allowed.year, false);
  player.attributes.selected_session = 'Another session';
  assert.equal(read(d).loaded, false); assert.equal(read(d).allowed.seek, false); assert.equal(read(d).position, null);
  player.attributes.selected_session = d.hass.states[d.entry.entities.replay_status].attributes.selected_session;
  player.attributes.replay_state = 'playing';
  assert.equal(read(d).allowed.play, false);
});

test('replay commands only address discovered entities and reject hidden controls or stale session contexts', () => {
  const d = fixture(), oldId = d.entry.entities.replay_player, renamed = 'media_player.renamed_replay';
  d.hass.states[renamed] = d.hass.states[oldId]; d.entry.entities.replay_player = renamed; delete d.hass.states[oldId];
  assert.deepEqual(command(d, 'play'), { domain: 'media_player', service: 'media_play', data: { entity_id: renamed } });
  const oldContext = read(d).controlContext;
  d.hass.states[renamed].attributes.selected_session_id = 'new-session';
  assert.equal(command(d, 'play', null, oldContext), null);
  d.module.fields = ['replay_progress'];
  assert.equal(command(d, 'play'), null); assert.equal(command(d, 'seek', 60), null);
  d.module.enabled = false;
  assert.equal(command(d, 'stop'), null);
});

test('replay seek keeps zero valid, rejects invalid or out-of-range targets and avoids offset double counting', () => {
  const d = fixture();
  assert.equal(command(d, 'seek', 0).data.seek_position, 0);
  assert.equal(command(d, 'seek', 1770.9).data.seek_position, 1770);
  for (const value of [null, '', false, NaN, Infinity, -1, 7201]) assert.equal(command(d, 'seek', value), null);
  const context = read(d).controlContext;
  d.hass.states[d.entry.entities.replay_player].attributes.media_position = 1801;
  assert.ok(command(d, 'seek', 30, context));
  d.hass.connection = { connected: false };
  assert.equal(command(d, 'seek', 30), null);
  d.entry.disabled_entities = ['replay_player'];
  assert.equal(read(d).playerStatus, 'disabled');
});

test('a never-pressed load button is usable, and session selectors require real available sessions', () => {
  const d = fixture('race'), state = d.hass.states[d.entry.entities.replay_status];
  assert.equal(command(d, 'refresh').service, 'press');
  assert.deepEqual(command(d, 'year', '2025').data, { entity_id: d.entry.entities.replay_year_select, option: '2025' });
  assert.equal(command(d, 'year', '1999'), null);
  state.state = 'selected'; state.attributes.selected_session = 'Demo Grand Prix · Race';
  assert.equal(command(d, 'load').data.entity_id, d.entry.entities.replay_load);
  d.entry.disabled_entities = ['replay_load'];
  assert.equal(command(d, 'load'), null);
  state.attributes.sessions_available = 0;
  assert.equal(command(d, 'session', 'Demo Grand Prix · Race'), null);
});
