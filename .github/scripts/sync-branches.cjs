'use strict';

async function syncOne({github, context, core}, source, sha, target) {
  const repo = context.repo;
  const comparison = (await github.rest.repos.compareCommits({...repo, base:target, head:sha})).data;
  if (['identical','behind'].includes(comparison.status)) return 'contained';
  if (comparison.status === 'ahead') {
    let updated = false;
    try {
      await github.rest.git.updateRef({...repo, ref:`heads/${target}`, sha, force:false});
      updated = true;
    } catch (error) {
      if (![403,422].includes(error.status)) throw error;
      core.info(`Protected ${target}; using a pull request.`);
    }
    if (updated) {
      await github.rest.actions.createWorkflowDispatch({...repo, workflow_id:'ci.yml', ref:target, inputs:{release:false}});
      return 'fast-forward';
    }
  }
  const branch = `sync/${source}-to-${target}/${sha.slice(0,12)}`;
  try { await github.rest.git.createRef({...repo, ref:`refs/heads/${branch}`, sha}); }
  catch (error) {
    if (error.status !== 422) throw error;
    const existing = (await github.rest.git.getRef({...repo, ref:`heads/${branch}`})).data;
    if (existing.object.sha !== sha) throw new Error('Synchronization snapshot changed; refusing to overwrite it.');
  }
  const pulls = await github.paginate(github.rest.pulls.list, {...repo, state:'open', base:target, head:`${repo.owner}:${branch}`, per_page:100});
  const pr = pulls[0] || (await github.rest.pulls.create({...repo, base:target, head:branch,
    title:`chore: Synchronize ${source} into ${target}`,
    body:`Preserve the published ${source} history in ${target} without replacing commits. This synchronization uses an immutable source snapshot and must pass CI before merging. Conflicts require a normal merge resolution; no side is selected automatically.`})).data;
  // GITHUB_TOKEN pushes do not reliably start CI. Run the merge ref explicitly,
  // attaching the required check to this immutable PR head.
  await github.rest.actions.createWorkflowDispatch({...repo, workflow_id:'ci.yml', ref:branch, inputs:{release:false, pull_request:String(pr.number)}});
  return 'pull-request';
}

async function synchronize(environment) {
  const {github, context} = environment;
  const release = context.payload.release;
  let source, sha, targets;
  if (release) {
    if (release.draft) return;
    source = release.prerelease ? 'beta' : 'main';
    if (release.target_commitish !== source) throw new Error('Unexpected release target; synchronization stopped.');
    sha = (await github.rest.repos.getCommit({...context.repo, ref:release.tag_name})).data.sha;
    targets = release.prerelease ? ['dev'] : ['beta','content','dev'];
  } else {
    source = 'main';
    sha = context.payload.after;
    targets = ['content','dev'];
  }
  const failures = [];
  for (const target of targets) {
    try { await syncOne(environment, source, sha, target); }
    catch (error) { failures.push(`${target}: ${error.message}`); }
  }
  if (failures.length) throw new Error(failures.join('\n'));
}
module.exports = {syncOne, synchronize};
