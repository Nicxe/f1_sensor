'use strict';

async function verifyDependabot({github, context}, pr) {
  if (pr.user.login !== 'dependabot[bot]' || pr.head.repo?.full_name !== pr.base.repo.full_name) {
    throw new Error('Expected an own-repository Dependabot PR.');
  }
  const commits = await github.paginate(github.rest.pulls.listCommits, {...context.repo, pull_number:pr.number, per_page:100});
  if (!commits.length) throw new Error('Dependabot PR has no commits.');
  for (const commit of commits) {
    if (!commit.commit.verification?.verified) throw new Error('Unverified dependency commit.');
    if (commit.author?.login === 'dependabot[bot]') continue;
    // Our update-branch merges preserve signed dependency commits and only add
    // already trusted target history. No other author or extra code is allowed.
    if (commit.author?.login !== 'github-actions[bot]' || commit.parents?.length !== 2) {
      throw new Error('Unexpected dependency commit author.');
    }
    const comparison = (await github.rest.repos.compareCommits({...context.repo,
      base:commit.parents[1].sha, head:pr.base.sha})).data;
    if (!['identical','ahead'].includes(comparison.status)) throw new Error('Dependency merge includes unrelated history.');
  }
}

async function refresh({github, context}, pr) {
  const current = (await github.rest.pulls.get({...context.repo, pull_number:pr.number})).data;
  if (current.state !== 'open' || current.mergeable_state !== 'behind') return;
  await github.rest.pulls.updateBranch({...context.repo, pull_number:current.number, expected_head_sha:current.head.sha});
  // update-branch is asynchronous. Dispatch only after GitHub exposes the new
  // head; the verification workflow also checks its merge parents atomically.
  for (let attempt=0; attempt<10; attempt++) {
    const updated = (await github.rest.pulls.get({...context.repo, pull_number:current.number})).data;
    if (updated.head.sha !== current.head.sha) {
      await github.rest.actions.createWorkflowDispatch({...context.repo, workflow_id:'ci.yml', ref:updated.base.ref,
        inputs:{release:false, pull_request:String(updated.number)}});
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error('Branch refresh is still pending; retry dependency automation.');
}

async function enable({github, context}, pr) {
  const rules = await github.paginate('GET /repos/{owner}/{repo}/rules/branches/{branch}',
    {...context.repo, branch: pr.base.ref});
  const protectedPR = rules.some(rule => rule.type === 'pull_request');
  const required = rules.some(rule => rule.type === 'required_status_checks'
    && rule.parameters.strict_required_status_checks_policy
    && rule.parameters.required_status_checks.some(check =>
      check.context === 'CI required' && check.integration_id === 15368));
  if (!protectedPR || !required) throw new Error('Automatic merge requires strict, GitHub Actions-bound CI required and PR protection.');
  const current = (await github.rest.pulls.get({...context.repo, pull_number: pr.number})).data;
  if (current.state !== 'open' || current.draft || current.head.sha !== pr.head.sha
      || current.base.sha !== pr.base.sha || current.base.ref !== pr.base.ref) {
    throw new Error('PR changed before automatic merge could be enabled.');
  }
  if (current.auto_merge) return;
  if (current.mergeable_state === 'clean') {
    const result = (await github.rest.pulls.merge({...context.repo, pull_number:current.number,
      sha:current.head.sha, merge_method:'merge'})).data;
    if (!result.merged) throw new Error('GitHub did not merge the verified PR.');
    return;
  }
  await github.graphql(`mutation($id:ID!, $head:GitObjectID!) {
    enablePullRequestAutoMerge(input:{pullRequestId:$id, expectedHeadOid:$head, mergeMethod:MERGE}) {
      pullRequest { number }
    }
  }`, {id: current.node_id, head: current.head.sha});
}

function eligible(base, metadata) {
  if (base === 'main') return metadata.alert === 'OPEN' && /^GHSA-[a-z0-9-]+$/.test(metadata.ghsa || '');
  return base === 'dev' && ['version-update:semver-patch', 'version-update:semver-minor'].includes(metadata.update);
}

module.exports = {enable, eligible, verifyDependabot, refresh};
