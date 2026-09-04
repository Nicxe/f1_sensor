'use strict';
const {spawnSync} = require('node:child_process');
const {upsertComment, ensureLabel, removeLabel} = require('./issue-automation.cjs');

async function routing({github, context}) {
  const pr = (await github.rest.pulls.get({...context.repo, pull_number:context.payload.pull_request.number})).data;
  const files = await github.paginate(github.rest.pulls.listFiles, {...context.repo, pull_number:pr.number, per_page:100});
  const check = spawnSync('python3', ['-c', 'import json,sys; from scripts.ci_policy import branch_error; d=json.load(sys.stdin); print(branch_error(d["event"],d["files"]))'], {input:JSON.stringify({event:{pull_request:pr}, files:files.flatMap(f => f.previous_filename ? [f.filename,f.previous_filename] : [f.filename])}), encoding:'utf8'});
  if (check.status !== 0) throw new Error(check.stderr);
  const error = check.stdout.trim();
  await upsertComment(github, {...context.repo, issue_number:pr.number}, '<!-- f1-pr-routing -->', error
    ? `Thanks for your contribution! ${error}\n\nPlease change this PR's base branch using **Edit** next to the title. You do not need to close and recreate the PR. See [CONTRIBUTING.md](https://github.com/${context.repo.owner}/${context.repo.repo}/blob/main/CONTRIBUTING.md).`
    : 'This PR now targets the correct branch.', () => false, !error);
}

async function conflicts({github, context, core}) {
  const candidates = context.payload.pull_request ? [context.payload.pull_request] : await github.paginate(github.rest.pulls.list, {...context.repo, state:'open', base:context.ref.replace('refs/heads/',''), per_page:100});
  for (const candidate of candidates) {
    let pr;
    for (let attempt=0; attempt<4; attempt++) {
      pr = (await github.rest.pulls.get({...context.repo, pull_number:candidate.number})).data;
      if (pr.mergeable !== null && pr.mergeable_state !== 'unknown') break;
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    if (pr.mergeable === null || pr.mergeable_state === 'unknown') {
      core.warning(`Mergeability for #${pr.number} is still unknown; leaving labels unchanged.`);
      continue;
    }
    const key = {...context.repo, issue_number:pr.number};
    const labeled = pr.labels.some(l => l.name === 'has-conflicts');
    if (pr.mergeable_state === 'dirty') {
      await ensureLabel(github, context.repo, 'has-conflicts', 'd93f0b');
      if (!labeled) await github.rest.issues.addLabels({...key, labels:['has-conflicts']});
      await upsertComment(github, key, '<!-- f1-conflicts -->', 'This PR has merge conflicts with its target branch. Merge or rebase the target branch locally, resolve the conflicts, and push the updated branch.');
    } else if (labeled) {
      await removeLabel(github, key, 'has-conflicts');
      await upsertComment(github, key, '<!-- f1-conflicts -->', 'The merge conflicts have been resolved. Thank you!');
    }
  }
}
module.exports = {routing, conflicts};
