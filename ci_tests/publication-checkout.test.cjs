'use strict';

const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const {createRequire} = require('node:module');
const os = require('node:os');
const path = require('node:path');
const yaml = require('js-yaml');
const {RELEASE_ASSETS} = require('../.github/scripts/release-publication.cjs');

const root = path.resolve(__dirname, '..');
const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
const workflows = ['sync-after-release.yml', 'issue-release-comment.yml'];
const tag = 'v6.1.0-beta.4';

function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'f1-publication-checkout-'));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const git = (...args) => execFileSync('git', args, {cwd: directory, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).trim();
  git('init', '--quiet', '--initial-branch=main');
  git('config', 'user.email', 'fixture@example.test');
  git('config', 'user.name', 'Publication fixture');
  fs.writeFileSync(path.join(directory, 'README.md'), 'Older stable source without publication helpers.\n');
  git('add', '.');
  git('commit', '--quiet', '-m', 'Older main');
  git('checkout', '--quiet', '-b', 'beta');
  fs.writeFileSync(path.join(directory, 'README.md'), 'Published beta predating the workflow correction.\n');
  git('add', '.');
  git('commit', '--quiet', '-m', 'Published beta');
  const publishedSha = git('rev-parse', 'HEAD');
  git('tag', tag);
  fs.cpSync(path.join(root, '.github/scripts'), path.join(directory, '.github/scripts'), {recursive: true});
  fs.mkdirSync(path.join(directory, '.github/workflows'), {recursive: true});
  for (const file of workflows) fs.copyFileSync(path.join(root, '.github/workflows', file), path.join(directory, '.github/workflows', file));
  git('add', '.');
  git('commit', '--quiet', '-m', 'New publication automation');
  const workflowSha = git('rev-parse', 'HEAD');
  const release = {
    id: 42, tag_name: tag, name: tag, draft: false, prerelease: true,
    target_commitish: 'beta', published_at: '2026-10-23T06:43:32Z',
    html_url: `https://github.com/example/f1_sensor/releases/tag/${tag}`,
    body: 'Fixes #123.',
    assets: RELEASE_ASSETS.map((name, id) => ({id, name, state: 'uploaded', size: 100 + id})),
  };
  const reads = [], writes = [], messages = [];
  const github = {
    paginate: async () => [],
    rest: {
      repos: {
        getReleaseByTag: async ({tag: requested}) => {
          assert.equal(requested, tag);
          reads.push('release-by-tag');
          return {data: structuredClone(release)};
        },
        getRelease: async ({release_id}) => {
          assert.equal(release_id, release.id);
          reads.push('release-by-id');
          return {data: structuredClone(release)};
        },
        updateRelease: async () => assert.fail('Recovery must not edit or republish the release'),
        createRelease: async () => assert.fail('Recovery must not create a release'),
        compareCommits: async () => ({data: {status: 'identical'}}),
      },
      git: {getRef: async ({ref}) => {
        reads.push(ref);
        return {data: {object: {sha: publishedSha}}};
      }},
      issues: {
        get: async ({issue_number}) => {
          reads.push(`issue:${issue_number}`);
          return {data: {title: '[Bug]: session state', body: '', labels: [], state: 'open'}};
        },
        getLabel: async () => ({data: {}}),
        addLabels: async request => writes.push({action: 'labels', ...request}),
        listComments() {},
        createComment: async request => writes.push({action: 'comment', ...request}),
      },
    },
  };
  const core = {info: message => messages.push(message), warning: message => messages.push(message)};

  async function run(file, {event = 'release', releaseTag = '', issueNumbers = '', refOverride} = {}) {
    git('checkout', '--quiet', '--detach', workflowSha);
    const workflow = yaml.load(fs.readFileSync(path.join(directory, '.github/workflows', file), 'utf8'));
    const steps = Object.values(workflow.jobs)[0].steps;
    const checkout = steps.find(step => step.uses?.startsWith('actions/checkout@'));
    const expression = refOverride || checkout.with.ref;
    const match = expression.match(/^\$\{\{\s*(.*?)\s*\}\}$/);
    assert.ok(match, 'The checkout must explicitly resolve its automation revision');
    const ref = new Function('github', `return (${match[1]});`)({
      workflow_sha: workflowSha, sha: publishedSha, event_name: event,
      ref: event === 'release' ? `refs/tags/${tag}` : 'refs/heads/beta',
      event: {repository: {default_branch: 'main'}},
    });
    git('checkout', '--quiet', '--detach', ref);
    const context = {
      repo: {owner: 'example', repo: 'f1_sensor'},
      payload: event === 'release'
        ? {release: structuredClone(release)}
        : {inputs: {source: 'beta', target: 'dev', release_tag: releaseTag}},
    };
    const previous = {RELEASE_TAG: process.env.RELEASE_TAG, ISSUE_NUMBERS: process.env.ISSUE_NUMBERS};
    process.env.RELEASE_TAG = releaseTag;
    process.env.ISSUE_NUMBERS = issueNumbers;
    try {
      for (const step of steps.filter(step => step.with?.script)) {
        await new AsyncFunction('github', 'context', 'core', 'require', step.with.script)(
          github, context, core, createRequire(path.join(directory, 'workflow-runner.cjs'))
        );
      }
    } finally {
      for (const [name, value] of Object.entries(previous)) {
        if (value === undefined) delete process.env[name];
        else process.env[name] = value;
      }
    }
    assert.equal(git('rev-parse', 'HEAD'), workflowSha, 'Automation must use its workflow revision, not main or the older release tag');
  }
  return {run, release, reads, writes, messages};
}

