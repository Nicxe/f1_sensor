const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');

const workflow = name => yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows', name), 'utf8'));

function trustedEvaluator(job) {
  const pin = /^Nicxe\/f1_sensor\/\.github\/workflows\/security-health\.yml@([a-f0-9]{40})$/.exec(job.uses || '');
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
  assert.deepEqual(audit.on.workflow_call.inputs, {checkout_ref: {type: 'string', default: ''}});
  assert.deepEqual(audit.permissions, {contents: 'read'});
  assert.equal(audit.jobs.audit.with.target_ref, "${{ inputs.checkout_ref || (github.event.inputs.pull_request && format('refs/pull/{0}/merge', github.event.inputs.pull_request)) || github.sha }}");
  assert.equal(trustedEvaluator(audit.jobs.audit), trustedEvaluator(workflow('security-health.yml').jobs['security-health']));
});
