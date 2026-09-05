import test from 'node:test';
import assert from 'node:assert/strict';
import {readdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root = new URL('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/', import.meta.url);
const {f1Translate, f1FormatDateTime} = await import(new URL('platform/i18n.js', root));
const {normalizeF1Action, handleF1CardActionKeydown} = await import(new URL('platform/actions.js', root));
const {resolveF1CardEntities} = await import(new URL('platform/entity-resolver.js', root));

test('every delivered JavaScript module has valid syntax', () => {
  const files = readdirSync(root, {recursive:true}).filter(p => p.endsWith('.js'));
  assert.ok(files.length > 1);
  for (const file of files) execFileSync(process.execPath, ['--check', fileURLToPath(new URL(file, root))], {stdio:'pipe'});
});
test('localization preserves fallback and respects HA time settings', () => {
  assert.equal(f1Translate({language:'unknown'}, 'missing', 'Fallback'), 'Fallback');
  const hass = {locale:{language:'sv-SE'}, config:{time_zone:'Europe/Stockholm'}};
  assert.match(f1FormatDateTime(hass,new Date('2026-09-04T12:30:00Z'),{hour:'2-digit',minute:'2-digit'}), /14:30/);
});
test('legacy services normalize to native HA actions', () => {
  const action = normalizeF1Action({action:'call-service', service:'light.toggle', data:{entity_id:'light.example'}});
  assert.equal(action.action,'perform-action');
  assert.equal(action.perform_action,'light.toggle');
});
test('keyboard activation ignores unrelated keys and nested controls', () => {
  let calls = 0;
  const host = {_handleCardAction:()=>calls++};
  for (const key of ['Enter',' ','Escape']) handleF1CardActionKeydown(host,{key,target:host,currentTarget:host,preventDefault(){}});
  assert.equal(calls,2);
});
test('entity discovery uses actual registered IDs and reuses the connection request', async () => {
  let calls=0;
  const hass={connection:{},callWS:async()=>{calls++;return [{entry_id:'a',entities:{track_status:'sensor.renamed_track'}}]}};
  const bindings={track_status_entity:'track_status'};
  const result=await resolveF1CardEntities(hass,{f1_entry_id:'a'},bindings);
  assert.equal(result.track_status_entity,'sensor.renamed_track');
  await resolveF1CardEntities(hass,{f1_entry_id:'a'},bindings);
  assert.equal(calls,1);
});
