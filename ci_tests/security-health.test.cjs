const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');

const workflow = yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows/security-health.yml'), 'utf8'));

test('scheduled security health covers permanent code branches with read-only permissions', () => {
  assert.ok(workflow.on.schedule.length);
  assert.ok('workflow_dispatch' in workflow.on);
  assert.ok('workflow_call' in workflow.on);
  assert.equal(workflow.permissions.contents, 'read');
  assert.equal(workflow.on.workflow_call.inputs.target_ref.default, '');
  assert.equal(workflow.jobs.audit.strategy.matrix.branch,
    '${{ fromJSON(inputs.target_ref != \'\' && \'["snapshot"]\' || \'["dev","beta","main"]\') }}');
  assert.equal(workflow.jobs.audit.strategy['fail-fast'], false);
});

test('health checks use reviewed tools and read target dependency snapshots without installation', () => {
  const steps = workflow.jobs.audit.steps;
  const checkout = steps.find(step => step.uses?.startsWith('actions/checkout@'));
  assert.equal(checkout.with.ref, '${{ inputs.tools_ref || github.workflow_sha }}');
  assert.equal(checkout.with['persist-credentials'], false);
  assert.equal(checkout.with['fetch-depth'], 0);
  const scan = steps.find(step => step.run?.includes('scripts/run_npm_audit.py'));
  assert.match(scan.run, /--mode gate\b/);
  assert.match(scan.run, /--target-ref\b/);
  assert.equal(scan.env.AUDIT_REF, "${{ inputs.target_ref || format('refs/heads/{0}', matrix.branch) }}");
  assert.match(scan.run, /git fetch --no-tags -- origin "\$AUDIT_REF"/);
  assert.match(scan.run, /git rev-parse --verify 'FETCH_HEAD\^\{commit\}'/);
  assert.match(scan.run, /--target-ref "\$snapshot"/);
  assert.equal(steps.some(step => /npm (?:ci|install)\b/.test(step.run || '')), false);
});

test('exact PR merge snapshots are fetched without executing target code or accepting arbitrary refs', () => {
  const scan = workflow.jobs.audit.steps.find(step => step.run?.includes('scripts/run_npm_audit.py'));
  const guard = scan.run.split('\n')[0];
  const expression = guard.match(/=~ (.+) \]\]; then$/)[1];
  const allowed = new RegExp(expression);
  for (const ref of ['a'.repeat(40), 'refs/heads/dev', 'refs/heads/beta', 'refs/heads/main', 'refs/pull/923/merge']) {
    assert.ok(allowed.test(ref), ref);
  }
  for (const ref of ['dev', '--upload-pack=malicious', 'refs/heads/feature', 'refs/pull/1/head', '$(touch /tmp/bad)', 'main\nrefs/heads/dev']) {
    assert.equal(allowed.test(ref), false, ref);
  }
  assert.equal(/git (?:checkout|switch)|npm (?:ci|install)\b/.test(scan.run), false);
});

test('snapshot callers are isolated from daily monitor concurrency', () => {
  assert.equal(workflow.concurrency.group, "dependency-security-health-${{ inputs.target_ref || 'daily' }}");
  assert.equal(workflow.concurrency['cancel-in-progress'], false);
});
