'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const { excludedLogin } = require('../.github/scripts/release-contributors.cjs');

test('excludes maintainers and automation accounts from release credits', () => {
  for (const login of [
    'Nicxe',
    'github-actions',
    'github-actions[bot]',
    'hosted-weblate',
    'hosted-weblate[bot]',
    'weblate[bot]',
    'dependabot[bot]'
  ]) {
    assert.equal(excludedLogin(login), true, login);
  }
});

test('keeps external contributor accounts eligible for release credits', () => {
  assert.equal(excludedLogin('example-contributor'), false);
});
