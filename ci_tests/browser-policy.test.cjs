const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const readConfig = (name, extra = {}) => {
  const env = { ...process.env, CI: 'true', ...extra };
  for (const key of ['F1_MAINTENANCE', 'F1_VISUAL_REVIEW']) if (!(key in extra)) delete env[key];
  const result = spawnSync(process.execPath, ['-e', `
    const config = require(${JSON.stringify(path.join(root, name))});
    console.log(JSON.stringify({retries: config.retries, trace: config.use.trace,
      excluded: ['keyboard works', 'measure timing @performance', 'pixels @visual'].map(title => config.grepInvert?.test(title) || false)}));
  `], { env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
};

test('blocking browser suites expose first-attempt failures and keep their traces', () => {
  for (const file of ['playwright.config.js', 'playwright.docs.config.js']) {
    const config = readConfig(file);
    assert.equal(config.retries, 0, file);
    assert.equal(config.trace, 'retain-on-failure', file);
  }
});

test('pixel reviews and benchmarks are opt-in without excluding functional tests', () => {
  assert.deepEqual(readConfig('playwright.config.js').excluded, [false, true, true]);
  assert.deepEqual(readConfig('playwright.config.js', { F1_MAINTENANCE: '1' }).excluded, [false, false, true]);
  assert.deepEqual(readConfig('playwright.config.js', { F1_VISUAL_REVIEW: '1' }).excluded, [false, true, false]);
  assert.deepEqual(readConfig('playwright.config.js', { F1_MAINTENANCE: '1', F1_VISUAL_REVIEW: '1' }).excluded, [false, false, false]);
});

test('card compatibility requires shipped cards but permits additional cards', () => {
  const { SUPPORTED_CARD_TYPES } = require('../frontend-tests/supported-cards.cjs');
  const missing = types => SUPPORTED_CARD_TYPES.filter(type => !types.includes(type));
  assert.deepEqual(missing([...SUPPORTED_CARD_TYPES, 'f1-future-card']), []);
  assert.deepEqual(missing(SUPPORTED_CARD_TYPES.filter(type => type !== 'f1-next-race-card')), ['f1-next-race-card']);
  assert.equal(new Set(SUPPORTED_CARD_TYPES).size, SUPPORTED_CARD_TYPES.length);
});

test('managed resource checks reject missing modules and stale nested module or tyre URLs', () => {
  const { assertManagedResources, REQUIRED_VERSIONED_ASSETS } = require('../frontend-tests/managed-resources.cjs');
  const base = '/cards/', version = 'new version+1';
  const requests = REQUIRED_VERSIONED_ASSETS.map(file => new URL(`http://localhost${base}${file}?v=${encodeURIComponent(version)}`));
  assert.doesNotThrow(() => assertManagedResources(requests, base, version));
  assert.throws(() => assertManagedResources(requests.slice(1), base, version), /never requested: register.js/);
  for (const file of ['platform/accessibility.js', 'hard_tyre.png']) {
    const stale = requests.map(url => new URL(url));
    stale.find(url => url.pathname === `${base}${file}`).search = '';
    assert.throws(() => assertManagedResources(stale, base, version), /Stale child resource/);
  }
});
