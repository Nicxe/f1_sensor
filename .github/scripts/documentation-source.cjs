'use strict';

const SHA = /^[0-9a-f]{40}$/;

function matchesReleaseSource(run, repository, branch, sha) {
  return ['push', 'workflow_dispatch'].includes(run.event) &&
    run.path === '.github/workflows/release-pipeline.yml' &&
    run.repository?.full_name === repository && run.head_repository?.full_name === repository &&
    ['main', 'beta'].includes(run.head_branch) && SHA.test(run.head_sha || '') &&
    (!branch || run.head_branch === branch) && (!sha || run.head_sha === sha);
}

function eligibleReleaseRun(run, repository) {
  return run.status === 'completed' && run.conclusion === 'success' &&
    matchesReleaseSource(run, repository);
}

async function resolvePublicationSource({github, context, core, runId, expectedSha, targetBranch}) {
  if (!Number.isSafeInteger(Number(runId)) || Number(runId) < 1) throw new Error('Invalid source workflow run.');
  // Re-fetch authoritative metadata; never trust a displayed check name,
  // contributor artifacts, or a success belonging to another commit/branch.
  const run = (await github.rest.actions.getWorkflowRun({...context.repo, run_id: Number(runId)})).data;
  if (run.id !== Number(runId)) throw new Error('Invalid source workflow run identity.');
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  if (!eligibleReleaseRun(run, repository) || !matchesReleaseSource(run, repository, targetBranch, expectedSha)) {
    core.info('This run is not a successful same-repository release verification; no documentation publication is authorized.');
    return null;
  }
  const commit = (await github.rest.git.getCommit({...context.repo, commit_sha: run.head_sha})).data;
  if (!SHA.test(commit.tree?.sha || '')) throw new Error('Source verification has no valid Git tree.');
  return {tested_sha: run.head_sha, tested_tree: commit.tree.sha, target_branch: run.head_branch, source_run_id: run.id};
}

async function waitForPublicationSource({github, context, core,
  sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)),
  now = Date.now, timeoutMs = 60 * 60 * 1000, pollMs = 30 * 1000}) {
  const branch = /^refs\/heads\/(main|beta)$/.exec(context.ref || '')?.[1];
  if (!['push', 'workflow_dispatch'].includes(context.eventName) || !branch ||
      !SHA.test(context.sha || '') || !Number.isFinite(timeoutMs) || timeoutMs <= 0 ||
      !Number.isFinite(pollMs) || pollMs <= 0) {
    throw new Error('Documentation publication requires a trusted main/beta push or dispatch and immutable commit.');
  }
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    const current = (await github.rest.git.getRef({...context.repo, ref: `heads/${branch}`})).data;
    if (!SHA.test(current.object?.sha || '')) throw new Error('Invalid current documentation branch commit.');
    if (current.object.sha !== context.sha) {
      core.info('The branch advanced or was rolled back; its current push owns documentation publication.');
      return null;
    }
    const runs = [];
    for (let page = 1; page <= 10; page++) {
      const data = (await github.rest.actions.listWorkflowRuns({...context.repo,
        workflow_id: 'release-pipeline.yml', head_sha: context.sha, branch, per_page: 100, page})).data;
      if (!Array.isArray(data.workflow_runs)) throw new Error('Incomplete release verification evidence.');
      runs.push(...data.workflow_runs.filter(run => matchesReleaseSource(run, repository, branch, context.sha)));
      if (data.workflow_runs.length < 100) break;
      if (page === 10) throw new Error('Release verification evidence exceeds the bounded search.');
    }
    if (runs.some(run => !Number.isSafeInteger(run.run_number) || run.run_number < 1)) {
      throw new Error('Invalid release verification run sequence.');
    }
    // run_number increases for each new execution of this workflow. Re-fetch
    // the newest matching run
    // so an older success cannot hide a newer queued, restarted or failed run.
    const candidate = runs.sort((left, right) => right.run_number - left.run_number)[0];
    if (candidate) {
      if (!Number.isSafeInteger(candidate.id) || candidate.id < 1) throw new Error('Invalid release verification run identity.');
      const run = (await github.rest.actions.getWorkflowRun({...context.repo, run_id: candidate.id})).data;
      if (!matchesReleaseSource(run, repository, branch, context.sha) || run.id !== candidate.id) {
        throw new Error('Release verification source identity changed.');
      }
      if (run.status === 'completed') {
        if (run.conclusion !== 'success') {
          core.info(`Release verification ${run.id} completed with ${run.conclusion}; no documentation is published.`);
          return null;
        }
        // Resolve and validate the authoritative success again before exposing
        // its immutable tree to jobs with publication permissions.
        return resolvePublicationSource({github, context, core, runId: run.id,
          expectedSha: context.sha, targetBranch: branch});
      }
      if (!['queued', 'in_progress', 'waiting', 'requested', 'pending'].includes(run.status)) {
        throw new Error('Invalid release verification status.');
      }
    }
    core.info(`Waiting for release verification of ${branch} at ${context.sha}.`);
    const remaining = deadline - now();
    if (remaining > 0) await sleep(Math.min(pollMs, remaining));
  }
  throw new Error('Timed out waiting for exact-commit release verification; retry Documentation publication after verification completes.');
}

module.exports = {eligibleReleaseRun, resolvePublicationSource, waitForPublicationSource};
