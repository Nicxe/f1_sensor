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

// Only stable numeric versions in the advisory's patched major are eligible.
// Ambiguous versions and cross-major security upgrades need manual review.
function compareVersion(value, fixed) {
  const parse = version => /^\d+\.\d+\.\d+$/.test(version || '') ? version.split('.').map(Number) : null;
  const a = parse(value), b = parse(fixed);
  if (!a || !b || a[0] !== b[0]) return null;
  for (let i=0; i<3; i++) if (a[i] !== b[i]) return Math.sign(a[i]-b[i]);
  return 0;
}

async function securityAdvisories({github, context}, pr, dependencies) {
  // fetch-metadata reads only the first 100 historical alerts and assumes
  // vulnerableRequirements starts with '= '. Neither holds for this repo.
  const alerts = await github.paginate('GET /repos/{owner}/{repo}/dependabot/alerts',
    {...context.repo, state:'open', per_page:100});
  const files = await github.paginate('GET /repos/{owner}/{repo}/pulls/{pull_number}/files',
    {...context.repo, pull_number:pr.number, per_page:100});
  const changed = new Set(files.map(file => file.filename));
  const contents = new Map();
  async function read(path, ref) {
    const key = `${ref}:${path}`;
    if (!contents.has(key)) {
      const {data} = await github.rest.repos.getContent({...context.repo, path, ref});
      if (data.encoding !== 'base64' || typeof data.content !== 'string') throw new Error('Cannot verify dependency manifest.');
      contents.set(key, Buffer.from(data.content, 'base64').toString('utf8'));
    }
    return contents.get(key);
  }
  const matches = new Set();
  for (const alert of alerts) {
    const {package:pkg, manifest_path:path} = alert.dependency;
    const fixed = alert.security_vulnerability.first_patched_version?.identifier;
    if (alert.state !== 'open' || !fixed || !changed.has(path)) continue;
    const metadata = dependencies.find(dependency => {
      const directory = (dependency.directory || '/').replace(/^\/+|\/+$/g, '');
      const manifestDirectory = path.includes('/') ? path.slice(0,path.lastIndexOf('/')) : '';
      const ecosystem = {npm_and_yarn:'npm',pip:'pip'}[dependency.packageEcosystem];
      return dependency.dependencyName === pkg.name && ecosystem === pkg.ecosystem && directory === manifestDirectory;
    });
    if (!metadata) continue;
    let before, after;
    if (pkg.ecosystem === 'npm' && path.endsWith('package-lock.json')) {
      const versions = content => Object.entries(JSON.parse(content).packages || {})
        .filter(([location]) => location === `node_modules/${pkg.name}` || location.endsWith(`/node_modules/${pkg.name}`))
        .map(([,entry]) => entry.version);
      before = versions(await read(path,pr.base.sha));
      after = versions(await read(path,pr.head.sha));
    } else if (pkg.ecosystem === 'pip' && path.endsWith('.txt')) {
      const versions = content => content.split(/\r?\n/).map(line => line.trim().match(/^([a-zA-Z0-9_.-]+)==(\d+\.\d+\.\d+)\s*(?:#.*)?$/))
        .filter(match => match && match[1].toLowerCase().replace(/[-_.]+/g,'-') === pkg.name.toLowerCase().replace(/[-_.]+/g,'-'))
        .map(match => match[2]);
      before = versions(await read(path,pr.base.sha));
      after = versions(await read(path,pr.head.sha));
    } else continue;
    if (before.some(version => compareVersion(version,fixed) === -1) && after.length &&
        after.every(version => [0,1].includes(compareVersion(version,fixed))) &&
        /^GHSA-[a-z0-9-]+$/.test(alert.security_advisory.ghsa_id)) {
      matches.add(alert.security_advisory.ghsa_id);
    }
  }
  return [...matches];
}

async function queueDependabot(environment, verifiedPR) {
  const {github, context} = environment;
  // Reopened dependency events can retain an old base SHA. Refresh the base,
  // while requiring the exact dependency head that was just authenticated.
  const current = (await github.rest.pulls.get({...context.repo, pull_number:verifiedPR.number})).data;
  if (current.head.sha !== verifiedPR.head.sha || current.base.ref !== verifiedPR.base.ref) {
    throw new Error('Dependency PR changed after verification.');
  }
  await enable(environment, current);
  await refresh(environment, current);
}

module.exports = {enable, eligible, securityAdvisories, verifyDependabot, refresh, queueDependabot};
