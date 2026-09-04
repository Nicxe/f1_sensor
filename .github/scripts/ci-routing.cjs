'use strict';
// Only an actual verification run for an unchanged same-repository PR can own CI.
function matchingPull(pr, repository, branch, sha) {
  return pr.state === 'open' && pr.head.repo?.full_name === repository &&
    pr.head.ref === branch && pr.head.sha === sha &&
    ((branch === 'dev' && pr.base.ref === 'beta') ||
     (branch === 'content' && pr.base.ref === 'main'));
}
function matchingRun(run, pr, sha) {
  return run.event === 'pull_request' && run.path === '.github/workflows/ci.yml' &&
    run.head_sha === sha && run.pull_requests?.some(p => p.number === pr.number) &&
    ['queued','in_progress','completed'].includes(run.status) &&
    (run.status !== 'completed' || run.conclusion === 'success');
}
async function route({github, context, core}) {
  core.setOutput('run_checks', 'true');
  try {
    const branch = context.ref.replace('refs/heads/', '');
    const repository = `${context.repo.owner}/${context.repo.repo}`;
    const pulls = await github.paginate(github.rest.pulls.list, {...context.repo,
      state:'open', head:`${context.repo.owner}:${branch}`, per_page:100});
    const pr = pulls.find(p => matchingPull(p, repository, branch, context.sha));
    if (!pr) return;
    const runs = (await github.rest.actions.listWorkflowRunsForRepo({...context.repo,
      head_sha:context.sha, event:'pull_request', per_page:100})).data.workflow_runs;
    const run = runs.find(r => matchingRun(r, pr, context.sha));
    if (run) {
      core.setOutput('run_checks', 'false');
      await core.summary.addRaw(`PR #${pr.number} verifies this exact head. ` +
        `[Follow PR verification](${run.html_url}).`).write();
    }
  } catch (error) {
    core.warning(`PR verification could not be confirmed; running development checks (${error.status || 'API error'}).`);
  }
}
module.exports = {matchingPull, matchingRun, route};
