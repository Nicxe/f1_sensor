'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  isBranchTag,
  latestStableTag,
  parseReleaseTag,
  releaseStage,
  sortedReleaseTags
} = require('../.github/scripts/release-stage.cjs');

test('release stages sort by semantic version rather than tag spelling', () => {
  const tags = [
    'v1.9.0', 'v1.10.0-beta.2', 'v1.10.0-beta.12',
    'v1.10.0-rc.1', 'v1.10.0', 'v2.0.0-beta.1',
    'unrelated', 'v1.10.0-alpha.1', 'v1.10.0-rc.01'
  ];
  assert.deepEqual(sortedReleaseTags(tags), [
    'v2.0.0-beta.1', 'v1.10.0', 'v1.10.0-rc.1',
    'v1.10.0-beta.12', 'v1.10.0-beta.2', 'v1.9.0'
  ]);
  assert.equal(latestStableTag(tags), 'v1.10.0');
  assert.deepEqual(parseReleaseTag('v1.10.0-rc.12'), {
    version: '1.10.0-rc.12', baseVersion: '1.10.0', stage: 'rc', number: 12
  });
});

test('RC stays on beta until stable history closes the cycle', () => {
  const tags = ['v1.0.0', 'v1.1.0-beta.1', 'v1.1.0-beta.2'];
  assert.equal(releaseStage({branch: 'beta', tags}), 'beta');
  assert.equal(releaseStage({branch: 'beta', tags, createRc: true}), 'rc');
  assert.equal(releaseStage({branch: 'beta', tags: [...tags, 'v1.1.0-rc.1']}), 'rc');
  assert.equal(releaseStage({branch: 'beta', tags: [...tags, 'v1.1.0-rc.1', 'v1.1.0']}), 'beta');
  assert.equal(releaseStage({branch: 'main', tags: [...tags, 'v1.1.0-rc.1']}), 'stable');
  assert.equal(releaseStage({branch: 'beta', tags: []}), 'beta');
});

test('only beta may start RC and managed branches accept their own version kinds', () => {
  for (const branch of ['main', 'dev', 'content', '']) {
    assert.throws(() => releaseStage({branch, createRc: true}), /requires the beta branch/);
  }
  assert.throws(() => releaseStage({branch: 'dev'}), /require beta or main/);
  assert.equal(isBranchTag('v1.1.0-beta.2', 'beta'), true);
  assert.equal(isBranchTag('v1.1.0-rc.1', 'beta'), true);
  assert.equal(isBranchTag('v1.1.0', 'main'), true);
  assert.equal(isBranchTag('v1.1.0', 'beta'), false);
  assert.equal(isBranchTag('v1.1.0-rc.1', 'main'), false);
  assert.equal(isBranchTag('v1.1.0-rc.1', 'dev'), false);
  for (const tag of ['1.1.0-rc.1', 'v1.1.0-rc.0', 'v1.1.0-rc.01',
    'v01.1.0', 'v1.1.0-alpha.1', 'v1.1.0-rc.1-extra', 'untagged-123']) {
    assert.equal(parseReleaseTag(tag), null, `${tag} is outside the supported release format`);
    assert.equal(isBranchTag(tag, 'beta'), false);
    assert.equal(isBranchTag(tag, 'main'), false);
  }
});

test('installed semantic-release supports beta to RC on the same branch and resets the next cycle', async () => {
  const {default: getLastRelease} = await import('../node_modules/semantic-release/lib/get-last-release.js');
  const {default: getNextVersion} = await import('../node_modules/semantic-release/lib/get-next-version.js');
  const tags = [
    {version: '1.0.0', gitTag: 'v1.0.0', channels: [null]},
    {version: '1.1.0-beta.1', gitTag: 'v1.1.0-beta.1', channels: ['beta']},
    {version: '1.1.0-beta.2', gitTag: 'v1.1.0-beta.2', channels: ['beta']}
  ];
  const evaluate = ({branch = 'beta', createRc = false, type = 'patch'}) => {
    const stage = releaseStage({branch, createRc, tags: tags.map(tag => tag.gitTag)});
    const context = {
      branch: {name: branch, type: branch === 'main' ? 'release' : 'prerelease',
        channel: branch === 'main' ? undefined : 'beta', prerelease: stage, tags},
      options: {tagFormat: 'v${version}'},
      nextRelease: {type, channel: branch === 'main' ? undefined : 'beta'},
      logger: {log() {}}
    };
    context.lastRelease = getLastRelease(context);
    return {previous: context.lastRelease.gitTag, next: getNextVersion(context)};
  };

  assert.deepEqual(evaluate({}), {previous: 'v1.1.0-beta.2', next: '1.1.0-beta.3'});
  // First RC re-analyzes the full stable-to-candidate range, including its feature.
  assert.deepEqual(evaluate({createRc: true, type: 'minor'}), {
    previous: 'v1.0.0', next: '1.1.0-rc.1'
  });
  tags.push({version: '1.1.0-rc.1', gitTag: 'v1.1.0-rc.1', channels: ['beta']});
  assert.deepEqual(evaluate({}), {previous: 'v1.1.0-rc.1', next: '1.1.0-rc.2'});
  assert.deepEqual(evaluate({branch: 'main', type: 'minor'}), {
    previous: 'v1.0.0', next: '1.1.0'
  });
  tags.push({version: '1.1.0', gitTag: 'v1.1.0', channels: [null]});
  assert.deepEqual(evaluate({type: 'minor'}), {
    previous: 'v1.1.0', next: '1.2.0-beta.1'
  });
});
