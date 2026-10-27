const test = require('node:test');
const assert = require('node:assert/strict');
const {cleanupMergedBranch, missingReference} = require('../.github/scripts/cleanup-branch.cjs');

function environment({branch = 'feature/fix', current = 'head', failure, at = 'deleteRef'} = {}) {
  const calls = [];
  const github = {rest: {git: {
    async getRef(args) {
      calls.push(['get', args.ref]);
      if (at === 'getRef' && failure) throw failure;
      return {data: {object: {sha: current}}};
    },
    async deleteRef(args) {
      calls.push(['delete', args.ref]);
      if (failure) throw failure;
    }
  }}};
  const context = {repo: {owner: 'owner', repo: 'repo'}, payload: {pull_request: {
    merged: true, head: {ref: branch, sha: 'head', repo: {full_name: 'owner/repo'}}
  }}};
  return {github, context, core: {info() {}}, calls};
}

test('merged temporary branch cleanup is idempotent for missing references only', async () => {
  const active = environment();
  assert.equal(await cleanupMergedBranch(active), 'deleted');
  assert.deepEqual(active.calls, [['get', 'heads/feature/fix'], ['delete', 'heads/feature/fix']]);
  for (const at of ['getRef', 'deleteRef']) {
    for (const failure of [{status: 404}, {status: 422, response: {data: {message: 'Reference does not exist'}}}]) {
      assert.equal(await cleanupMergedBranch(environment({at, failure})), 'already_missing');
    }
  }
});

test('protection, permission, rate-limit and server failures remain failures', async () => {
  for (const failure of [
    {status: 422, response: {data: {message: 'Cannot delete a protected branch'}}},
    {status: 422, message: 'Validation Failed'},
    {status: 403, message: 'Reference does not exist'},
    {status: 429}, {status: 500}
  ]) {
    assert.equal(missingReference(failure), false);
    await assert.rejects(cleanupMergedBranch(environment({failure})), error => error === failure);
  }
});

test('permanent, unmerged, foreign and advanced branches are preserved', async () => {
  for (const branch of ['main', 'beta', 'content', 'dev']) {
    const env = environment({branch});
    assert.equal(await cleanupMergedBranch(env), 'preserved');
    assert.deepEqual(env.calls, []);
  }
  for (const foreign of [false, true]) {
    const env = environment();
    if (foreign) env.context.payload.pull_request.head.repo.full_name = 'fork/repo';
    else env.context.payload.pull_request.merged = false;
    assert.equal(await cleanupMergedBranch(env), 'preserved');
    assert.deepEqual(env.calls, []);
  }
  const advanced = environment({current: 'new-work'});
  assert.equal(await cleanupMergedBranch(advanced), 'preserved');
  assert.deepEqual(advanced.calls, [['get', 'heads/feature/fix']]);
});
