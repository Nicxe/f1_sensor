'use strict';
const {enable} = require('./auto-merge.cjs');

async function syncOne(environment, source, sha, target) {
  const {github, context, core} = environment;
  const repo = context.repo;
  const base = (await github.rest.git.getRef({...repo, ref:`heads/${target}`})).data.object.sha;
  const comparison = (await github.rest.repos.compareCommits({...repo, base, head:sha})).data;
  if (['identical', 'behind'].includes(comparison.status)) return 'contained';
  // A new target head gets a new snapshot; strict branch rules never require
  // rewriting a snapshot or choosing a conflict resolution automatically.
  const prefix = `sync/${source}-to-${target}/`;
  const branch = `${prefix}${sha.slice(0,12)}-${base.slice(0,12)}`;
  try { await github.rest.git.createRef({...repo, ref:`refs/heads/${branch}`, sha}); }
  catch (error) { if (error.status !== 422) throw error; }
  const snapshot = (await github.rest.repos.getCommit({...repo, ref:branch})).data;
  if (snapshot.sha !== sha && (snapshot.parents?.length !== 2
      || snapshot.parents[0].sha !== sha || snapshot.parents[1].sha !== base)) {
    throw new Error('Synchronization snapshot changed; refusing to overwrite it.');
  }
  if (snapshot.sha === sha && comparison.status === 'diverged') {
    // GitHub returns 409 for conflicts, leaving both protected branches intact.
    await github.rest.repos.merge({...repo, base:branch, head:base,
      commit_message:`chore: Preserve ${target} changes while synchronizing ${source}`});
  } else if (snapshot.sha === sha) {
    // Even when the source already contains the target, give each PR its own
    // head. GitHub associates required checks with commits, not PR numbers.
    const commit = (await github.rest.git.createCommit({...repo,
      message:`chore: Verify ${source} synchronization into ${target}`,
      tree:snapshot.commit.tree.sha, parents:[sha, base]})).data;
    await github.rest.git.updateRef({...repo, ref:`heads/${branch}`, sha:commit.sha, force:false});
  }
  const pulls = await github.paginate(github.rest.pulls.list,
    {...repo, state:'open', base:target, head:`${repo.owner}:${branch}`, per_page:100});
  const pr = pulls[0] || (await github.rest.pulls.create({...repo, base:target, head:branch,
    title:`chore: Synchronize ${source} into ${target}`,
    body:`Preserve the ${source} and ${target} histories. This snapshot includes the exact target head before verification. Automatic merging requires CI; conflicts require normal manual resolution.`})).data;
  if (pr.user.login !== 'github-actions[bot]') throw new Error('Unexpected synchronization PR author.');
  if (pr.auto_merge) return 'queued';
  const head = pr.head.sha;
  if (pr.base.sha !== base) throw new Error('Target changed; a fresh synchronization snapshot is required.');
  // Fence off unrelated green checks on the same commit before enabling merge.
  const externalId = `f1-pr:${pr.number}:${base}:${head}`;
  const checks = await github.paginate(github.rest.checks.listForRef,
    {...repo, ref:head, check_name:'CI required', per_page:100});
  const existing = checks.find(check => check.external_id === externalId && check.app?.id === 15368);
  const pending = {...repo, name:'CI required', status:'in_progress',
    output:{title:'Verifying synchronization',summary:'Checking the exact source and target snapshot before automatic merging.'}};
  if (existing) await github.rest.checks.update({...pending, check_run_id:existing.id});
  else await github.rest.checks.create({...pending, head_sha:head, external_id:externalId});
  await github.rest.actions.createWorkflowDispatch({...repo, workflow_id:'ci.yml', ref:target,
    inputs:{release:false, pull_request:String(pr.number)}});
  await enable(environment, pr);
  // Retire only our older pending snapshots, after the replacement is queued.
  const obsolete = await github.paginate(github.rest.pulls.list, {...repo, state:'open', base:target, per_page:100});
  for (const old of obsolete) {
    if (old.number !== pr.number && old.user.login === 'github-actions[bot]'
        && old.head.repo?.full_name === pr.head.repo.full_name && old.head.ref.startsWith(prefix)) {
      await github.rest.pulls.update({...repo, pull_number:old.number, state:'closed'});
    }
  }
  core.info(`Queued synchronization PR #${pr.number}.`);
  return 'pull-request';
}

async function synchronize(environment) {
  const {github, context} = environment;
  const release = context.payload.release;
  let source = 'main';
  let targets = ['beta', 'content', 'dev'];
  let sha;
  if (release) {
    if (release.draft) return;
    source = release.prerelease ? 'beta' : 'main';
    if (release.target_commitish !== source) throw new Error('Unexpected release target; synchronization stopped.');
    sha = (await github.rest.repos.getCommit({...context.repo, ref:release.tag_name})).data.sha;
    if (release.prerelease) targets = ['dev'];
  } else {
    sha = (await github.rest.git.getRef({...context.repo, ref:'heads/main'})).data.object.sha;
  }
  const failures = [];
  for (const target of targets) {
    try { await syncOne(environment, source, sha, target); }
    catch (error) { failures.push(`${target}: ${error.message}`); }
  }
  if (failures.length) throw new Error(failures.join('\n'));
}
module.exports = {syncOne, synchronize};
