'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {RELEASE_ASSETS, verifyPublishedRelease, resolvePublishedRelease} = require('../.github/scripts/release-publication.cjs');

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

function resolverFixture(overrides = {}) {
  const value = fixture(overrides);
  const resolve = ({releaseTag = '', payloadRelease} = {}) => resolvePublishedRelease({
    github: value.github,
    context: {...context, payload: payloadRelease ? {release: payloadRelease} : {}},
    core,
    releaseTag,
    wait: async delay => value.waits.push(delay)
  });
  return {...value, resolve};
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

test('strict publication verification never repairs a placeholder tag', async () => {
  const {release, github, updates} = fixture();
  const before = structuredClone(release);

  await assert.rejects(verifyPublishedRelease({
    github, context, core, releaseId: release.id, allowTagRepair: false
  }));

  assert.deepEqual(updates, []);
  assert.deepEqual(release, before);
});

test('manual publication replay verifies the requested release by ID without changing it', async () => {
  const {release, github, updates, waits, resolve} = resolverFixture({tag_name: tag});
  const before = structuredClone(release);
  const reads = [];
  const getRelease = github.rest.repos.getRelease;
  const getReleaseByTag = github.rest.repos.getReleaseByTag;
  github.rest.repos.getRelease = async parameters => {
    reads.push({id: parameters.release_id});
    return getRelease(parameters);
  };
  github.rest.repos.getReleaseByTag = async parameters => {
    reads.push({tag: parameters.tag});
    return getReleaseByTag(parameters);
  };

  assert.deepEqual(await resolve({releaseTag: `  ${tag}\n`}), before);
  assert.deepEqual(reads[0], {tag});
  assert.ok(reads.some(read => read.id === release.id));
  assert.deepEqual(updates, []);
  assert.deepEqual(waits, []);
  assert.deepEqual(release, before);
});

test('manual publication replay rejects drafts and incomplete uploaded assets without writes', async () => {
  for (const overrides of [{draft: true}, {assets: []}]) {
    const {release, updates, resolve} = resolverFixture({tag_name: tag, ...overrides});
    const before = structuredClone(release);

    await assert.rejects(resolve({releaseTag: tag}));

    assert.deepEqual(updates, []);
    assert.deepEqual(release, before);
  }
});

test('manual publication replay rejects invalid tag input before any release lookup', async () => {
  for (const releaseTag of [placeholder, 'beta', `refs/tags/${tag}`, `${tag}; false`, 'v6.1.0-rc.1']) {
    const {github, updates, resolve} = resolverFixture({tag_name: tag});
    let lookups = 0;
    const unexpectedLookup = async () => {
      lookups++;
      assert.fail('Invalid input must not reach GitHub');
    };
    github.rest.repos.getReleaseByTag = unexpectedLookup;
    github.rest.repos.getRelease = unexpectedLookup;

    await assert.rejects(resolve({releaseTag}));

    assert.equal(lookups, 0);
    assert.deepEqual(updates, []);
  }
});

test('manual publication replay rejects a tag lookup that returns a different release tag', async () => {
  for (const returnedTag of [placeholder, 'v6.1.0-beta.2']) {
    const {release, github, updates, resolve} = resolverFixture({tag_name: tag});
    let idLookups = 0;
    github.rest.repos.getReleaseByTag = async () => ({data: {...release, tag_name: returnedTag}});
    github.rest.repos.getRelease = async () => {
      idLookups++;
      assert.fail('A mismatched lookup must stop before ID verification');
    };

    await assert.rejects(resolve({releaseTag: tag}));

    assert.equal(idLookups, 0);
    assert.deepEqual(updates, []);
  }
});

test('manual publication replay does not repair a concurrent change back to a placeholder', async () => {
  const {release, github, updates, resolve} = resolverFixture({tag_name: tag});
  const getReleaseByTag = github.rest.repos.getReleaseByTag;
  github.rest.repos.getReleaseByTag = async parameters => {
    const response = await getReleaseByTag(parameters);
    release.tag_name = placeholder;
    return response;
  };

  await assert.rejects(resolve({releaseTag: tag}));

  assert.equal(release.tag_name, placeholder);
  assert.deepEqual(updates, []);
});

test('manual publication replay rejects a concurrent change to another valid version', async () => {
  const {release, github, updates, resolve} = resolverFixture({tag_name: tag});
  const changedTag = 'v6.1.0-beta.2';
  const getReleaseByTag = github.rest.repos.getReleaseByTag;
  let firstLookup = true;
  github.rest.repos.getReleaseByTag = async parameters => {
    const response = await getReleaseByTag(parameters);
    if (firstLookup) {
      firstLookup = false;
      release.tag_name = changedTag;
      release.name = changedTag;
    }
    return response;
  };

  await assert.rejects(resolve({releaseTag: tag}));

  assert.equal(release.tag_name, changedTag);
  assert.deepEqual(updates, []);
});

test('release-event resolution preserves the existing canonical tag-repair policy', async () => {
  const {release, updates, resolve} = resolverFixture();
  const before = structuredClone(release);

  const result = await resolve({payloadRelease: {id: release.id, tag_name: placeholder}});

  assert.deepEqual(result, {...before, tag_name: tag});
  assert.deepEqual(updates, [{...context.repo, release_id: release.id, tag_name: tag}]);
});

test('publication resolution rejects simultaneous event and manual release selectors', async () => {
  const {release, github, updates, resolve} = resolverFixture({tag_name: tag});
  let lookups = 0;
  const unexpectedLookup = async () => {
    lookups++;
    assert.fail('Ambiguous selectors must not reach GitHub');
  };
  github.rest.repos.getReleaseByTag = unexpectedLookup;
  github.rest.repos.getRelease = unexpectedLookup;

  await assert.rejects(resolve({releaseTag: tag, payloadRelease: {id: release.id}}));

  assert.equal(lookups, 0);
  assert.deepEqual(updates, []);
});

test('publication resolution without a selector preserves manual branch synchronization', async () => {
  const {github, updates} = fixture();
  github.rest.repos.getReleaseByTag = async () => assert.fail('Manual branch synchronization must not load a release');
  github.rest.repos.getRelease = async () => assert.fail('Manual branch synchronization must not load a release');
  const manualContext = {...context, payload: {inputs: {source: 'beta', target: 'dev'}}};

  for (const releaseTag of ['', ' \n ']) {
    assert.equal(await resolvePublishedRelease({github, context: manualContext, core, releaseTag}), undefined);
  }

  assert.deepEqual(updates, []);
});
