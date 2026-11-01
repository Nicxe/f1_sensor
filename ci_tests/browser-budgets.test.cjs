const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const yaml = require('js-yaml');

// A successful dev run spent ten minutes provisioning Chromium alone. Browser
// setup must not consume the time previously reserved for each check lane.
const observedInstallMinutes = 10;
const setupAndCleanupMinutes = 5;

for (const [workflow, group, checkMinutes] of [
  ['translations.yml', 'translations', 8],
  ['frontend.yml', 'frontend', 12],
  ['documentation.yml', 'documentation', 15],
]) {
  test(`${group} reserves independent browser setup and verification budgets`, () => {
    const source = fs.readFileSync(path.join(__dirname, '../.github/workflows', workflow), 'utf8');
    const job = yaml.load(source).jobs[group];
    const install = job.steps.find(step => step.run === 'npx playwright install --with-deps chromium');
    const verify = job.steps.find(step => step.run === `python3 scripts/run_check.py ${group}`);

    assert.ok(install, 'the locked browser and its OS dependencies are installed');
    assert.ok(verify, 'the actual shared verification command is still required');
    assert.ok(job.steps.indexOf(install) < job.steps.indexOf(verify));
    for (const step of [install, verify]) {
      assert.ok(Number.isInteger(step['timeout-minutes']) && step['timeout-minutes'] > 0,
        'setup and verification each have an explicit bounded timeout');
      assert.equal(step['continue-on-error'], undefined, 'failures cannot be ignored');
      assert.equal(step.if, undefined, 'verification cannot be conditionally omitted');
    }
    assert.ok(install['timeout-minutes'] > observedInstallMinutes,
      'a known ten-minute browser install has provisioning headroom');
    assert.ok(verify['timeout-minutes'] >= checkMinutes,
      'the previous check budget is preserved independently of browser setup');
    assert.ok(Number.isInteger(job['timeout-minutes']));
    assert.ok(job['timeout-minutes'] >= install['timeout-minutes'] + verify['timeout-minutes'] + setupAndCleanupMinutes,
      'the job leaves room for both phases plus dependency setup and cleanup');
    assert.equal(install['working-directory'], verify['working-directory'],
      'the browser and check use dependencies from the same checkout');
  });
}

function weeklyBrowserSteps() {
  const source = fs.readFileSync(path.join(__dirname, '../.github/workflows/maintenance.yml'), 'utf8');
  const job = yaml.load(source).jobs.browser;
  return {
    job,
    install: job.steps.find(step => step.run === 'npx playwright install --with-deps chromium webkit'),
    performance: job.steps.find(step => step.env?.F1_MAINTENANCE === 'true'),
    webkit: job.steps.find(step => step.env?.F1_BROWSER === 'webkit'),
  };
}

function runsStep(condition, {installation, previousSuccess = true, cancelled = false}) {
  const expression = condition?.replace(/^\$\{\{\s*|\s*\}\}$/g, '') || 'success()';
  // GitHub adds success() unless the expression explicitly uses a status check.
  const overridesSuccess = /\b(?:always|cancelled|failure|success)\s*\(/.test(expression);
  if (!overridesSuccess && !previousSuccess) return false;
  return Boolean(vm.runInNewContext(expression, {
    steps: {[weeklyBrowserSteps().install.id]: {outcome: installation}},
    success: () => previousSuccess,
    failure: () => !previousSuccess && !cancelled,
    cancelled: () => cancelled,
    always: () => true,
  }));
}

test('weekly browser maintenance reserves installation and both verification budgets', () => {
  const {job, install, performance, webkit} = weeklyBrowserSteps();
  assert.ok(install, 'Chromium, WebKit and their system packages are installed together');
  assert.ok(typeof install.id === 'string' && install.id.length > 0,
    'later steps can check whether installation succeeded');
  assert.ok(performance, 'Chromium performance verification remains selected');
  assert.ok(webkit, 'WebKit functional verification remains selected');
  assert.ok(job.steps.indexOf(install) < job.steps.indexOf(performance));
  assert.ok(job.steps.indexOf(performance) < job.steps.indexOf(webkit));
  for (const step of [install, performance, webkit]) {
    assert.ok(Number.isInteger(step['timeout-minutes']) && step['timeout-minutes'] > 0,
      'each installation and verification phase has a bounded timeout');
    assert.equal(step['continue-on-error'], undefined, 'selected failures remain failures');
    assert.equal(step['working-directory'], install['working-directory'],
      'the browser and checks use the same installed dependency snapshot');
  }
  assert.ok(install['timeout-minutes'] > observedInstallMinutes,
    'installing two browsers has headroom beyond the observed Chromium-only setup');
  assert.ok(performance['timeout-minutes'] >= 12,
    'performance verification retains the previous complete browser-job budget');
  assert.ok(webkit['timeout-minutes'] >= 8, 'WebKit keeps a separate functional check budget');
  assert.equal(install.if, undefined, 'installation is required after dependency setup');
  assert.equal(runsStep(performance.if, {installation: 'success'}), true,
    'performance verification runs when dependency and browser setup succeeds');
  assert.ok(Number.isInteger(job['timeout-minutes']));
  assert.ok(job['timeout-minutes'] >= setupAndCleanupMinutes
    + install['timeout-minutes'] + performance['timeout-minutes'] + webkit['timeout-minutes'],
  'the job can finish installation, both checks and cleanup within their individual budgets');
});

test('weekly WebKit runs after successful installation even if Chromium performance fails', () => {
  const {webkit} = weeklyBrowserSteps();
  assert.equal(runsStep(webkit.if, {installation: 'success'}), true);
  assert.equal(runsStep(webkit.if, {installation: 'success', previousSuccess: false}), true);
});

test('weekly WebKit never runs with a missing browser or after cancellation', () => {
  const {webkit} = weeklyBrowserSteps();
  for (const installation of ['failure', 'cancelled', 'skipped', undefined]) {
    assert.equal(runsStep(webkit.if, {installation, previousSuccess: false}), false,
      `installation outcome ${installation} cannot authorize WebKit tests`);
  }
  assert.equal(runsStep(webkit.if, {
    installation: 'success', previousSuccess: false, cancelled: true,
  }), false, 'cancelling after installation must not start another browser test');
  const {performance} = weeklyBrowserSteps();
  assert.equal(runsStep(performance.if, {installation: 'failure', previousSuccess: false}), false,
    'dependency or browser-installation failure also prevents Chromium tests');
});
