'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const editorial = require('../.github/scripts/release-editorial.cjs');

test('extracts only the editorial text from a promotion PR', () => {
  const body = `## Release editorial\n\n${editorial.START}\n<!-- Guidance -->\nThis beta focuses on a faster timing card.\nPlease test session changes.\n${editorial.END}`;
  assert.equal(editorial.extractEditorial(body), 'This beta focuses on a faster timing card.\nPlease test session changes.');
  assert.equal(editorial.extractEditorial('No template markers'), null);
  assert.equal(editorial.extractEditorial(`${editorial.START}\n<!-- Optional -->\n${editorial.END}`), '');
});

test('recognizes only the two managed promotion paths', () => {
  assert.equal(editorial.isPromotion({base: {ref: 'beta'}, head: {ref: 'dev'}}), true);
  assert.equal(editorial.isPromotion({base: {ref: 'main'}, head: {ref: 'beta'}}), true);
  assert.equal(editorial.isPromotion({base: {ref: 'main'}, head: {ref: 'feature/card'}}), false);
});

test('replaces the generated placeholder once and preserves final edits', () => {
  const generated = `Before\n\n${editorial.START}\n<!-- Optional editorial summary -->\n${editorial.END}\n\n### Bug fixes\n`;
  const result = editorial.replaceEditorial(generated, 'This release improves race-weekend reliability.');
  assert.equal(result.replaced, true);
  assert.equal(result.notes, 'Before\n\nThis release improves race-weekend reliability.\n\n### Bug fixes\n');
  assert.deepEqual(editorial.replaceEditorial(result.notes, 'Different text'), {notes: result.notes, replaced: false});
});

test('selects a release tag only for the matching release branch', () => {
  const run = () => 'v5.8.0-beta.5\nv5.8.0\n';
  assert.equal(editorial.releaseTagAtHead({branch: 'beta', run}), 'v5.8.0-beta.5');
  assert.equal(editorial.releaseTagAtHead({branch: 'main', run}), 'v5.8.0');
  assert.equal(editorial.releaseTagAtHead({branch: 'dev', run}), '');
});

test('selects the RC draft when the final beta and first candidate share the tested commit', () => {
  const run = () => 'v6.1.0-beta.3\nv6.1.0-rc.1\nv6.1.0\n';
  assert.equal(editorial.releaseTagAtHead({branch: 'beta', run}), 'v6.1.0-rc.1');
  assert.equal(editorial.releaseTagAtHead({branch: 'main', run}), 'v6.1.0');
});

test('rejects ambiguous candidate tags or different preview versions at the tested commit', () => {
  for (const tags of [
    'v6.1.0-rc.1\nv6.1.0-rc.2\n',
    'v6.1.0-beta.3\nv6.2.0-rc.1\n',
    'v6.1.0-beta.2\nv6.1.0-beta.3\n'
  ]) {
    assert.throws(() => editorial.releaseTagAtHead({branch: 'beta', run: () => tags}), /Ambiguous/);
  }
});

test('retries a newly created draft release until its tag is visible', async () => {
  const waits = [];
  let calls = 0;
  const release = await editorial.releaseByTag({
    github: {rest: {repos: {getReleaseByTag: async () => {
      calls += 1;
      if (calls < 3) throw {status: 404};
      return {data: {id: 42, draft: true}};
    }, listReleases: () => {}}}, paginate: async () => []},
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}},
    core: {info: () => {}},
    tag: 'v5.8.0',
    wait: async delay => waits.push(delay)
  });
  assert.equal(release.id, 42);
  assert.deepEqual(waits, [1000, 2000]);
});

test('finds a newly created draft whose tag endpoint is not available yet', async () => {
  const release = await editorial.releaseByTag({
    github: {rest: {repos: {
      getReleaseByTag: async () => { throw {status: 404}; },
      listReleases: () => {}
    }}, paginate: async () => [{id: 42, draft: true, tag_name: 'v5.8.0'}]},
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}},
    core: {info: () => {}},
    tag: 'v5.8.0',
    wait: async () => assert.fail('a visible draft should not be retried')
  });
  assert.equal(release.id, 42);
});

