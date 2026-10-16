import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';
import { makeDemo } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/demo.js';
import { teamRadioCommand, teamRadioModel } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/team-radio-data.js';

const fixture = () => {
  const demo = makeDemo('race');
  return { ...demo, entry: demo.preview.entries[0] };
};
const module = (options = {}, extra = {}) => normalizeConfig({ modules: [{ type: 'team_radio', options, ...extra }] }).modules[0];

test('Team Radio normalizes the latest clip and keeps stable clip identity across transcription updates', () => {
  const demo = fixture();
  const first = teamRadioModel(demo.hass, demo.entry, module());
  assert.equal(first.source.status, 'available');
  assert.equal(first.clips.length, 1);
  assert.equal(first.clips[0].driverTla, 'LEC');
  assert.deepEqual(first.clips[0].transcriptionSegments.map(row => row.speaker), ['A', 'B', 'A']);
  assert.match(first.clips[0].clipUrl, /^\/api\/f1_sensor\/team-radio\//);

  const id = first.clips[0].id;
  demo.hass.states[demo.entry.entities.team_radio].attributes.transcription_text = 'Corrected transcript';
  assert.equal(teamRadioModel(demo.hass, demo.entry, module()).clips[0].id, id);
});

test('Team Radio history follows driver and team focus without falling back to another message', () => {
  const demo = fixture();
  const recent = module({ presentation: 'recent_messages', messages_to_show: 10 });
  assert.deepEqual(teamRadioModel(demo.hass, demo.entry, recent).clips.map(clip => clip.racingNumber), ['16', '4']);
  assert.deepEqual(teamRadioModel(demo.hass, demo.entry, recent, { driver: '4' }).clips.map(clip => clip.driverTla), ['NOR']);
  assert.deepEqual(teamRadioModel(demo.hass, demo.entry, recent, { team: 'McLaren' }).clips.map(clip => clip.racingNumber), ['4']);
  assert.equal(teamRadioModel(demo.hass, demo.entry, recent, { driver: '63' }).clips.length, 0);

  const pinned = module({ presentation: 'recent_messages' }, { driver: '16' });
  assert.deepEqual(teamRadioModel(demo.hass, demo.entry, pinned, { driver: '4' }).clips.map(clip => clip.racingNumber), ['16']);
});

test('Team Radio resolves missing driver identity from the driver list without overriding clip data', () => {
  const demo = fixture();
  const radio = demo.hass.states[demo.entry.entities.team_radio];
  const roster = demo.hass.states[demo.entry.entities.driver_list];
  const clip = {
    utc: '2026-02-20T14:40:24Z', racing_number: '27', path: 'TeamRadio/27_message.mp3',
    driver_name: 'Nico Hülkenberg',
  };
  radio.attributes = { ...clip, history: [clip] };
  roster.attributes.drivers = [{
    racing_number: '27', tla: 'HUL', full_name: 'Roster name', team: 'Audi', team_color: '#f50537',
  }];

  const [resolved] = teamRadioModel(demo.hass, demo.entry, module()).clips;
  assert.equal(resolved.driverTla, 'HUL');
  assert.equal(resolved.driverName, 'Nico Hülkenberg');
  assert.equal(resolved.teamName, 'Audi');
  assert.equal(resolved.teamColor, '#f50537');
  assert.deepEqual(teamRadioModel(demo.hass, demo.entry, module(), { team: 'Audi' }).clips.map(item => item.racingNumber), ['27']);
});

test('Team Radio transcription targets only the configured AI Task entity and latest clip', () => {
  const demo = fixture();
  const aiTaskEntityId = 'ai_task.google_ai_task';
  demo.hass.states[aiTaskEntityId] = { state: 'idle', attributes: {} };
  const configured = module({ presentation: 'recent_messages', messages_to_show: 10, ai_task_entity_id: aiTaskEntityId });
  const result = teamRadioModel(demo.hass, demo.entry, configured);

  assert.equal(result.transcription.ready, true);
  assert.equal(result.clips[0].isLatest, true);
  assert.equal(result.clips[1].isLatest, false);
  assert.deepEqual(teamRadioCommand(demo.hass, demo.entry, configured, result.clips[0].id), {
    domain: 'f1_sensor',
    service: 'transcribe_team_radio',
    data: {
      entity_id: demo.entry.entities.team_radio,
      ai_task_entity_id: aiTaskEntityId,
      force: false,
    },
    returnResponse: true,
  });
  assert.equal(teamRadioCommand(demo.hass, demo.entry, configured, result.clips[1].id), null);

  demo.hass.states[aiTaskEntityId].state = 'unavailable';
  assert.equal(teamRadioCommand(demo.hass, demo.entry, configured, result.clips[0].id), null);
  assert.equal(teamRadioCommand(demo.hass, demo.entry, module({ ai_task_entity_id: 'sensor.not_ai' }), result.clips[0].id), null);
});

test('Team Radio rejects external audio URLs, unsafe colors and unsupported speaker identities', () => {
  const demo = fixture();
  const attributes = demo.hass.states[demo.entry.entities.team_radio].attributes;
  Object.assign(attributes, {
    clip_url: 'https://example.com/private.mp3',
    team_color: '#fff;position:fixed',
    transcription_segments: [
      { speaker: 'driver', text: '  Copy.  ' },
      { speaker: 'B', text: '' },
      null,
    ],
  });
  const [clip] = teamRadioModel(demo.hass, demo.entry, module()).clips;
  assert.equal(clip.clipUrl, null);
  assert.equal(clip.teamColor, '#e80020');
  assert.deepEqual(clip.transcriptionSegments, [{ speaker: 'unknown', text: 'Copy.' }]);
});

test('Team Radio reports disabled and malformed sources without inventing clips', () => {
  const demo = fixture();
  demo.entry.disabled_entities.push('team_radio');
  demo.hass.states[demo.entry.entities.team_radio].attributes = { history: [null, false, {}] };
  const result = teamRadioModel(demo.hass, demo.entry, module());
  assert.equal(result.source.status, 'disabled');
  assert.deepEqual(result.clips, []);
});
