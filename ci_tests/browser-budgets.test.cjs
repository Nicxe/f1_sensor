const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
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
