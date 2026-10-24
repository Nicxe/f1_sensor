const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const semver = require('semver');

function checkSecurityPatches(lock) {
  assert.ok(lock && [2, 3].includes(lock.lockfileVersion) && lock.packages &&
    typeof lock.packages === 'object' && !Array.isArray(lock.packages) && lock.packages[''],
  'complete package-lock evidence is required');
  for (const [name, entry] of Object.entries(lock.packages)) {
    let range;
    if (/(?:^|\/)node_modules\/body-parser$/.test(name)) {
      range = '<1.20.9 || >=2.0.0 <2.4.0';
    } else if (/(?:^|\/)node_modules\/undici$/.test(name) && !entry?.inBundle) {
      range = '>=6.23.0 <6.29.1 || >=7.18.0 <7.30.1 || >=8.0.0 <8.12.2';
    } else continue;
    assert.ok(entry && semver.valid(entry.version), `${name}: invalid version`);
    assert.ok(!semver.satisfies(entry.version, range), `${name}: vulnerable ${entry.version}`);
  }
  // Bundled npm dependencies remain subject to the live audit and its exact,
  // expiring exceptions; a lockfile assertion cannot make them safe.
}

function fixture(packages) {
  return {lockfileVersion: 3, packages: {'': {}, ...packages}};
}

test('resolved ordinary dependencies do not reintroduce patched crash vulnerabilities', () => {
  checkSecurityPatches(JSON.parse(fs.readFileSync(path.join(__dirname, '../package-lock.json'), 'utf8')));
});

test('removing body-parser or undici entirely is a valid security repair', () => {
  assert.doesNotThrow(() => checkSecurityPatches(fixture({})));
  assert.doesNotThrow(() => checkSecurityPatches(fixture({'node_modules/@types/body-parser': {version: '1.19.0'}})));
});

test('independent vulnerable fixtures fail even when the live graph is fixed', () => {
  for (const [name, versions] of [
    ['body-parser', ['1.20.8', '2.3.9']],
    ['undici', ['6.29.0', '7.30.0', '8.12.1']],
  ]) {
    for (const version of versions) {
      for (const prefix of ['node_modules/', 'node_modules/consumer/node_modules/']) {
        assert.throws(() => checkSecurityPatches(fixture({[prefix + name]: {version}})), /vulnerable/);
      }
    }
  }
});

test('independent patched fixtures and unrelated safe branches pass', () => {
  for (const [name, versions] of [
    ['body-parser', ['1.20.9', '2.4.0']],
    ['undici', ['6.22.0', '6.29.1', '7.30.1', '8.12.2']],
  ]) {
    for (const version of versions) {
      assert.doesNotThrow(() => checkSecurityPatches(fixture({[`node_modules/${name}`]: {version}})));
    }
  }
});

test('missing or malformed dependency evidence is not a clean graph', () => {
  for (const lock of [null, {}, {lockfileVersion: 3}, fixture({'node_modules/undici': {}}),
    fixture({'node_modules/body-parser': {version: 'not-semver'}})]) {
    assert.throws(() => checkSecurityPatches(lock));
  }
});
