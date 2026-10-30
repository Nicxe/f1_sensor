const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const workflow = fs.readFileSync(path.join(__dirname, '../.github/workflows/ci.yml'), 'utf8');
const group = workflow.match(/^  group: (.+)$/m)[1];
const reportCondition = workflow.split('  report-pr:')[1].match(/^    if: (.+)$/m)[1];
const github = (event, number = '658') => ({
  event_name: event,
  ref: 'refs/heads/dev',
  event: {
    pull_request: {number: event === 'pull_request' ? number : ''},
    inputs: {pull_request: event === 'workflow_dispatch' ? number : ''},
  },
});
const groupFor = context => group.replace(/\$\{\{(.*?)\}\}/g,
  (_, expression) => vm.runInNewContext(expression, {github: context}));

test('native and dispatched verification of the same PR cannot cancel each other', () => {
  assert.notEqual(groupFor(github('pull_request')), groupFor(github('workflow_dispatch')));
  assert.equal(groupFor(github('workflow_dispatch')), groupFor(github('workflow_dispatch')));
  assert.notEqual(groupFor(github('workflow_dispatch', '658')), groupFor(github('workflow_dispatch', '659')));
});

test('cancelled verification cannot publish failure while completed failures still report', () => {
  const expression = reportCondition.replace(/^\$\{\{\s*|\s*\}\}$/g, '');
  for (const result of ['success', 'failure']) {
    const context = {
      github: github('workflow_dispatch'),
      needs: {checks: {outputs: {tested_head: 'verified-head'}}, required: {result}},
      always: () => true,
      cancelled: () => false,
    };
    assert.equal(Boolean(vm.runInNewContext(expression, context)), true);
    context.cancelled = () => true;
    assert.equal(Boolean(vm.runInNewContext(expression, context)), false);
    context.cancelled = () => false;
    context.needs.checks.outputs.tested_head = '';
    assert.equal(Boolean(vm.runInNewContext(expression, context)), false);
  }
});

test('superseded native runs skip both gates, while real failures still reach the gates', () => {
  for (const filename of ['ci.yml','ci-checks.yml']) {
    const text=fs.readFileSync(path.join(__dirname,'../.github/workflows',filename),'utf8');
    const condition=text.split('  required:')[1].match(/^    if: (.+)$/m)[1];
    const expression=condition.replace(/^\$\{\{\s*|\s*\}\}$/g,'');
    for (const result of ['success','failure']) {
      const context={always:()=>true,cancelled:()=>false,needs:{checks:{result}}};
      assert.equal(Boolean(vm.runInNewContext(expression,context)),true);
      context.cancelled=()=>true;
      assert.equal(Boolean(vm.runInNewContext(expression,context)),false);
    }
  }
});

const yaml = require('js-yaml');
const reportScript = yaml.load(workflow).jobs['report-pr'].steps[0].with.script;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

function reporter(result = 'success') {
  const writes = [];
  const pr = {number: 956, head: {sha: 'head'}, base: {sha: 'base', ref: 'content'}};
  const externalId = 'f1-pr:956:base:head';
  const checks = [
    {id: 1, name: 'CI required', conclusion: 'success', app: {id: 15368}},
    {id: 2, external_id: externalId, conclusion: 'failure', app: {id: 15368}},
    {id: 3, external_id: 'f1-pr:955:base:head', app: {id: 15368}},
    {id: 4, external_id: externalId, app: {id: 7}},
  ];
  const github = {
    paginate: async () => checks,
    rest: {
      pulls: {get: async () => ({data: pr})},
      checks: {listForRef() {}, update: async data => writes.push(['update', data]),
        create: async data => writes.push(['create', data])},
    },
  };
  const context = {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, ref: 'refs/heads/content', runId: 123};
  const env = {PR_NUMBER: '956', TESTED_BASE: 'base', TESTED_HEAD: 'head', CI_RESULT: result};
  return {pr, checks, context, env, writes,
    run: () => new AsyncFunction('github', 'context', 'process', reportScript)(github, context, {env})};
}

test('successful trusted re-verification updates its failed check without touching native or other PR checks', async () => {
  const state = reporter();
  await state.run();
  assert.equal(state.writes.length, 1);
  const [operation, data] = state.writes[0];
  assert.equal(operation, 'update');
  assert.equal(data.check_run_id, 2);
  assert.equal(data.conclusion, 'success');
  assert.equal(data.details_url, 'https://github.com/Nicxe/f1_sensor/actions/runs/123');
});

test('native green checks cannot override a failed, skipped or cancelled trusted verification', async () => {
  for (const result of ['failure', 'skipped', 'cancelled']) {
    const state = reporter(result);
    await state.run();
    assert.equal(state.writes.length, 1);
    assert.equal(state.writes[0][1].check_run_id, 2);
    assert.equal(state.writes[0][1].conclusion, 'failure');
  }
});

test('changed PR head, base commit or target branch cannot publish a trusted result', async () => {
  for (const field of ['head', 'base', 'target']) {
    const state = reporter();
    if (field === 'head') state.pr.head.sha = 'new-head';
    if (field === 'base') state.pr.base.sha = 'new-base';
    if (field === 'target') state.pr.base.ref = 'dev';
    await assert.rejects(state.run(), /PR changed/);
    assert.deepEqual(state.writes, []);
  }
});

test('a new verified snapshot creates its own check instead of reusing an older target result', async () => {
  const state = reporter();
  state.checks[1].external_id = 'f1-pr:956:old-base:head';
  await state.run();
  assert.equal(state.writes.length, 1);
  assert.equal(state.writes[0][0], 'create');
  assert.equal(state.writes[0][1].external_id, 'f1-pr:956:base:head');
  assert.equal(state.writes[0][1].head_sha, 'head');
});
