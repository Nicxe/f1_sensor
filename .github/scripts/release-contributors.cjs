'use strict';

const { execFileSync } = require('node:child_process');

const run = (command, args, options = {}) =>
  execFileSync(command, args, { encoding: 'utf8', ...options });

const releaseTagPattern = /^v\d+\.\d+\.\d+(?:-(?:beta|rc)\.\d+)?$/;

function previousReleaseTag(branch, head = 'HEAD', excludeTag, stage) {
  return run('git', ['tag', '--merged', head, '--sort=-version:refname'])
    .trim()
    .split('\n')
    .find(
      (tag) =>
        tag !== head &&
        tag !== excludeTag &&
        releaseTagPattern.test(tag) &&
        (branch === 'beta' && stage !== 'rc' ? /-(?:beta|rc)\./.test(tag) : !tag.includes('-'))
    );
}

function excludedLogin(login) {
  const normalized = String(login || '').trim().toLowerCase();
  return (
    !normalized ||
    normalized === 'nicxe' ||
    normalized === 'github-actions' ||
    normalized === 'github-actions[bot]' ||
    normalized === 'hosted-weblate' ||
    normalized === 'hosted-weblate[bot]' ||
    normalized === 'weblate' ||
    normalized === 'weblate[bot]' ||
    normalized.endsWith('[bot]') ||
    normalized === 'dependabot' ||
    normalized === 'renovate'
  );
}

function commitHashes(branch, head = 'HEAD', excludeTag, stage) {
  const previous = previousReleaseTag(branch, head, excludeTag, stage);
  return run('git', [
    'rev-list',
    '--reverse',
    previous ? `${previous}..${head}` : head
  ])
    .trim()
    .split('\n')
    .filter(Boolean);
}

function collectContributors({ branch, head = 'HEAD', excludeTag, stage }) {
  const repository = process.env.GITHUB_REPOSITORY;
  if (!repository) return [];

  const logins = new Set();
  for (const hash of commitHashes(branch, head, excludeTag, stage)) {
    const output = run('gh', [
      'api',
      `repos/${repository}/commits/${hash}/pulls`,
      '--header',
      'Accept: application/vnd.github+json',
      '--jq',
      '.[].user.login'
    ]);
    for (const login of output.split(/\r?\n/)) {
      if (!excludedLogin(login)) logins.add(login.trim());
    }
  }
  return [...logins].sort((a, b) => a.localeCompare(b));
}

function setReleaseContributors({ branch, head = 'HEAD', excludeTag, stage }) {
  try {
    const contributors = collectContributors({ branch, head, excludeTag, stage });
    process.env.RELEASE_CONTRIBUTORS = JSON.stringify(contributors);
    console.log(
      contributors.length
        ? `Release contributors: ${contributors.join(', ')}`
        : 'Release contributors: none after bot and maintainer filtering.'
    );
    return contributors;
  } catch (error) {
    // Contributor credits are additive; an API outage must not block a release.
    console.warn(`Unable to collect release contributors: ${error.message}`);
    process.env.RELEASE_CONTRIBUTORS = '[]';
    return [];
  }
}

module.exports = {
  collectContributors,
  excludedLogin,
  previousReleaseTag,
  setReleaseContributors
};
