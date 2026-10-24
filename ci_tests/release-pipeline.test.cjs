const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('js-yaml');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const workflowScripts = file => Object.values(yaml.load(read(file)).jobs)
  .flatMap(job => job.steps || []).filter(step => step.with?.script).map(step => step.with.script);

test('prepares the editorial before final verification and gives the maintainer the manual publication link', async () => {
  const events = [];
  const content = [];
  const summary = {
    addHeading(text) { content.push(text); return this; },
    addRaw(text) { content.push(text); return this; },
    addLink(label, url) { content.push(url); return this; },
    async write() { events.push('summary'); }
  };
  const editorial = {
    releaseTagAtHead: () => 'v6.1.0-beta.3',
    applyReleaseEditorial: async () => events.push('editorial'),
    reconcileReleaseTag: async () => {
      events.push('verify');
      return {draft: true, html_url: 'https://github.com/Nicxe/f1_sensor/releases/tag/untagged-abc123'};
    }
  };
  for (const script of workflowScripts('.github/workflows/release.yml')) {
    await new AsyncFunction('github', 'context', 'core', 'require', script)(
      {}, {ref: 'refs/heads/beta'}, {summary}, () => editorial
    );
  }
  assert.deepEqual(events, ['editorial', 'verify', 'summary']);
  assert.match(content.join('\n'), /v6\.1\.0-beta\.3/);
  assert.match(content.join('\n'), /Publication is always manual/);
  assert.ok(content.includes('https://github.com/Nicxe/f1_sensor/releases/edit/untagged-abc123'));
});

test('publication consumers use the verified release and stop downstream work if verification fails', async () => {
  for (const file of ['.github/workflows/issue-release-comment.yml', '.github/workflows/sync-after-release.yml']) {
    const script = workflowScripts(file).at(-1);
    for (const fail of [false, true]) {
      const events = [];
      const canonical = {id: 42, draft: false, tag_name: 'v6.1.0-beta.3'};
      const context = {payload: {release: {id: 42, tag_name: 'untagged-abc123'}}};
      const modules = {
        './.github/scripts/release-publication.cjs': {resolvePublishedRelease: async ({context}) => {
          assert.equal(context.payload.release.id, 42);
          events.push('verify');
          if (fail) throw new Error('verification failed');
          return canonical;
        }},
        './.github/scripts/issue-automation.cjs': {releasedIssues: async (environment, {release}) => {
          assert.equal(release, canonical);
          events.push('consume');
        }},
        './.github/scripts/sync-branches.cjs': {synchronize: async ({context}) => {
          assert.equal(context.payload.release, canonical);
          events.push('consume');
        }}
      };
      const run = () => new AsyncFunction('github', 'context', 'core', 'require', script)(
        {}, context, {info() {}}, name => modules[name]
      );
      if (fail) await assert.rejects(run(), /verification failed/);
      else await run();
      assert.deepEqual(events, fail ? ['verify'] : ['verify', 'consume']);
    }
  }
});

test('release verification executes fresh checks before target release work', () => {
  const workflow = read('.github/workflows/release-pipeline.yml');
  assert.match(workflow, /checks:\n\s+uses: \.\/\.github\/workflows\/ci-checks\.yml\n\s+with:\n\s+allow_reuse: false/);
  assert.match(workflow, /release:\n\s+needs: \[checks, security\]/);
  assert.equal(yaml.load(workflow).jobs.deploy, undefined);
  assert.equal(yaml.load(workflow).jobs.context7, undefined);
});

test('release safety blocks a draft while unrelated documentation failure does not', () => {
  const workflow = yaml.load(read('.github/workflows/release-pipeline.yml'));
  const expression = workflow.jobs.release.if.trim();
  const environment = () => ({
    cancelled: () => false,
    needs: {checks: {result: 'success', outputs: {product_result: 'success'}},
      security: {result: 'success'}, documentation: {result: 'failure'}},
    vars: {}, inputs: {release: true},
    github: {event_name: 'push', ref: 'refs/heads/beta'}
  });
  assert.equal(vm.runInNewContext(expression, environment()), true);
  for (const failed of ['failure', 'cancelled', 'skipped', undefined]) {
    const env = environment();
    env.needs.security.result = failed;
    assert.equal(vm.runInNewContext(expression, env), false);
  }
  const productFailure = environment();
  productFailure.needs.checks.outputs.product_result = 'failure';
  assert.equal(vm.runInNewContext(expression, productFailure), false);
  assert.equal(workflow.jobs.security.with.mode, 'gate');
  assert.equal(workflow.jobs.security.with.checkout_ref, '${{ needs.checks.outputs.tested_sha }}');
  assert.equal(workflow.jobs.documentation.with.checkout_ref, '${{ needs.checks.outputs.tested_sha }}');
});

test('Context7 runs only after a successful main documentation deployment', () => {
  const workflow = read('.github/workflows/documentation-publication.yml');
  assert.match(workflow, /context7:\n\s+needs: \[source, deploy\]/);
  assert.match(workflow, /needs\.deploy\.result == 'success'/);
  assert.match(workflow, /needs\.source\.outputs\.target_branch == 'main'/);
  assert.match(workflow, /needs\.deploy\.outputs\.published == 'true'/);
  assert.equal(fs.existsSync(path.join(root, '.github/workflows/context7-refresh.yml')), false);
});
