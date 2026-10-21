import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createContext, SourceTextModule, SyntheticModule} from 'node:vm';
import {catalogs, expectedMessage} from '../localization-fixture.cjs';

const root = new URL('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/localization/', import.meta.url);
const runtimeSource = readFileSync(new URL('index.js', root), 'utf8');
const {LEGACY} = await import(new URL('legacy.js', root));

const isolatedRuntime = async (messages, source = runtimeSource) => {
  const context = createContext({URL, Intl, __F1_SENSOR_LOCALES__: structuredClone(messages)});
  const legacy = new SyntheticModule(['LEGACY'], function () { this.setExport('LEGACY', LEGACY); }, {context});
  await legacy.link(() => { throw new Error('Unexpected legacy dependency'); });
  await legacy.evaluate();
  const runtime = new SourceTextModule(source, {
    context,
    initializeImportMeta: meta => { meta.url = new URL('index.js', root).href; },
    importModuleDynamically: () => legacy,
  });
  await runtime.link(() => { throw new Error('Unexpected static dependency'); });
  await runtime.evaluate();
  return runtime.namespace;
};

const sentinels = () => ({
  en: {'sample.title': 'Source {name}', 'sample.sparse': 'English fallback', 'sample.base': 'Base source', 'sample.count.one': '{count} item', 'sample.count.other': '{count} items'},
  sv: {'sample.title': 'A translator may reword this for {name}; {name}'},
  de: {'sample.title': 'A newly completed German entry for {name}'},
  pt: {'sample.base': 'Portuguese base fallback'},
  'pt-BR': {'sample.title': 'Regional wording for {name}'},
  es: {},
});

const assertLocaleContract = runtime => {
  assert.equal(runtime.translate('sv-SE', 'sample.title', {name: 'Driver'}), 'A translator may reword this for Driver; Driver');
  assert.equal(runtime.translate('de-DE', 'sample.title', {name: 'Driver'}), 'A newly completed German entry for Driver');
  assert.equal(runtime.translate('pt_BR', 'sample.title', {name: 'Driver'}), 'Regional wording for Driver');
  assert.equal(runtime.translate('pt-BR', 'sample.base'), 'Portuguese base fallback');
  assert.equal(runtime.translate('es', 'sample.sparse'), 'English fallback');
  assert.equal(runtime.translate('zz-ZZ', 'sample.sparse'), 'English fallback');
  assert.equal(runtime.translatePlural('sv', 'sample.count', 1), '1 item');
  assert.equal(runtime.translatePlural('sv', 'sample.count', 4), '4 items');
};

test('translator wording, sparse new languages, regional catalogs and German completion remain supported', async () => {
  const runtime = await isolatedRuntime(sentinels());
  assertLocaleContract(runtime);
  assert.equal(runtime.languageCode(' PT_br '), 'pt-br');
  assert.equal(runtime.translate('zz-ZZ', 'missing.key'), 'missing.key');
});

test('the contract detects a runtime that silently returns English for every language', async () => {
  const mutant = runtimeSource.replace('messageFor(language, key) ?? key', 'messageFor("en", key) ?? key');
  assert.notEqual(mutant, runtimeSource, 'The mutation must change the implementation under test');
  const runtime = await isolatedRuntime(sentinels(), mutant);
  assert.throws(() => assertLocaleContract(runtime), {code: 'ERR_ASSERTION'});
});

test('every current catalog is wired to the runtime with English fallback for missing keys', async () => {
  const {LOCALES, translate} = await import(new URL('index.js', root));
  assert.deepEqual(Object.keys(LOCALES).sort(), Object.keys(catalogs).sort());
  for (const language of Object.keys(catalogs)) {
    for (const key of Object.keys(catalogs.en)) {
      assert.equal(translate(language, key), expectedMessage(language, key), `${language}: ${key}`);
    }
  }
});

test('legacy dynamic counts still apply their declared patterns without freezing target wording', async () => {
  const {translateSourceText} = await import(new URL('index.js', root));
  const source = '3 of 4 columns';
  for (const [language, legacy] of Object.entries(LEGACY)) {
    const match = legacy.patterns.find(([pattern]) => new RegExp(pattern).test(source));
    const expected = match ? source.replace(new RegExp(match[0]), match[1]) : source;
    assert.equal(translateSourceText(language, source), expected, language);
  }
});
