const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');

const root = path.resolve(__dirname, '..');
const loadWorkflow = name => yaml.load(fs.readFileSync(path.join(root, '.github/workflows', name), 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const head = 'a'.repeat(40);
const tree = 'b'.repeat(40);

function environment({branch = 'beta', conclusion = 'success', eventName = 'push', pending = false, superseded = false} = {}) {
  const calls = [];
  const outputs = {};
  const summary = [];
  let clock = 0;
  let listing = 0;
  let source;
  const run = {
    id: 42,
    run_number: 17,
    status: 'completed',
    conclusion,
    event: eventName,
    path: '.github/workflows/release-pipeline.yml',
    head_sha: head,
    head_branch: branch,
    repository: {full_name: 'owner/repo'},
    head_repository: {full_name: 'owner/repo'}
  };
  const core = {
    info(message) { calls.push(['info', message]); },
    warning(message) { calls.push(['warning', message]); },
    setOutput(name, value) { outputs[name] = value; },
    summary: {
      addHeading(value) { summary.push(value); return this; },
      addRaw(value) { summary.push(value); return this; },
      addLink(label, url) { summary.push(url); return this; },
      async write() { calls.push(['summary']); }
    }
  };
  const github = {rest: {
    actions: {
      async listWorkflowRuns(parameters) {
        calls.push(['list', parameters]);
        assert.equal(parameters.workflow_id, 'release-pipeline.yml');
        assert.equal(parameters.branch, branch);
        assert.equal(parameters.head_sha, head);
        listing += 1;
        if (pending && listing === 1) return {data: {workflow_runs: []}};
        source = pending && listing === 2
          ? {...run, status: 'in_progress', conclusion: null}
          : run;
        return {data: {workflow_runs: [source]}};
      },
      async getWorkflowRun(parameters) {
        calls.push(['run', parameters]);
        assert.equal(parameters.run_id, 42);
        return {data: source};
      }
    },
    git: {
      async getRef(parameters) {
        calls.push(['ref', parameters]);
        assert.equal(parameters.ref, `heads/${branch}`);
        return {data: {object: {sha: superseded ? 'c'.repeat(40) : head}}};
      },
      async getCommit(parameters) {
        calls.push(['commit', parameters]);
        assert.equal(parameters.commit_sha, head);
        return {data: {tree: {sha: tree}}};
      }
    },
    repos: {
      async getContent() {
        assert.fail('The publisher must not require its workflow file to exist on main.');
      }
    }
  }};
  const context = {repo: {owner: 'owner', repo: 'repo'}, ref: `refs/heads/${branch}`, sha: head, eventName};
  const helper = require('../.github/scripts/documentation-source.cjs');
  const modules = name => {
    assert.equal(name, './.github/scripts/documentation-source.cjs');
    return {...helper, waitForPublicationSource: arguments_ => helper.waitForPublicationSource({
      ...arguments_,
      now: () => clock,
      sleep: async milliseconds => { clock += milliseconds; },
      timeoutMs: 180_000
    })};
  };
  return {calls, outputs, summary, core, github, context, modules};
}

async function executeSource(env) {
  const source = loadWorkflow('documentation-publication.yml').jobs.source;
  const script = source.steps.find(step => step.id === 'source').with.script;
  await new AsyncFunction('require', 'github', 'context', 'core', script)(env.modules, env.github, env.context, env.core);
}

test('the first beta promotion starts its own publisher without a default-branch workflow dependency', () => {
  const workflow = loadWorkflow('documentation-publication.yml');
  assert.deepEqual(workflow.on.push.branches, ['beta', 'main']);
  assert.ok(Object.hasOwn(workflow.on, 'workflow_dispatch'));
  assert.equal(workflow.on.workflow_run, undefined);
  assert.equal(workflow.on.pull_request, undefined);
  assert.match(workflow.jobs.source.if, /github\.ref == 'refs\/heads\/beta'/);
  assert.match(workflow.jobs.source.if, /github\.ref == 'refs\/heads\/main'/);
  assert.doesNotMatch(workflow.jobs.source.if, /workflow_run|default_branch/);
});

test('the actual beta publisher script waits for exact-commit verification and exposes immutable inputs', async () => {
  const env = environment({pending: true});
  await executeSource(env);
  assert.equal(env.outputs.publish, 'true');
  assert.equal(env.outputs.tested_sha, head);
  assert.equal(env.outputs.tested_tree, tree);
  assert.equal(env.outputs.target_branch, 'beta');
  assert.equal(String(env.outputs.source_run_id), '42');
  assert.ok(env.calls.filter(([operation]) => operation === 'list').length >= 3);
  assert.ok(env.calls.some(([operation]) => operation === 'run'), 'the selected API result must be re-fetched');
  assert.equal(env.calls.filter(([operation]) => operation === 'commit').length, 1);
  assert.ok(env.summary.includes('https://github.com/owner/repo/actions/runs/42'));
});

test('a trusted main dispatch uses its own verified commit rather than the beta publication context', async () => {
  const env = environment({branch: 'main', eventName: 'workflow_dispatch'});
  await executeSource(env);
  assert.equal(env.outputs.publish, 'true');
  assert.equal(env.outputs.tested_sha, head);
  assert.equal(env.outputs.tested_tree, tree);
  assert.equal(env.outputs.target_branch, 'main');
  assert.equal(String(env.outputs.source_run_id), '42');
});

test('failed release verification produces an explicit non-publication result', async () => {
  const env = environment({conclusion: 'failure'});
  await executeSource(env);
  assert.equal(env.outputs.publish, 'false');
  assert.equal(env.outputs.tested_sha, undefined);
  assert.equal(env.outputs.tested_tree, undefined);
  assert.equal(env.outputs.target_branch, undefined);
  assert.equal(env.calls.filter(([operation]) => operation === 'commit').length, 0);
  assert.match(env.summary.join('\n'), /No publication/);
  assert.ok(!env.summary.some(value => value.includes('/actions/runs/42')));
  const publication = loadWorkflow('documentation-publication.yml');
  assert.equal(publication.jobs.deploy.if, "needs.source.outputs.publish == 'true'");
  assert.equal(loadWorkflow('release-pipeline.yml').jobs.deploy, undefined);
  assert.equal(loadWorkflow('release-pipeline.yml').jobs['documentation-publication'], undefined);
});

test('an obsolete beta push cannot publish or delay the latest queued publisher', async () => {
  const env = environment({pending: true, superseded: true});
  await executeSource(env);
  assert.equal(env.outputs.publish, 'false');
  assert.equal(env.outputs.tested_sha, undefined);
  assert.equal(env.calls.filter(([operation]) => operation === 'commit').length, 0);
  assert.ok(env.calls.some(([operation]) => operation === 'ref'));
  assert.ok(env.calls.filter(([operation]) => operation === 'list').length <= 1);
});

test('publication forwards only verified source identity and keeps build jobs read-only', () => {
  const publication = loadWorkflow('documentation-publication.yml');
  assert.deepEqual(publication.permissions, {contents: 'read', actions: 'read'});
  assert.deepEqual(publication.jobs.deploy.with, {
    tested_sha: '${{ needs.source.outputs.tested_sha }}',
    tested_tree: '${{ needs.source.outputs.tested_tree }}',
    target_branch: '${{ needs.source.outputs.target_branch }}'
  });
  assert.equal(publication.jobs.deploy.needs, 'source');
  assert.equal(publication.jobs.release, undefined);
  const deploy = loadWorkflow('deploy.yml');
  assert.deepEqual(deploy.permissions, {contents: 'read'});
  assert.deepEqual(deploy.jobs.build.permissions, {contents: 'read'});
  for (const [name, job] of Object.entries(deploy.jobs)) {
    if (name !== 'deploy') {
      assert.notEqual(job.permissions?.pages, 'write');
      assert.notEqual(job.permissions?.['id-token'], 'write');
    }
  }
  assert.deepEqual(deploy.jobs.deploy.permissions, {
    contents: 'read', actions: 'read', pages: 'write', 'id-token': 'write'
  });
});
