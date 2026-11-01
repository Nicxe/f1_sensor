const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const yaml = require('js-yaml');

const executor = yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows/security-snapshot.yml'), 'utf8'));
const scan = executor.jobs.audit.steps.find(step => step.run?.includes('scripts/run_npm_audit.py'));

test('security executor covers permanent code branches with read-only permissions', () => {
  assert.deepEqual(Object.keys(executor.on), ['workflow_call']);
  assert.equal(executor.permissions.contents, 'read');
  for (const input of ['tools_ref', 'target_ref']) {
    assert.equal(executor.on.workflow_call.inputs[input].type, 'string');
    assert.equal(executor.on.workflow_call.inputs[input].default, '');
  }
  assert.equal(executor.on.workflow_call.inputs.mode.type, 'string');
  assert.equal(executor.on.workflow_call.inputs.mode.default, 'gate');
  assert.equal(executor.on.workflow_call.inputs.base.type, 'string');
  assert.equal(executor.on.workflow_call.inputs.base.default, '');
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
  assert.match(scan.run, /--target-ref\b/);
  assert.equal(scan.env.AUDIT_REF, "${{ inputs.target_ref || format('refs/heads/{0}', matrix.branch) }}");
  assert.equal(scan.env.AUDIT_TARGET_REF, '${{ inputs.target_ref }}');
  assert.equal(scan.env.AUDIT_MODE, '${{ inputs.mode }}');
  assert.equal(scan.env.AUDIT_BASE, '${{ inputs.base }}');
  assert.match(scan.run, /git fetch --no-tags -- origin "\$AUDIT_REF"/);
  assert.match(scan.run, /git rev-parse --verify 'FETCH_HEAD\^\{commit\}'/);
  assert.equal(steps.some(step => /npm (?:ci|install)\b/.test(step.run || '')), false);
});

function runSnapshot(ref, extraEnvironment = {}) {
  // Exercise the real workflow shell without network access or target code.
  // Successful fake fetch/rev-parse are the only permitted Git operations.
  return spawnSync('bash', ['-e', '-c', `
    git() {
      if [[ "$#" == 5 && "$1 $2 $3 $4" == 'fetch --no-tags -- origin' ]]; then
        if [[ "$AUDIT_FETCH_FAIL" == 1 ]]; then return 1; fi
        if [[ "$AUDIT_BASE_FETCH_FAIL" == 1 && "$5" == "$AUDIT_BASE" ]]; then return 1; fi
        fetched_ref="$5"
        printf 'FETCH %s\\n' "$5"
      elif [[ "$#" == 3 && "$1 $2 $3" == 'rev-parse --verify FETCH_HEAD^{commit}' ]]; then
        if [[ "$fetched_ref" == "$AUDIT_BASE" ]]; then
          printf '%s\\n' "\${AUDIT_BASE_RESOLVED_REF:-$AUDIT_BASE}"
        else
          printf '%s\\n' '${'b'.repeat(40)}'
        fi
      else return 90; fi
    }
    python3() {
      if [[ "$1" != 'scripts/run_npm_audit.py' ]]; then return 91; fi
      printf 'AUDIT'
      printf ' %s' "$@"
      printf '\\n'
    }
    ${scan.run}
  `], {env: {
    ...process.env,
    AUDIT_REF: ref,
    AUDIT_TARGET_REF: ref,
    AUDIT_MODE: executor.on.workflow_call.inputs.mode?.default,
    AUDIT_BASE: executor.on.workflow_call.inputs.base?.default,
    ...extraEnvironment,
  }, encoding: 'utf8'});
}

test('exact PR merge snapshots and legacy short permanent branches reach the immutable evaluator', () => {
  for (const ref of ['a'.repeat(40), 'refs/heads/dev', 'refs/heads/beta', 'refs/heads/main',
    'refs/pull/923/merge', 'dev', 'beta', 'main']) {
    const result = runSnapshot(ref);
    const normalized = ['dev', 'beta', 'main'].includes(ref) ? `refs/heads/${ref}` : ref;
    assert.equal(result.status, 0, `${ref}: ${result.stderr}`);
    assert.equal(result.stdout, `FETCH ${normalized}\nAUDIT scripts/run_npm_audit.py --mode gate --target-ref ${'b'.repeat(40)}\n`);
  }
});

test('introduced audit compares the exact target and immutable base without installing either', () => {
  const base = 'c'.repeat(40);
  const result = runSnapshot('refs/pull/923/merge', {AUDIT_MODE: 'introduced', AUDIT_BASE: base});
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout,
    `FETCH refs/pull/923/merge\nFETCH ${base}\nAUDIT scripts/run_npm_audit.py --mode introduced --target-ref ${'b'.repeat(40)} --base ${base}\n`);
});

