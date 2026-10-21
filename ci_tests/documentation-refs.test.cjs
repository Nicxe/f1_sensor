const test = require('node:test');
const assert = require('node:assert/strict');
const {resolveDocumentationRefs, publicationStillCurrent, latestVerifiedCommit} = require('../.github/scripts/documentation-refs.cjs');

const testedSha = 'a'.repeat(40);
const testedTree = 'b'.repeat(40);
const stableSha = 'c'.repeat(40);
const nextSha = 'd'.repeat(40);
const unverifiedSha = 'e'.repeat(40);
const release = (branch, sha, id = 42) => ({id, head_sha: sha, head_branch: branch,
  repository: {full_name: 'owner/repo'}, head_repository: {full_name: 'owner/repo'},
  event: 'push', path: '.github/workflows/release-pipeline.yml', status: 'completed', conclusion: 'success'});

function environment({branch = 'beta', tree = testedTree, beta = testedSha, stable = stableSha,
  proofs = {main: [release('main', stableSha)], beta: [release('beta', testedSha)]}, compare} = {}) {
  const requests = [];
  const current = {main: stable, beta};
  return {
    testedSha, testedTree, targetBranch: branch,
    context: {repo: {owner: 'owner', repo: 'repo'}, ref: 'refs/heads/main'},
    core: {info() {}},
    github: {rest: {
      git: {
        async getCommit({commit_sha}) {assert.equal(commit_sha, testedSha); return {data: {tree: {sha: tree}}};},
        async getRef({ref}) {return {data: {object: {sha: current[ref.replace('heads/', '')]}}};}
      },
      actions: {async listWorkflowRuns({workflow_id, branch, page}) {
        assert.equal(workflow_id, 'release-pipeline.yml');
        requests.push([branch, page]);
        return {data: {workflow_runs: proofs[branch].slice((page - 1) * 100, page * 100)}};
      }},
      repos: {async compareCommits({base, head}) {
        const history = [stableSha, testedSha, nextSha, unverifiedSha];
        const status = base === head ? 'identical' :
          !history.includes(base) || !history.includes(head) ? 'diverged' :
            history.indexOf(base) < history.indexOf(head) ? 'ahead' : 'behind';
        return {data: {status: compare ? compare(base, head) : status}};
      }}
    }},
    requests
  };
}

test('publication pins tested target tree and a previously verified companion despite newer failed/pending content', async () => {
  const env = environment({stable: unverifiedSha});
  assert.deepEqual(await resolveDocumentationRefs(env), {
    publish: true, stable_sha: stableSha, beta_sha: testedSha, companion_run_id: 42
  });
  assert.deepEqual(env.requests, [['beta', 1], ['main', 1]]);
  assert.equal(await publicationStillCurrent({...env, stableSha, betaSha: testedSha}), true);
  await assert.rejects(resolveDocumentationRefs(environment({tree: nextSha})), /does not match/);
  await assert.rejects(resolveDocumentationRefs(environment({branch: 'dev'})), /requires a tested/);
});

test('a newer successful target verification supersedes the old run but an unverified push does not', async () => {
  const proofs = {main: [release('main', stableSha)], beta: [release('beta', nextSha)]};
  assert.deepEqual(await resolveDocumentationRefs(environment({beta: nextSha, proofs})), {publish: false});
  const pending = environment({beta: nextSha});
  assert.equal((await resolveDocumentationRefs(pending)).beta_sha, testedSha);
  const stable = environment({branch: 'main', stable: testedSha,
    proofs: {main: [release('main', testedSha)], beta: [release('beta', testedSha)]}});
  assert.equal((await resolveDocumentationRefs(stable)).stable_sha, testedSha);
});

test('new verified companion evidence prevents an obsolete artifact from overwriting it', async () => {
  const proofs = {main: [release('main', nextSha)], beta: [release('beta', testedSha)]};
  const env = environment({stable: nextSha, proofs});
  assert.equal(await publicationStillCurrent({...env, stableSha, betaSha: testedSha}), false);
});

test('a rollback during the build prevents discarded source from being republished', async () => {
  const env = environment({compare: () => 'behind'});
  assert.equal(await publicationStillCurrent({...env, stableSha, betaSha: nextSha}), false);
});

