'use strict';

const {execFileSync} = require('node:child_process');

const releaseTagPattern = /^v((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))(?:-(beta|rc)\.([1-9]\d*))?$/;

function parseReleaseTag(tag) {
  const match = releaseTagPattern.exec(String(tag));
  if (!match) return null;
  return {
    version: String(tag).slice(1),
    baseVersion: match[1],
    stage: match[2] || 'stable',
    number: match[3] ? Number(match[3]) : null
  };
}

// Only the project's stable, beta.N and rc.N formats enter this comparison.
function compareReleaseTags(left, right) {
  const a = parseReleaseTag(left);
  const b = parseReleaseTag(right);
  for (let index = 0; index < 3; index++) {
    const x = BigInt(a.baseVersion.split('.')[index]);
    const y = BigInt(b.baseVersion.split('.')[index]);
    if (x !== y) return x > y ? 1 : -1;
  }
  const order = {beta: 0, rc: 1, stable: 2};
  if (a.stage !== b.stage) return order[a.stage] - order[b.stage];
  const x = BigInt(a.number || 0);
  const y = BigInt(b.number || 0);
  return x === y ? 0 : x > y ? 1 : -1;
}

function sortedReleaseTags(tags) {
  return tags.filter(tag => parseReleaseTag(tag)).sort((a, b) => compareReleaseTags(b, a));
}

function isBranchTag(tag, branch) {
  const release = parseReleaseTag(tag);
  return Boolean(release && (branch === 'beta'
    ? release.stage !== 'stable'
    : branch === 'main' && release.stage === 'stable'));
}

function mergedReleaseTags(head = 'HEAD', {cwd = process.cwd(), env = process.env} = {}) {
  return sortedReleaseTags(execFileSync('git', ['tag', '--merged', head], {
    cwd, env, encoding: 'utf8'
  }).trim().split('\n'));
}

function latestStableTag(tags) {
  return sortedReleaseTags(tags).find(tag => parseReleaseTag(tag).stage === 'stable');
}

function releaseStage({branch, createRc = false, tags = []}) {
  if (createRc && branch !== 'beta') throw new Error('Create RC requires the beta branch.');
  if (branch === 'main') return 'stable';
  if (branch !== 'beta') throw new Error('Releases require beta or main');
  const latest = sortedReleaseTags(tags)[0];
  return createRc || (latest && parseReleaseTag(latest).stage === 'rc') ? 'rc' : 'beta';
}

function configuredStage({env = process.env, cwd = process.cwd()} = {}) {
  const branch = env.GITHUB_REF_NAME || execFileSync('git', ['branch', '--show-current'], {
    cwd, env, encoding: 'utf8'
  }).trim();
  if (env.CREATE_RC === 'true' && branch !== 'beta') throw new Error('Create RC requires the beta branch.');
  if (env.RELEASE_STAGE) {
    if (!['beta', 'rc', 'stable'].includes(env.RELEASE_STAGE)
        || (branch === 'main' && env.RELEASE_STAGE !== 'stable')
        || (branch === 'beta' && env.RELEASE_STAGE === 'stable')) {
      throw new Error('Invalid release stage for this branch.');
    }
    return env.RELEASE_STAGE;
  }
  if (branch !== 'beta') return branch === 'main' ? 'stable' : 'beta';
  return releaseStage({branch, createRc: env.CREATE_RC === 'true', tags: mergedReleaseTags('HEAD', {cwd, env})});
}

module.exports = {
  compareReleaseTags, configuredStage, isBranchTag, latestStableTag,
  mergedReleaseTags, parseReleaseTag, releaseStage, releaseTagPattern, sortedReleaseTags
};
