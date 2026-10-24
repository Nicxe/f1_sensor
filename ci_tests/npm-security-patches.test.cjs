const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const semver = require('semver');

const lock = JSON.parse(fs.readFileSync(path.join(__dirname, '../package-lock.json'), 'utf8'));

test('resolved body parsers contain the compressed-request crash fix', () => {
  const parsers = Object.entries(lock.packages).filter(([name]) => /(?:^|\/)node_modules\/body-parser$/.test(name));
  assert.ok(parsers.length, 'the documentation server dependency must be checked');
  for (const [name, entry] of parsers) {
    assert.ok(semver.valid(entry.version), `${name}: invalid version`);
    assert.ok(!semver.satisfies(entry.version, '<1.20.9 || >=2.0.0 <2.4.0'), `${name}: ${entry.version}`);
  }
});

test('ordinary undici dependencies contain the excessive-content-encoding crash fix', () => {
  const clients = Object.entries(lock.packages).filter(([name, entry]) =>
    /(?:^|\/)node_modules\/undici$/.test(name) && !entry.inBundle);
  assert.ok(clients.length, 'the HTTP client dependencies must be checked');
  for (const [name, entry] of clients) {
    assert.ok(semver.valid(entry.version), `${name}: invalid version`);
    assert.ok(!semver.satisfies(entry.version, '>=6.23.0 <6.29.1 || >=7.18.0 <7.30.1 || >=8.0.0 <8.12.2'), `${name}: ${entry.version}`);
  }
  // Bundled npm dependencies remain subject to the live audit and its exact,
  // expiring exceptions; a lockfile assertion cannot make them safe.
});