test('identifies only a matching draft as safe to repair', () => {
  const matching = {
    id: 42, draft: true, tag_name: 'untagged-abc123', name: 'v5.8.0-beta.6',
    target_commitish: 'beta', assets: [{name: 'f1_sensor.zip'}]
  };
  assert.equal(editorial.isUntaggedRelease(matching), true);
  assert.equal(editorial.findRepairableDraft({
    releases: [matching], tag: 'v5.8.0-beta.6', branch: 'beta',
    assetNames: ['f1_sensor.zip']
  }), matching);
  assert.equal(editorial.findRepairableDraft({
    releases: [{...matching, target_commitish: 'main'}],
    tag: 'v5.8.0-beta.6', branch: 'beta', assetNames: ['f1_sensor.zip']
  }), undefined);
  assert.equal(editorial.findRepairableDraft({
    releases: [{...matching, name: 'Other release'}],
    tag: 'v5.8.0-beta.6', branch: 'beta', assetNames: ['f1_sensor.zip']
  }), undefined);
  assert.equal(editorial.findRepairableDraft({
    releases: [{...matching, assets: []}],
    tag: 'v5.8.0-beta.6', branch: 'beta', assetNames: ['f1_sensor.zip']
  }).id, 42);
  assert.equal(editorial.findRepairableDraft({
    releases: [{...matching, tag_name: 'v5.8.0-beta.6'}],
    tag: 'v5.8.0-beta.6', branch: 'beta'
  }).id, 42);
});

test('repairs a matching untagged draft and verifies the corrected tag', async () => {
  const updates = [];
  let currentTag = 'untagged-abc123';
  let tagLookup = 0;
  const github = {
    rest: {repos: {
      getCommit: async () => ({data: {sha: 'head-sha'}}),
      getReleaseByTag: async () => {
        tagLookup += 1;
        if (tagLookup === 1) throw {status: 404};
        return {data: {id: 42, tag_name: 'v5.8.0-beta.6', draft: true}};
      },
      listReleases: () => {},
      updateRelease: async payload => {
        updates.push(payload);
        currentTag = payload.tag_name;
        return {data: {id: 42, tag_name: payload.tag_name, draft: true}};
      },
      getRelease: async () => ({data: {
        id: 42, name: 'v5.8.0-beta.6', tag_name: currentTag, draft: true,
        assets: [{name: 'f1_sensor.zip', state: 'uploaded'}]
      }})
    }},
    paginate: async () => [{
      id: 42, draft: true, tag_name: 'untagged-abc123', name: 'v5.8.0-beta.6',
      target_commitish: 'beta', assets: [{name: 'f1_sensor.zip'}]
    }]
  };
  const messages = [];
  const release = await editorial.reconcileReleaseTag({
    github,
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, sha: 'head-sha', ref: 'refs/heads/beta'},
    core: {info: message => messages.push(message), warning: message => messages.push(message)},
    tag: 'v5.8.0-beta.6',
    assetNames: ['f1_sensor.zip'],
    wait: async () => {}
  });
  assert.equal(release.tag_name, 'v5.8.0-beta.6');
  assert.deepEqual(updates, [{
    owner: 'Nicxe', repo: 'f1_sensor', release_id: 42,
    tag_name: 'v5.8.0-beta.6'
  }]);
  assert.match(messages.join('\n'), /Repairing the tag on draft release 42/);
});

test('accepts a correctly tagged draft by ID without rewriting it or querying the published endpoint', async () => {
  let tagLookups = 0;
  const updates = [];
  const release = await editorial.reconcileReleaseTag({
    github: {
      rest: {repos: {
        getCommit: async () => ({data: {sha: 'head-sha'}}),
        getReleaseByTag: async () => {
          tagLookups += 1;
          if (tagLookups === 1) throw {status: 404};
          return {data: {id: 42, tag_name: 'v5.8.0-beta.6', draft: true}};
        },
        listReleases: () => {},
        updateRelease: async payload => {
          updates.push(payload);
          return {data: {id: 42, tag_name: payload.tag_name, draft: true}};
        },
        getRelease: async () => ({data: {id: 42, tag_name: 'v5.8.0-beta.6', draft: true}})
      }},
      paginate: async () => [{
        id: 42, tag_name: 'v5.8.0-beta.6', name: 'v5.8.0-beta.6',
        target_commitish: 'beta', draft: true
      }]
    },
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, sha: 'head-sha', ref: 'refs/heads/beta'},
    core: {info() {}, warning() {}},
    tag: 'v5.8.0-beta.6',
    wait: async () => {}
  });
  assert.equal(release.id, 42);
  assert.equal(tagLookups, 0);
  assert.equal(updates.length, 0);
});

test('fails closed when no release becomes stable', async () => {
  let tagLookups = 0;
  await assert.rejects(editorial.reconcileReleaseTag({
    github: {
      rest: {repos: {
        getCommit: async () => ({data: {sha: 'head-sha'}}),
        getReleaseByTag: async () => {
          tagLookups += 1;
          throw {status: 404};
        },
        listReleases: () => {}
      }},
      paginate: async () => []
    },
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, sha: 'head-sha', ref: 'refs/heads/beta'},
    core: {info() {}, warning() {}},
    tag: 'v5.8.0-beta.6',
    wait: async () => {}
  }), /No correctly tagged release with all required assets/);
  assert.equal(tagLookups, editorial.RELEASE_LOOKUP_ATTEMPTS);
});

