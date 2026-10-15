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
    graphql: async () => ({repository: {object: {associatedPullRequests: {nodes: [{
      number: 851, merged: true, baseRefName: 'beta', headRefName: 'dev',
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
    body: 'Before\n\nFaster session updates are the focus of this beta.\n\n### Bug fixes\n'
  }]);
  assert.match(messages[0], /promotion PR #851/);
});
