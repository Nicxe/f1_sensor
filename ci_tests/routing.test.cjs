const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');

const workflow = name => yaml.load(fs.readFileSync(path.join(__dirname, '..', '.github/workflows', name), 'utf8'));

test('metadata-only PR edits do not restart or cancel product verification', () => {
  const events = workflow('ci.yml').on.pull_request.types;
  assert.deepEqual(events, ['opened', 'synchronize', 'reopened', 'ready_for_review']);
  const retarget = workflow('pr-target-check.yml').jobs.metadata.steps.find(step => step.name === 'Verify a changed target branch');
  assert.equal(retarget.if, "github.event.action == 'edited' && github.event.changes.base");
});

test('a green development run requires its own completed applicable checks', () => {
  const jobs = workflow('development.yml').jobs;
  assert.deepEqual(Object.keys(jobs), ['checks']);
  assert.equal(jobs.checks.uses, './.github/workflows/ci-checks.yml');
  assert.equal(jobs.checks.if, undefined);
  assert.equal(jobs.checks.needs, undefined);
});

test('every selected job and the final gate use the immutable planned commit', () => {
  const {jobs, on: {workflow_call: {outputs}}} = workflow('ci-checks.yml');
  assert.equal(outputs.tested_sha.value, '${{ jobs.plan.outputs.tested_sha }}');
  assert.equal(outputs.tested_tree.value, '${{ jobs.plan.outputs.tested_tree }}');
  for (const [name, job] of Object.entries(jobs)) {
    if (!job.uses) continue;
    assert.equal(job.with.checkout_ref, '${{ needs.plan.outputs.tested_sha }}', name);
    assert.ok(jobs.required.needs.includes(name), `${name} must reach the aggregate`);
  }
  const checkout = jobs.required.steps.find(step => step.uses?.startsWith('actions/checkout@'));
  assert.equal(checkout.with.ref, '${{ needs.plan.outputs.tested_sha }}');
  assert.equal(jobs.audit.with.mode, '${{ needs.plan.outputs.audit_mode }}');
  assert.equal(jobs.audit.with.base, '${{ needs.plan.outputs.audit_base }}');
});

test('documentation verification is independent of multi-channel publication', () => {
  const docs = workflow('documentation.yml');
  assert.equal(docs.on.workflow_call.inputs.publish, undefined);
  const checkouts = docs.jobs.documentation.steps.filter(step => step.uses?.startsWith('actions/checkout@'));
  assert.equal(checkouts.length, 1);
  assert.equal(checkouts[0].with.ref, '${{ inputs.checkout_ref || github.sha }}');
  assert.ok(docs.jobs.documentation.steps.some(step => step.run === 'python3 scripts/run_check.py documentation'));
  assert.ok(!docs.jobs.documentation.steps.some(step => step.uses?.startsWith('actions/upload-pages-artifact@')));
  const release = workflow('release-pipeline.yml');
  assert.deepEqual(release.jobs.release.needs, ['checks', 'security']);
  assert.equal(release.jobs.checks.with.separate_delivery, true);
  assert.equal(release.jobs.documentation.uses, './.github/workflows/documentation.yml');
  assert.equal(release.jobs.security.with.mode, 'gate');
  for (const name of ['documentation', 'security']) {
    assert.equal(release.jobs[name].with.checkout_ref, '${{ needs.checks.outputs.tested_sha }}');
  }
  assert.equal(release.jobs.deploy, undefined);
  const publication = workflow('documentation-publication.yml');
  assert.equal(publication.jobs.deploy.needs, 'source');
  assert.deepEqual(publication.jobs.deploy.with, {
    tested_sha: '${{ needs.source.outputs.tested_sha }}',
    tested_tree: '${{ needs.source.outputs.tested_tree }}',
    target_branch: '${{ needs.source.outputs.target_branch }}'
  });
});

test('Pages builds immutable channel refs and reports actual publication', () => {
  const {jobs, permissions, on: {workflow_call}} = workflow('deploy.yml');
  assert.equal(workflow_call.inputs.tested_sha.required, true);
  assert.equal(workflow_call.inputs.tested_tree.required, true);
  assert.equal(workflow_call.inputs.target_branch.required, true);
  const checkouts = jobs.build.steps.filter(step => step.uses?.startsWith('actions/checkout@') && step.with.path !== 'publication-tools');
  assert.deepEqual(checkouts.map(step => step.with.ref), [
    '${{ needs.refs.outputs.stable_sha }}', '${{ needs.refs.outputs.beta_sha }}'
  ]);
  assert.equal(jobs.deploy.steps.find(step => step.id === 'deployment').if, "steps.current.outputs.publish == 'true'");
  assert.equal(workflow_call.outputs.published.value, '${{ jobs.deploy.outputs.published }}');
  assert.deepEqual(permissions, {contents: 'read'});
  assert.deepEqual(jobs.refs.permissions, {contents: 'read', actions: 'read'});
  assert.deepEqual(jobs.build.permissions, {contents: 'read'});
  assert.deepEqual(jobs.deploy.permissions, {contents: 'read', actions: 'read', pages: 'write', 'id-token': 'write'});
});