for (const file of workflows) {
  for (const event of ['release', 'workflow_dispatch']) {
    test(`${file} loads real helpers from its workflow revision with older main (${event})`, async t => {
      const env = fixture(t);
      const before = structuredClone(env.release);
      await env.run(file, {event, releaseTag: event === 'workflow_dispatch' ? tag : ''});
      assert.ok(env.reads.includes('release-by-id'));
      assert.deepEqual(env.release, before);
      if (file === 'sync-after-release.yml') {
        assert.deepEqual(env.writes, []);
        assert.ok(!env.reads.some(read => read.startsWith('heads/')));
        assert.ok(env.messages.some(message => /does not require automatic synchronization/.test(message)));
      } else {
        assert.deepEqual(env.reads.filter(read => read.startsWith('issue:')), ['issue:123']);
        assert.equal(env.writes.filter(write => write.action === 'comment').length, 1);
      }
    });
  }
  test(`${file} reproduces the missing module when automation is checked out from older main`, async t => {
    const env = fixture(t);
    await assert.rejects(env.run(file, {refOverride: '${{ github.event.repository.default_branch }}'}), error =>
      error.code === 'MODULE_NOT_FOUND' && error.message.includes('release-publication.cjs'));
    assert.deepEqual(env.writes, []);
  });
  test(`${file} stops before consumers when a replay selects an unpublished draft`, async t => {
    const env = fixture(t);
    env.release.draft = true;
    await assert.rejects(env.run(file, {event: 'workflow_dispatch', releaseTag: tag}), /published/);
    assert.deepEqual(env.writes, []);
  });
}

test('manual branch synchronization remains available without a publication replay tag', async t => {
  const env = fixture(t);
  await env.run('sync-after-release.yml', {event: 'workflow_dispatch'});
  assert.deepEqual(env.reads, ['heads/beta', 'heads/dev']);
  assert.deepEqual(env.writes, []);
});

test('manual issue backfill retains explicit issue numbers instead of release-note discovery', async t => {
  const env = fixture(t);
  await env.run('issue-release-comment.yml', {event: 'workflow_dispatch', releaseTag: tag, issueNumbers: '#456, 789'});
  assert.deepEqual(env.reads.filter(read => read.startsWith('issue:')), ['issue:456', 'issue:789']);
  assert.equal(env.writes.filter(write => write.action === 'comment').length, 2);
});

test('publication replay with no release-note references does not invent issue notifications', async t => {
  const env = fixture(t);
  env.release.body = 'Translation and documentation updates.';
  await env.run('issue-release-comment.yml', {event: 'workflow_dispatch', releaseTag: tag});
  assert.ok(env.reads.includes('release-by-id'));
  assert.deepEqual(env.writes, []);
});
