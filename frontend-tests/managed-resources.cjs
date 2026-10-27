const assert = require('node:assert/strict');

const REQUIRED_VERSIONED_ASSETS = Object.freeze([
  'register.js', 'f1-sensor-live-data-card.js', 'f1-lit-3.3.2.js',
  'platform/base-card.js', 'platform/actions.js', 'platform/accessibility.js',
  'platform/i18n.js', 'platform/card-registry.js', 'modular/catalog.js',
  'modular/card.js', 'modular/editor.js',
  ...['hard', 'soft', 'medium', 'intermediate', 'wet'].map(name => `${name}_tyre.png`),
]);

const assertManagedResources = (requests, base, version) => {
  const paths = new Set(requests.map(url => url.pathname.slice(base.length)));
  for (const file of REQUIRED_VERSIONED_ASSETS) assert(paths.has(file), `Managed resource was never requested: ${file}`);
  for (const url of requests) assert.equal(url.searchParams.get('v'), version, `Stale child resource: ${url.pathname}`);
};

module.exports = { assertManagedResources, REQUIRED_VERSIONED_ASSETS };
