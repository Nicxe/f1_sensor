const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const yaml = require('js-yaml');

const workflow = yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows/security-health.yml'), 'utf8'));
const executor = yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows/security-snapshot.yml'), 'utf8'));
const scan = executor.jobs.audit.steps.find(step => step.run?.includes('scripts/run_npm_audit.py'));

test('scheduled security health covers permanent code branches with read-only permissions', () => {
  assert.ok(workflow.on.schedule.length);
  assert.ok('workflow_dispatch' in workflow.on);
  assert.ok('workflow_call' in workflow.on);
  assert.equal(workflow.permissions.contents, 'read');
  assert.equal(workflow.on.workflow_call.inputs.target_ref.default, '');
  assert.equal(workflow.jobs.audit.uses, './.github/workflows/security-snapshot.yml');
  assert.deepEqual(workflow.jobs.audit.with, {
    tools_ref: '${{ inputs.tools_ref || github.workflow_sha }}',
    target_ref: "${{ inputs.target_ref || '' }}",
  });
  assert.equal(workflow.concurrency, undefined, 'only the executor owns concurrency; nested callers must not deadlock');
  assert.deepEqual(Object.keys(executor.on), ['workflow_call']);
  assert.equal(executor.permissions.contents, 'read');
  for (const input of ['tools_ref', 'target_ref']) {
    assert.equal(executor.on.workflow_call.inputs[input].type, 'string');
    assert.equal(executor.on.workflow_call.inputs[input].default, '');
  }
  assert.equal(executor.jobs.audit.strategy.matrix.branch,
    '${{ fromJSON(inputs.target_ref != \'\' && \'["snapshot"]\' || \'["dev","beta","main"]\') }}');
  assert.equal(executor.jobs.audit.strategy['fail-fast'], false);
});

test('health checks use reviewed tools and read target dependency snapshots without installation', () => {
  const steps = executor.jobs.audit.steps;
  const checkout = steps.find(step => step.uses?.startsWith('actions/checkout@'));
  assert.equal(checkout.with.ref, '${{ inputs.tools_ref || github.workflow_sha }}');
  assert.equal(checkout.with['persist-credentials'], false);
  assert.equal(checkout.with['fetch-depth'], 0);
  assert.match(scan.run, /--mode gate\b/);
  assert.match(scan.run, /--target-ref\b/);
  assert.equal(scan.env.AUDIT_REF, "${{ inputs.target_ref || format('refs/heads/{0}', matrix.branch) }}");
  assert.match(scan.run, /git fetch --no-tags -- origin "\$AUDIT_REF"/);
  assert.match(scan.run, /git rev-parse --verify 'FETCH_HEAD\^\{commit\}'/);
  assert.match(scan.run, /--target-ref "\$snapshot"/);
  assert.equal(steps.some(step => /npm (?:ci|install)\b/.test(step.run || '')), false);
});

function runSnapshot(ref, extraEnvironment = {}) {
  // Exercise the real workflow shell without network access or target code.
  // Successful fake fetch/rev-parse are the only permitted Git operations.
  return spawnSync('bash', ['-e', '-c', `
    git() {
      if [[ "$#" == 5 && "$1 $2 $3 $4" == 'fetch --no-tags -- origin' ]]; then
        if [[ "$AUDIT_FETCH_FAIL" == 1 ]]; then return 1; fi
        printf 'FETCH %s\\n' "$5"
      elif [[ "$#" == 3 && "$1 $2 $3" == 'rev-parse --verify FETCH_HEAD^{commit}' ]]; then
        printf '%s\\n' '${'b'.repeat(40)}'
      else return 90; fi
    }
    python3() {
      if [[ "$#" != 5 || "$1 $2 $3 $4" != 'scripts/run_npm_audit.py --mode gate --target-ref' ]]; then return 91; fi
      printf 'AUDIT %s\\n' "$5"
    }
    ${scan.run}
  `], {env: {...process.env, AUDIT_REF: ref, ...extraEnvironment}, encoding: 'utf8'});
}

test('exact PR merge snapshots and legacy short permanent branches reach the immutable evaluator', () => {
  for (const ref of ['a'.repeat(40), 'refs/heads/dev', 'refs/heads/beta', 'refs/heads/main',
    'refs/pull/923/merge', 'dev', 'beta', 'main']) {
    const result = runSnapshot(ref);
    const normalized = ['dev', 'beta', 'main'].includes(ref) ? `refs/heads/${ref}` : ref;
    assert.equal(result.status, 0, `${ref}: ${result.stderr}`);
    assert.equal(result.stdout, `FETCH ${normalized}\nAUDIT ${'b'.repeat(40)}\n`);
  }
});

test('arbitrary branches, option injection and shell content never fetch or execute', () => {
  for (const ref of ['feature', '--upload-pack=malicious', 'refs/heads/feature', 'refs/pull/1/head',
    '$(touch /tmp/bad)', 'main\nrefs/heads/dev', 'refs/heads/dev\n', 'dev; echo INJECTED', '']) {
    const result = runSnapshot(ref);
    assert.notEqual(result.status, 0, ref);
    assert.equal(result.stdout, '', ref);
  }
  assert.equal(/git (?:checkout|switch)|npm (?:ci|install)\b/.test(scan.run), false);
});

test('a failed fetch cannot audit a stale FETCH_HEAD or silently substitute a branch', () => {
  const result = runSnapshot('refs/pull/923/merge', {AUDIT_FETCH_FAIL: '1'});
  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, '');
});

test('snapshot callers are isolated from daily monitor concurrency', () => {
  assert.equal(executor.concurrency.group, "dependency-security-health-${{ inputs.target_ref || 'daily' }}");
  assert.equal(executor.concurrency['cancel-in-progress'], false);
});