test('companion requires same-repository successful release evidence still in branch history', async () => {
  const rejected = [
    {...release('main', stableSha), event: 'pull_request'},
    {...release('main', stableSha), head_repository: {full_name: 'fork/repo'}},
    {...release('main', stableSha), path: '.github/workflows/ci.yml'},
    {...release('main', stableSha), conclusion: 'failure'}
  ];
  for (const proofs of [{main: [], beta: [release('beta', testedSha)]},
    {main: rejected, beta: [release('beta', testedSha)]}]) {
    await assert.rejects(resolveDocumentationRefs(environment({proofs})), /No successful trusted.*main/);
  }
  const unrelated = environment({stable: unverifiedSha, compare: () => 'diverged'});
  await assert.rejects(latestVerifiedCommit(unrelated, 'main', unverifiedSha), /No successful trusted/);
  const failed = environment();
  failed.github.rest.actions.listWorkflowRuns = async () => {throw new Error('API unavailable');};
  await assert.rejects(resolveDocumentationRefs(failed), /API unavailable/);
});

test('verified companion search paginates instead of falling back to unverified HEAD', async () => {
  const invalid = {...release('main', nextSha), event: 'pull_request'};
  const proofs = {main: [...Array(100).fill(invalid), release('main', stableSha)], beta: [release('beta', testedSha)]};
  const env = environment({proofs, stable: unverifiedSha});
  assert.equal((await resolveDocumentationRefs(env)).stable_sha, stableSha);
  assert.ok(env.requests.some(([branch, page]) => branch === 'main' && page === 2));
});

test('new manual verification of an old ancestor cannot outrank a verified descendant', async () => {
  const oldManual = {...release('main', stableSha, 99), event: 'workflow_dispatch'};
  const newerCommit = release('main', nextSha, 41);
  for (const runs of [[oldManual, newerCommit], [newerCommit, oldManual]]) {
    const env = environment({stable: unverifiedSha,
      proofs: {main: runs, beta: [release('beta', testedSha)]}});
    assert.deepEqual(await latestVerifiedCommit(env, 'main', unverifiedSha), {sha: nextSha, runId: 41});
    assert.deepEqual(await resolveDocumentationRefs(env), {
      publish: true, stable_sha: nextSha, beta_sha: testedSha, companion_run_id: 41
    });
    assert.equal(await publicationStillCurrent({...env, stableSha, betaSha: testedSha}), false);
  }
  const target = environment({beta: unverifiedSha, proofs: {
    main: [release('main', stableSha)],
    beta: [{...release('beta', testedSha, 99), event: 'workflow_dispatch'}, release('beta', nextSha, 41)]
  }});
  assert.deepEqual(await resolveDocumentationRefs(target), {publish: false});
});

test('a candidate on an earlier page cannot hide a newer verified descendant on a later page', async () => {
  const env = environment({stable: unverifiedSha, proofs: {
    main: [...Array(100).fill(release('main', stableSha, 99)), release('main', nextSha, 41)],
    beta: [release('beta', testedSha)]
  }});
  assert.deepEqual(await latestVerifiedCommit(env, 'main', unverifiedSha), {sha: nextSha, runId: 41});
  assert.deepEqual(env.requests, [['main', 1], ['main', 2]]);
});

test('incomparable verified ancestors fail closed unless a verified descendant dominates both', async () => {
  const compare = (base, head) => {
    if (head === unverifiedSha || (head === testedSha && [stableSha, nextSha].includes(base))) return 'ahead';
    if (base === unverifiedSha || (base === testedSha && [stableSha, nextSha].includes(head))) return 'behind';
    return 'diverged';
  };
  const runs = [release('main', stableSha), release('main', nextSha)];
  const env = environment({stable: unverifiedSha, compare,
    proofs: {main: runs, beta: [release('beta', testedSha)]}});
  await assert.rejects(latestVerifiedCommit(env, 'main', unverifiedSha), /ambiguous ancestry/);
  runs.push(release('main', testedSha, 43));
  assert.deepEqual(await latestVerifiedCommit(env, 'main', unverifiedSha), {sha: testedSha, runId: 43});
});

test('bounded history fails closed rather than assuming an unseen descendant is unverified', async () => {
  const env = environment({stable: unverifiedSha, proofs: {
    main: Array(1000).fill(release('main', stableSha)), beta: [release('beta', testedSha)]
  }});
  await assert.rejects(latestVerifiedCommit(env, 'main', unverifiedSha), /bounded search.*incomplete evidence/);
  assert.equal(env.requests.length, 10);
});

test('verified current HEAD is provably maximal without searching older history', async () => {
  const env = environment({stable: unverifiedSha, proofs: {
    main: [release('main', stableSha), release('main', unverifiedSha, 44),
      ...Array(1000).fill(release('main', nextSha))], beta: [release('beta', testedSha)]
  }});
  assert.deepEqual(await latestVerifiedCommit(env, 'main', unverifiedSha), {sha: unverifiedSha, runId: 44});
  assert.deepEqual(env.requests, [['main', 1]]);
});
