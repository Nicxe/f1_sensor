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
