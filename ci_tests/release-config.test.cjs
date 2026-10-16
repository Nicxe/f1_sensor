'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const config = require('../release.config.cjs');

test('does not release the known internal-only fixes again', () => {
  const analyzer = config.plugins.find(plugin => Array.isArray(plugin)
    && plugin[0] === '@semantic-release/commit-analyzer');
  const rules = analyzer?.[1]?.releaseRules || [];
  assert.deepEqual(rules.filter(rule => rule.release === false), [
    {
      type: 'fix',
      scope: 'compatibility',
      subject: 'Verify release tags from GitHub directly',
      release: false
    },
    {
      type: 'fix',
      scope: 'compatibility',
      subject: 'tolerate delayed release assets',
      release: false
    },
    {
      type: 'fix',
      scope: 'ci',
      subject: 'wait for promotion verification registration',
      release: false
    }
  ]);
});

test('misclassified release-workflow history produces no semantic release', async () => {
  const analyzer = config.plugins.find(plugin => Array.isArray(plugin)
    && plugin[0] === '@semantic-release/commit-analyzer');
  const {analyzeCommits} = await import('@semantic-release/commit-analyzer');
  const releaseType = await analyzeCommits(analyzer[1], {
    commits: [
      {message: 'fix(compatibility): Verify release tags from GitHub directly'},
      {message: 'fix(compatibility): tolerate delayed release assets'},
      {message: 'fix(ci): wait for promotion verification registration'}
    ],
    logger: {log() {}}
  });
  assert.equal(releaseType, null);
});
