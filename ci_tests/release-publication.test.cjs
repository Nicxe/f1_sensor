'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {RELEASE_ASSETS, verifyPublishedRelease} = require('../.github/scripts/release-publication.cjs');

const tag = 'v6.1.0-beta.3';
const placeholder = 'untagged-3083a602f3cc784594f8';
const context = {repo: {owner: 'Nicxe', repo: 'f1_sensor'}};
const core = {info() {}, warning() {}};

function fixture(overrides = {}) {
  const release = {
    id: 42, name: tag, tag_name: placeholder, draft: false, prerelease: true,
    body: 'Edited and manually published in GitHub', target_commitish: 'beta',
    published_at: '2026-10-20T12:22:20Z',
    assets: RELEASE_ASSETS.map((name, id) => ({id, name, state: 'uploaded', size: id + 100, digest: `sha256:${id}`})),
    ...overrides
  };
  const updates = [];
  const waits = [];
  const github = {rest: {repos: {
    getRelease: async () => ({data: structuredClone(release)}),
    getCommit: async () => ({data: {sha: 'release-sha'}}),
    getReleaseByTag: async ({tag: requested}) => {
      if (requested !== release.tag_name) throw {status: 404};
      return {data: structuredClone(release)};
    },
    updateRelease: async payload => {
      updates.push(payload);
      release.tag_name = payload.tag_name;
      return {data: structuredClone(release)};
    }
  }}};
  const verify = () => verifyPublishedRelease({
    github, context, core, releaseId: 42, wait: async delay => waits.push(delay)
  });
  return {release, github, updates, waits, verify};
}

test('repairs a manually published placeholder only when both tags identify the same commit', async () => {
  const {release, updates, verify} = fixture();
  const before = structuredClone(release);
  const result = await verify();
  assert.equal(result.tag_name, tag);
  assert.deepEqual(updates, [{...context.repo, release_id: 42, tag_name: tag}]);
  assert.deepEqual(result, {...before, tag_name: tag});
});

test('a correctly tagged publication is read-only, including after another consumer repaired it', async () => {
  const {updates, verify} = fixture({tag_name: tag, name: 'Custom release title'});
  assert.equal((await verify()).tag_name, tag);
  assert.deepEqual(updates, []);
});

test('never publishes an unpublished draft', async () => {
  const {updates, verify} = fixture({draft: true});
  await assert.rejects(verify(), /already published releases; drafts remain manual/);
  assert.deepEqual(updates, []);
});

test('never moves a release to a different commit', async () => {
  const {github, updates, verify} = fixture();
  github.rest.repos.getCommit = async ({ref}) => ({data: {sha: ref === tag ? 'other-sha' : 'release-sha'}});
  await assert.rejects(verify(), /different commit or release branch/);
  assert.deepEqual(updates, []);
});

test('requires an existing version tag instead of creating one', async () => {
  const {github, updates, verify} = fixture();
  github.rest.repos.getCommit = async () => { throw {status: 404}; };
  await assert.rejects(verify(), error => error.status === 404);
  assert.deepEqual(updates, []);
});

test('refuses ambiguous versions, unrelated tags, wrong channels and missing assets', async () => {
  for (const overrides of [
    {name: 'A custom title with no version'},
    {tag_name: 'another-release'},
    {tag_name: 'v6.1.0-beta.2'},
    {prerelease: false},
    {target_commitish: 'dev'},
    {assets: []}
  ]) {
    const {updates, verify} = fixture(overrides);
    await assert.rejects(verify());
    assert.deepEqual(updates, []);
  }
});

test('does not take a version already used by another published release', async () => {
  const {github, updates, verify} = fixture();
  github.rest.repos.getReleaseByTag = async () => ({data: {id: 99, tag_name: tag, draft: false}});
  await assert.rejects(verify(), /already belongs to another release/);
  assert.deepEqual(updates, []);
});

test('waits for the published tag lookup after metadata correction', async () => {
  const {github, waits, verify} = fixture();
  const lookup = github.rest.repos.getReleaseByTag;
  let reads = 0;
  github.rest.repos.getReleaseByTag = async payload => {
    if (++reads < 4) throw {status: 404};
    return lookup(payload);
  };
  assert.equal((await verify()).tag_name, tag);
  assert.deepEqual(waits, [1000, 2000]);
});

test('a concurrent change to notes is preserved and blocks downstream automation', async () => {
  const {release, github, verify} = fixture();
  const update = github.rest.repos.updateRelease;
  github.rest.repos.updateRelease = async payload => {
    await update(payload);
    release.body = 'New manual edit';
  };
  await assert.rejects(verify(), /changed during tag verification/);
  assert.equal(release.body, 'New manual edit');
});

test('does not republish a release that becomes a draft during verification', async () => {
  const {release, github, updates, verify} = fixture();
  const update = github.rest.repos.updateRelease;
  github.rest.repos.updateRelease = async payload => {
    await update(payload);
    release.draft = true;
  };
  await assert.rejects(verify(), /no longer published/);
  assert.equal(release.draft, true);
  assert.ok(updates.every(payload => !Object.hasOwn(payload, 'draft')));
});

test('supports stable releases with the same manual-publication safeguards', async () => {
  const {release, verify} = fixture({name: 'v6.1.0', prerelease: false, target_commitish: 'main'});
  assert.equal((await verify()).tag_name, 'v6.1.0');
  assert.equal(release.draft, false);
});