test('adds a promotion PR editorial to an untouched draft release', async () => {
  const updates = [];
  const github = {
    rest: {repos: {
      getReleaseByTag: async () => ({data: {
        id: 42, draft: true,
        body: `Before\n\n${editorial.START}\n<!-- Optional -->\n${editorial.END}\n\n### Bug fixes\n`
      }}),
      updateRelease: async payload => updates.push(payload)
    }},
    paginate: async () => [],
    graphql: async () => ({repository: {object: {associatedPullRequests: {nodes: [{
      number: 851, merged: true, baseRefName: 'beta', headRefName: 'dev',
      mergeCommit: {oid: 'merge-sha'},
      body: `${editorial.START}\nFaster session updates are the focus of this beta.\n${editorial.END}`
    }]}}}})
  };
  const messages = [];
  const changed = await editorial.applyReleaseEditorial({
    github,
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, sha: 'merge-sha', ref: 'refs/heads/beta'},
    core: {info: message => messages.push(message)},
    getTag: () => 'v5.8.0-beta.6'
  });
  assert.equal(changed, true);
  assert.deepEqual(updates, [{
    owner: 'Nicxe', repo: 'f1_sensor', release_id: 42,
    tag_name: 'v5.8.0-beta.6',
    body: 'Before\n\nFaster session updates are the focus of this beta.\n\n### Bug fixes\n'
  }]);
  assert.match(messages[0], /promotion PR #851/);
});

test('draft lookup does not use the published endpoint when its normal untagged URL is visible', async () => {
  const release = {id: 42, draft: true, tag_name: 'v6.1.0-beta.3', html_url: 'https://github.com/Nicxe/f1_sensor/releases/tag/untagged-abc123'};
  const result = await editorial.releaseByTag({
    github: {rest: {repos: {
      listReleases() {},
      getReleaseByTag: async () => assert.fail('A draft does not need a published tag endpoint')
    }}, paginate: async () => [release]},
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}}, core: {info() {}}, tag: release.tag_name
  });
  assert.equal(result, release);
});

test('completed draft verification waits for uploaded assets without rewriting a correct tag', async () => {
  const tag = 'v6.1.0-beta.3';
  const release = {id: 42, name: tag, draft: true, tag_name: tag, target_commitish: 'beta', body: 'Manual notes'};
  let reads = 0;
  const waits = [];
  const result = await editorial.reconcileReleaseTag({
    github: {rest: {repos: {
      getCommit: async () => ({data: {sha: 'head-sha'}}),
      listReleases() {},
      getRelease: async () => ({data: {...release, assets: ++reads > 1 ? [{name: 'f1_sensor.zip', state: 'uploaded'}] : []}}),
      updateRelease: async () => assert.fail('A correct draft tag must not be rewritten'),
      getReleaseByTag: async () => assert.fail('A draft does not need a published tag endpoint')
    }}, paginate: async () => [release]},
    context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, sha: 'head-sha', ref: 'refs/heads/beta'},
    core: {info() {}, warning() {}}, tag, assetNames: ['f1_sensor.zip'],
    wait: async delay => waits.push(delay)
  });
  assert.equal(result.draft, true);
  assert.equal(result.body, 'Manual notes');
  assert.deepEqual(waits, [1000]);
});

test('duplicate release drafts are rejected instead of repairing an arbitrary one', () => {
  const draft = {id: 42, draft: true, tag_name: 'v6.1.0-beta.3', name: 'v6.1.0-beta.3', target_commitish: 'beta'};
  assert.throws(() => editorial.findRepairableDraft({
    releases: [draft, {...draft, id: 43}], tag: draft.tag_name, branch: 'beta'
  }), /Multiple matching drafts/);
});

test('selects the promotion PR whose merge commit is the release commit', async () => {
  const context = {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, sha: 'merge-897'};
  const github = {
    graphql: async () => ({repository: {object: {associatedPullRequests: {nodes: [
      {
        number: 896,
        body: `${editorial.START}\nWrong release text\n${editorial.END}`,
        baseRefName: 'beta',
        headRefName: 'dev',
        merged: true,
        mergeCommit: {oid: 'merge-896'}
      },
      {
        number: 897,
        body: `${editorial.START}\nCorrect release text\n${editorial.END}`,
        baseRefName: 'beta',
        headRefName: 'dev',
        merged: true,
        mergeCommit: {oid: 'merge-897'}
      }
    ]}}}})
  };

  const result = await editorial.promotionPullRequest(github, context);
  assert.equal(result.number, 897);
  assert.equal(editorial.extractEditorial(result.body), 'Correct release text');
});
