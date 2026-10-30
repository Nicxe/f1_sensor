const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const yaml = require('js-yaml');
const root = path.join(__dirname, '..');

function missingApprovals(declared, trusted) {
  return declared.entries.flatMap(entry => entry.advisory_ids.flatMap(id =>
    entry.allowed_nodes.filter(node => !trusted.entries.some(approved =>
      approved.package === entry.package && approved.advisory_ids.includes(id)
      && approved.allowed_nodes.includes(node) && approved.expires === entry.expires))
      .map(node => `${entry.package}:${id}:${node}:${entry.expires}`)));
}

test('every declared exception is available in both immutable trusted evaluators', () => {
  const declared = JSON.parse(fs.readFileSync(path.join(root, 'quality/npm-audit-allowlist.json')));
  for (const [filename, job] of [['audit.yml', 'audit'], ['security-health.yml', 'security-health']]) {
    const workflow = yaml.load(fs.readFileSync(path.join(root, '.github/workflows', filename), 'utf8'));
    const evaluator = workflow.jobs[job];
    const pin = evaluator.uses.match(/@([a-f0-9]{40})$/)?.[1];
    assert.ok(pin, 'The evaluator must be pinned to a reviewed immutable commit.');
    assert.equal(evaluator.with.tools_ref, pin);
    const trusted = JSON.parse(execFileSync('git', ['show', `${pin}:quality/npm-audit-allowlist.json`],
      {cwd: root, encoding: 'utf8'}));
    assert.deepEqual(missingApprovals(declared, trusted), [],
      `${filename} still uses a policy without the declared approvals; refresh its reviewed pin.`);
  }
});

test('a stale trusted policy cannot cover a newly declared advisory, path or expiry', () => {
  const approved = {package: 'example', advisory_ids: [42], allowed_nodes: ['node_modules/tool/node_modules/example'], expires: '2030-01-01'};
  const trusted = {entries: [approved]};
  for (const change of [{advisory_ids: [42, 43]}, {allowed_nodes: ['node_modules/example']}, {expires: '2030-02-01'}]) {
    assert.equal(missingApprovals({entries: [{...approved, ...change}]}, trusted).length, 1);
  }
  assert.deepEqual(missingApprovals({entries: [approved]}, trusted), []);
  // A repaired dependency may retire an exception without retaining old IDs.
  assert.deepEqual(missingApprovals({entries: []}, trusted), []);
});
