'use strict';

const {eligibleReleaseRun} = require('./documentation-source.cjs');
const SHA = /^[0-9a-f]{40}$/;

async function currentChannelRefs({github, context}) {
  const refs = await Promise.all(['main', 'beta'].map(async branch => {
    const ref = (await github.rest.git.getRef({...context.repo, ref: `heads/${branch}`})).data;
    if (!SHA.test(ref.object.sha)) throw new Error(`Invalid documentation commit for ${branch}.`);
    return [branch, ref.object.sha];
  }));
  return Object.fromEntries(refs);
}

async function isAncestor({github, context}, base, head) {
  if (base === head) return true;
  const comparison = (await github.rest.repos.compareCommits({...context.repo, base, head})).data;
  if (!['ahead', 'behind', 'identical', 'diverged'].includes(comparison.status)) {
    throw new Error('Could not establish documentation source ancestry.');
  }
  return ['ahead', 'identical'].includes(comparison.status);
}

async function latestVerifiedCommit(environment, branch, currentSha) {
  const {github, context} = environment;
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  const seen = new Set();
  const ancestry = new Map();
  let frontier = [];
  const ancestor = async (base, head) => {
    const key = `${base}:${head}`;
    if (!ancestry.has(key)) ancestry.set(key, await isAncestor(environment, base, head));
    return ancestry.get(key);
  };
  for (let page = 1; page <= 10; page++) {
    const response = (await github.rest.actions.listWorkflowRuns({...context.repo,
      workflow_id: 'release-pipeline.yml', branch, status: 'success', per_page: 100, page})).data;
    for (const run of response.workflow_runs) {
      if (!eligibleReleaseRun(run, repository) || run.head_branch !== branch || seen.has(run.head_sha)) continue;
      seen.add(run.head_sha);
      if (!await ancestor(run.head_sha, currentSha)) continue;
      const candidate = {sha: run.head_sha, runId: run.id};
      // The current branch tip dominates every eligible ancestor, even when an
      // older commit has a more recently created manual verification run.
      if (run.head_sha === currentSha) return candidate;
      const remaining = [];
      let dominated = false;
      for (const previous of frontier) {
        if (await ancestor(candidate.sha, previous.sha)) {
          dominated = true;
          break;
        }
        if (!await ancestor(previous.sha, candidate.sha)) remaining.push(previous);
      }
      if (!dominated) frontier = [...remaining, candidate];
    }
    if (response.workflow_runs.length < 100) {
      if (frontier.length > 1) {
        throw new Error(`Successful release verifications on ${branch} have ambiguous ancestry; documentation publication cannot choose a source safely.`);
      }
      if (frontier.length === 1) return frontier[0];
      throw new Error(`No successful trusted release verification remains on ${branch}; documentation publication cannot use unverified content.`);
    }
  }
  throw new Error(`Successful release verification history on ${branch} exceeds the bounded search; documentation publication cannot use incomplete evidence.`);
}

async function resolveDocumentationRefs(environment) {
  const {github, context, core, testedSha, testedTree, targetBranch: branch} = environment;
  if (!['main', 'beta'].includes(branch) || !SHA.test(testedSha) || !SHA.test(testedTree)) {
    throw new Error('Documentation publication requires a tested main/beta commit and tree.');
  }
  const commit = (await github.rest.git.getCommit({...context.repo, commit_sha: testedSha})).data;
  if (commit.tree.sha !== testedTree) throw new Error('Tested documentation tree does not match its commit.');
  const current = await currentChannelRefs(environment);
  if (!await isAncestor(environment, testedSha, current[branch])) {
    core.info('The tested source no longer belongs to this release branch; skipping publication.');
    return {publish: false};
  }
  const latestTarget = await latestVerifiedCommit(environment, branch, current[branch]);
  if (latestTarget.sha !== testedSha && !await isAncestor(environment, latestTarget.sha, testedSha)) {
    core.info('A newer verified source owns documentation publication; skipping this superseded run.');
    return {publish: false};
  }
  const companionBranch = branch === 'main' ? 'beta' : 'main';
  const companion = await latestVerifiedCommit(environment, companionBranch, current[companionBranch]);
  return {publish: true,
    stable_sha: branch === 'main' ? testedSha : companion.sha,
    beta_sha: branch === 'beta' ? testedSha : companion.sha,
    companion_run_id: companion.runId};
}

async function publicationStillCurrent(environment) {
  const {core, stableSha, betaSha} = environment;
  const current = await currentChannelRefs(environment);
  for (const [branch, expected] of [['main', stableSha], ['beta', betaSha]]) {
    if (!await isAncestor(environment, expected, current[branch])) {
      core.info(`The pinned source on ${branch} was removed from branch history; skipping this obsolete artifact.`);
      return false;
    }
    const latest = await latestVerifiedCommit(environment, branch, current[branch]);
    if (latest.sha !== expected && !await isAncestor(environment, latest.sha, expected)) {
      core.info(`A newer verified source on ${branch} superseded this artifact; its run will publish it.`);
      return false;
    }
  }
  return true;
}

module.exports = {resolveDocumentationRefs, publicationStillCurrent, latestVerifiedCommit};