test('daily checks retain the full health gate without an explicit snapshot or baseline', () => {
  const result = runSnapshot('refs/heads/dev', {AUDIT_TARGET_REF: ''});
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout,
    `FETCH refs/heads/dev\nAUDIT scripts/run_npm_audit.py --mode gate --target-ref ${'b'.repeat(40)}\n`);
});

test('invalid modes and introduced comparisons without immutable inputs fail before fetching', () => {
  for (const environment of [
    {AUDIT_MODE: ''}, {AUDIT_MODE: 'unknown'}, {AUDIT_MODE: 'gate; echo INJECTED'},
    {AUDIT_MODE: 'introduced', AUDIT_BASE: ''},
    {AUDIT_MODE: 'introduced', AUDIT_BASE: 'dev'},
    {AUDIT_MODE: 'introduced', AUDIT_BASE: '--upload-pack=malicious'},
    {AUDIT_MODE: 'introduced', AUDIT_BASE: `${'c'.repeat(40)}\n`},
    {AUDIT_MODE: 'introduced', AUDIT_BASE: 'c'.repeat(40), AUDIT_TARGET_REF: ''},
  ]) {
    const result = runSnapshot('refs/heads/dev', environment);
    assert.notEqual(result.status, 0, JSON.stringify(environment));
    assert.equal(result.stdout, '', JSON.stringify(environment));
  }
});

test('a failed baseline fetch never reuses the target as a clean comparison', () => {
  const result = runSnapshot('refs/pull/923/merge', {
    AUDIT_MODE: 'introduced', AUDIT_BASE: 'c'.repeat(40), AUDIT_BASE_FETCH_FAIL: '1',
  });
  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, 'FETCH refs/pull/923/merge\n');
});

test('a comparison that resolves to another commit cannot produce audit evidence', () => {
  const base = 'c'.repeat(40);
  const result = runSnapshot('refs/pull/923/merge', {
    AUDIT_MODE: 'introduced', AUDIT_BASE: base, AUDIT_BASE_RESOLVED_REF: 'd'.repeat(40),
  });
  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, `FETCH refs/pull/923/merge\nFETCH ${base}\n`);
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

const workflow = name => yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows', name), 'utf8'));

function trustedEvaluator(job) {
  const pin = /^Nicxe\/f1_sensor\/\.github\/workflows\/security-snapshot\.yml@([a-f0-9]{40})$/.exec(job.uses || '');
  assert.ok(pin, 'Use the reviewed evaluator workflow at an immutable commit.');
  assert.notEqual(pin[1], '0'.repeat(40), 'Replace the preparation placeholder before delivery.');
  assert.equal(job.with.tools_ref, pin[1], 'Execute only evaluator tools from that same reviewed commit.');
  assert.equal(job.steps, undefined);
  assert.equal(job.secrets, undefined);
  return pin[1];
}

test('daily security launcher delegates read-only health checks to the reviewed immutable evaluator', () => {
  const launcher = workflow('security-health.yml');
  assert.ok(launcher.on.schedule.length);
  assert.ok('workflow_dispatch' in launcher.on);
  assert.equal(launcher.on.push, undefined);
  assert.equal(launcher.on.pull_request, undefined);
  assert.deepEqual(launcher.permissions, {contents: 'read'});
  assert.equal(launcher.jobs['security-health'].with.target_ref, undefined);
  trustedEvaluator(launcher.jobs['security-health']);
});

test('main audit preserves its caller API and checks only the requested snapshot using identical trusted tools', () => {
  const audit = workflow('audit.yml');
  assert.deepEqual(audit.on.workflow_call.inputs, {checkout_ref: {type: 'string', default: ''}, mode: {type: 'string', default: 'gate'}, base: {type: 'string', default: ''}});
  assert.deepEqual(audit.permissions, {contents: 'read'});
  assert.equal(audit.jobs.audit.with.target_ref, "${{ inputs.checkout_ref || (github.event.inputs.pull_request && format('refs/pull/{0}/merge', github.event.inputs.pull_request)) || github.sha }}");
  assert.equal(audit.jobs.audit.with.mode, '${{ inputs.mode }}');
  assert.equal(audit.jobs.audit.with.base, '${{ inputs.base }}');
  assert.equal(trustedEvaluator(audit.jobs.audit), trustedEvaluator(workflow('security-health.yml').jobs['security-health']));
});
