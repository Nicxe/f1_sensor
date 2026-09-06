'use strict';

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

module.exports = {enable, eligible};
