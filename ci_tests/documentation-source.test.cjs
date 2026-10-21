const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');
const {eligibleReleaseRun, resolvePublicationSource, waitForPublicationSource} = require('../.github/scripts/documentation-source.cjs');

const head = 'a'.repeat(40);
const tree = 'b'.repeat(40);
const run = {
  id: 42, run_number: 1, status: 'completed', conclusion: 'success', event: 'push',
  path: '.github/workflows/release-pipeline.yml', head_sha: head, head_branch: 'beta',
  repository: {full_name: 'owner/repo'}, head_repository: {full_name: 'owner/repo'}
};

function environment(source = run) {
  const commits = [];
  return {
    runId: '42', context: {repo: {owner: 'owner', repo: 'repo'}, ref: 'refs/heads/main'}, core: {info() {}},
    commits,
    github: {rest: {
      actions: {async getWorkflowRun({run_id}) {assert.equal(run_id, 42); return {data: source};}},
      git: {async getCommit({commit_sha}) {commits.push(commit_sha); return {data: {tree: {sha: tree}}};}}
    }}
  };
}

test('successful same-repository release verification supplies the exact tested source and branch', async () => {
  for (const branch of ['beta', 'main']) {
    for (const event of ['push', 'workflow_dispatch']) {
      const env = environment({...run, head_branch: branch, event});
      assert.deepEqual(await resolvePublicationSource(env), {tested_sha: head, tested_tree: tree, target_branch: branch, source_run_id: 42});
      assert.deepEqual(env.commits, [head]);
    }
  }
});

test('fork, PR, unrelated workflow, wrong branch and unsuccessful runs never authorize publication', async () => {
  for (const changed of [
    {repository: {full_name: 'fork/repo'}}, {head_repository: {full_name: 'fork/repo'}},
    {head_repository: null}, {event: 'pull_request'}, {event: 'workflow_run'},
    {path: '.github/workflows/ci.yml'}, {head_branch: 'dev'}, {head_branch: 'content'},
    {status: 'in_progress'}, {conclusion: 'failure'}, {conclusion: 'cancelled'}, {head_sha: 'bad'}
  ]) {
    const source = {...run, ...changed};
    assert.equal(eligibleReleaseRun(source, 'owner/repo'), false);
    const env = environment(source);
    assert.equal(await resolvePublicationSource(env), null);
    assert.deepEqual(env.commits, []);
  }
});

test('re-fetched API state is authoritative and malformed source identity fails closed', async () => {
  const env = environment({...run, conclusion: 'failure'});
  env.context.payload = {workflow_run: run};
  assert.equal(await resolvePublicationSource(env), null);
  await assert.rejects(resolvePublicationSource({...environment(), runId: '../main'}), /Invalid source/);
  const invalid = environment();
  invalid.github.rest.git.getCommit = async () => ({data: {tree: {sha: 'bad'}}});
  await assert.rejects(resolvePublicationSource(invalid), /no valid Git tree/);
  const wrongIdentity = environment({...run, id: 43});
  await assert.rejects(resolvePublicationSource(wrongIdentity), /Invalid source.*identity/);
  assert.equal(await resolvePublicationSource({...environment(), expectedSha: 'c'.repeat(40)}), null);
  assert.equal(await resolvePublicationSource({...environment(), targetBranch: 'main'}), null);
});

test('delivery can only follow completed release verification and passes explicit immutable source inputs', () => {
  const source = yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows/documentation-publication.yml'), 'utf8'));
  assert.deepEqual(source.on, {push: {branches: ['beta', 'main']}, workflow_dispatch: null});
  assert.equal(source.jobs.source.steps[0].with.ref, '${{ github.workflow_sha }}');
  assert.equal(source.jobs.deploy.if, "needs.source.outputs.publish == 'true'");
  assert.equal(source.jobs.deploy.with.tested_sha, '${{ needs.source.outputs.tested_sha }}');
  assert.equal(source.jobs.deploy.with.tested_tree, '${{ needs.source.outputs.tested_tree }}');
  assert.equal(source.jobs.deploy.with.target_branch, '${{ needs.source.outputs.target_branch }}');
  assert.equal(source.permissions['contents'], 'read');
  assert.equal(source.jobs.source.permissions, undefined);
  assert.equal(source.jobs.deploy.permissions.actions, 'read');
});

function waitingEnvironment(snapshots = [[run]]) {
  const env = environment();
  let elapsed = 0, polls = 0;
  const waits = [], requested = [];
  env.context = {...env.context, ref: 'refs/heads/beta', sha: head, eventName: 'push'};
  env.now = () => elapsed;
  env.sleep = async milliseconds => {waits.push(milliseconds); elapsed += milliseconds;};
  env.timeoutMs = 90;
  env.pollMs = 30;
  env.github.rest.git.getRef = async ({ref}) => {
    assert.equal(ref, 'heads/beta');
    return {data: {object: {sha: head}}};
  };
  let current = [];
  env.github.rest.actions.listWorkflowRuns = async parameters => {
    requested.push(parameters);
    current = snapshots[Math.min(polls++, snapshots.length - 1)];
    return {data: {workflow_runs: current}};
  };
  env.github.rest.actions.getWorkflowRun = async ({run_id}) => ({data: current.find(item => item.id === run_id)});
  return {...env, waits, requested};
}

