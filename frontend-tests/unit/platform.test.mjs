import test from 'node:test';
import assert from 'node:assert/strict';
import {readdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {catalogs, expectedMessage} from '../localization-fixture.cjs';
const root = new URL('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/', import.meta.url);
const {f1Translate, f1FormatDateTime, f1TranslateText, STRINGS, FRONTEND_TEXT_TRANSLATIONS} = await import(new URL('platform/i18n.js', root));
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
test('every projected locale exposes source keys after English fallback', () => {
  const frontendKeys = [...new Set(Object.entries(catalogs.en)
    .filter(([key]) => key.startsWith('legacy.platform.')).map(([, source]) => source))];
  for (const language of Object.keys(STRINGS).filter(lang => lang !== 'en')) {
    assert.deepEqual(Object.keys(STRINGS[language]).sort(), Object.keys(STRINGS.en).sort(), `STRINGS.${language}`);
    assert.deepEqual(Object.keys(FRONTEND_TEXT_TRANSLATIONS[language]).sort(), [...frontendKeys].sort(), `FRONTEND_TEXT_TRANSLATIONS.${language}`);
  }
});
test('the platform uses the current selected catalog rather than silently returning English', () => {
  for (const language of Object.keys(catalogs)) {
    for (const key of Object.keys(catalogs.en)) {
      assert.equal(f1Translate({locale: {language}}, key), expectedMessage(language, key), `${language}: ${key}`);
    }
  }
});
test('Dutch localization provides translated strings, frontend texts and counts', () => {
  const hass = {locale:{language:'nl'}};
  assert.match(f1Translate(hass, 'track_map.paused'), /\S/);
  for (const source of ['No session data', '12 cars', 'Idle / 3 cars', 'Measured precipitation 1.2 mm', 'No', 'Round 16', 'Show history', '1.1 m/s SE', '2.0 km/h W→']) {
    assert.match(f1TranslateText(hass, source), /\S/, source);
  }
  assert.match(f1TranslateText({locale:{language:'sv'}}, '3.4 m/s SW↗'), /\S/);
  assert.match(f1TranslateText({locale:{language:'sv'}}, '4 docs'), /\S/);
  const untranslated = '4 docs';
  assert.equal(f1TranslateText({locale:{language:'de'}}, untranslated), untranslated);
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