test('first beta push waits for discovery and queued verification without consulting a main publisher', async () => {
  const env = waitingEnvironment([[], [{...run, status: 'queued', conclusion: null}], [run]]);
  assert.deepEqual(await waitForPublicationSource(env), {
    tested_sha: head, tested_tree: tree, target_branch: 'beta', source_run_id: 42
  });
  assert.deepEqual(env.waits, [30, 30]);
  assert.equal(env.requested.length, 3);
  for (const request of env.requested) {
    assert.equal(request.workflow_id, 'release-pipeline.yml');
    assert.equal(request.head_sha, head);
    assert.equal(request.branch, 'beta');
  }
});

test('failed, cancelled and skipped exact-commit verification cannot authorize publication', async () => {
  for (const conclusion of ['failure', 'cancelled', 'skipped', 'timed_out', 'action_required']) {
    const env = waitingEnvironment([[{...run, conclusion}]]);
    assert.equal(await waitForPublicationSource(env), null);
    assert.deepEqual(env.commits, []);
    assert.deepEqual(env.waits, []);
  }
});

test('newest workflow execution wins over an older same-SHA success and is re-fetched while queued', async () => {
  const newer = {...run, id: 43, run_number: 2, status: 'in_progress', conclusion: null};
  const env = waitingEnvironment([[run, newer], [run, {...newer, status: 'completed', conclusion: 'success'}]]);
  assert.equal((await waitForPublicationSource(env)).source_run_id, 43);
  assert.deepEqual(env.waits, [30]);
});

test('wrong branch, SHA, repository, event or workflow never supplies matching release evidence', async () => {
  for (const changed of [{head_branch: 'main'}, {head_sha: 'c'.repeat(40)},
    {head_repository: {full_name: 'fork/repo'}}, {repository: {full_name: 'other/repo'}},
    {event: 'pull_request'}, {path: '.github/workflows/ci.yml'}]) {
    const env = waitingEnvironment([[{...run, ...changed}]]);
    await assert.rejects(waitForPublicationSource(env), /Timed out/);
    assert.deepEqual(env.commits, []);
    assert.equal(env.waits.reduce((sum, value) => sum + value, 0), env.timeoutMs);
  }
});

test('API failures, missing evidence, source mutation and malformed identities fail closed', async () => {
  const unavailable = waitingEnvironment();
  unavailable.github.rest.actions.listWorkflowRuns = async () => {throw new Error('API unavailable');};
  await assert.rejects(waitForPublicationSource(unavailable), /API unavailable/);
  await assert.rejects(waitForPublicationSource(waitingEnvironment([[]])), /Timed out/);
  const changed = waitingEnvironment();
  changed.github.rest.actions.getWorkflowRun = async () => ({data: {...run, head_sha: 'c'.repeat(40)}});
  await assert.rejects(waitForPublicationSource(changed), /source identity changed/);
  const badStatus = waitingEnvironment([[{...run, status: 'unknown'}]]);
  await assert.rejects(waitForPublicationSource(badStatus), /Invalid.*status/);
  const badSequence = waitingEnvironment([[{...run, run_number: undefined}]]);
  await assert.rejects(waitForPublicationSource(badSequence), /Invalid.*sequence/);
  const badId = waitingEnvironment([[{...run, id: '../main'}]]);
  await assert.rejects(waitForPublicationSource(badId), /Invalid.*identity/);
});

test('untrusted trigger contexts and superseded pushes cannot publish', async () => {
  for (const changed of [{eventName: 'pull_request'}, {ref: 'refs/heads/dev'}, {sha: 'not-a-sha'}]) {
    const env = waitingEnvironment();
    env.context = {...env.context, ...changed};
    await assert.rejects(waitForPublicationSource(env), /requires a trusted/);
  }
  const superseded = waitingEnvironment();
  superseded.github.rest.git.getRef = async () => ({data: {object: {sha: 'd'.repeat(40)}}});
  assert.equal(await waitForPublicationSource(superseded), null);
  assert.deepEqual(superseded.requested, []);
});

test('authoritative re-fetch revokes a success that was restarted before tree resolution', async () => {
  const env = waitingEnvironment();
  let fetches = 0;
  env.github.rest.actions.getWorkflowRun = async () => ({data: ++fetches === 1 ? run : {...run, status: 'queued', conclusion: null}});
  assert.equal(await waitForPublicationSource(env), null);
  assert.deepEqual(env.commits, []);
});
