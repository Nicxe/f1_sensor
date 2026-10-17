'use strict';

const {execFileSync} = require('node:child_process');

const START = '<!-- release-editorial:start -->';
const END = '<!-- release-editorial:end -->';
const RELEASE_LOOKUP_ATTEMPTS = 10;

function isPromotion(pr) {
  return (pr?.base?.ref === 'beta' && pr?.head?.ref === 'dev')
    || (pr?.base?.ref === 'main' && pr?.head?.ref === 'beta');
}

function editorialBlock(body) {
  const text = String(body || '');
  const start = text.indexOf(START);
  const end = text.indexOf(END, start + START.length);
  if (start < 0 || end < 0) return null;
  return text.slice(start + START.length, end);
}

function extractEditorial(body) {
  const block = editorialBlock(body);
  if (block === null) return null;
  return block.replace(/<!--[\s\S]*?-->/g, '').trim();
}

function replaceEditorial(notes, editorial) {
  const text = String(notes || '');
  const start = text.indexOf(START);
  const end = text.indexOf(END, start + START.length);
  if (start < 0 || end < 0) return {notes: text, replaced: false};
  const insertion = editorial ? `${editorial.trim()}\n\n` : '';
  return {
    notes: `${text.slice(0, start)}${insertion}${text.slice(end + END.length).replace(/^\n+/, '')}`,
    replaced: true
  };
}

function releaseTagAtHead({branch = process.env.GITHUB_REF_NAME, run = execFileSync} = {}) {
  const tags = String(run('git', ['tag', '--points-at', 'HEAD'], {encoding: 'utf8'}))
    .trim().split('\n').filter(tag => /^v\d+\.\d+\.\d+(?:-beta\.\d+)?$/.test(tag))
    .filter(tag => (branch === 'beta') === tag.includes('-beta.'));
  if (tags.length > 1) throw new Error('Ambiguous release tags on the tested commit');
  return tags[0] || '';
}

async function promotionPullRequest(github, context) {
  const data = await github.graphql(`
    query ReleaseEditorial($owner: String!, $repo: String!, $oid: GitObjectID!) {
      repository(owner: $owner, name: $repo) {
        object(oid: $oid) {
          ... on Commit {
            associatedPullRequests(first: 10) {
              nodes { number url body baseRefName headRefName merged mergeCommit { oid } }
            }
          }
        }
      }
    }`, {...context.repo, oid: context.sha});
  const pulls = data.repository.object?.associatedPullRequests.nodes || [];
  return pulls.find(pr => pr.merged
    && pr.mergeCommit?.oid === context.sha
    && isPromotion({
      base: {ref: pr.baseRefName}, head: {ref: pr.headRefName}
    }));
}

function isUntaggedRelease(release) {
  return /^untagged-[0-9a-f]+$/.test(String(release?.tag_name || ''));
}

function findRepairableDraft({releases, tag, branch, commitSha}) {
  return releases.find(release => release.draft
    && (release.tag_name === tag || isUntaggedRelease(release))
    && release.name === tag
    && (release.target_commitish === branch || release.target_commitish === commitSha)
    // GitHub can expose the draft before its uploaded assets are visible in
    // listReleases. Assets are deliberately not part of the identity check;
    // the tag and tested commit are the safety boundary for this repair.
  );
}

async function releaseTagMatchesHead({
  github,
  context,
  tag,
  wait = delay => new Promise(resolve => setTimeout(resolve, delay))
}) {
  for (let attempt = 1; attempt <= RELEASE_LOOKUP_ATTEMPTS; attempt += 1) {
    try {
      const commit = await github.rest.repos.getCommit({...context.repo, ref: tag});
      return commit.data.sha === context.sha;
    } catch (error) {
      if (error.status !== 404 || attempt === RELEASE_LOOKUP_ATTEMPTS) throw error;
      await wait(Math.min(1000 * 2 ** (attempt - 1), 8000));
    }
  }
  return false;
}

async function reconcileReleaseTag({
  github,
  context,
  core,
  tag,
  branch = context.ref.replace('refs/heads/', ''),
  assetNames = [],
  wait = delay => new Promise(resolve => setTimeout(resolve, delay))
}) {
  if (!(await releaseTagMatchesHead({github, context, tag, wait}))) {
    throw new Error(`${tag} does not point at the tested commit ${context.sha}.`);
  }

  let confirmedReleaseId;
  for (let attempt = 1; attempt <= RELEASE_LOOKUP_ATTEMPTS; attempt += 1) {
    let tagVisible = false;
    try {
      const release = (await github.rest.repos.getReleaseByTag({...context.repo, tag})).data;
      if (release.tag_name !== tag) throw new Error(`GitHub returned ${release.tag_name} for ${tag}.`);
      if (!release.draft) {
        core.info(`${tag} is already published and correctly associated with the release.`);
        return release;
      }
      if (confirmedReleaseId === release.id) {
        core.info(`${tag} is stably associated with draft release ${release.id}.`);
        return release;
      }
      confirmedReleaseId = release.id;
      tagVisible = true;
      core.info(`${tag} is visible by tag; confirming the association once more.`);
    } catch (error) {
      if (error.status !== 404) throw error;
      confirmedReleaseId = undefined;
    }

    if (!tagVisible) {
      const releases = await github.paginate(github.rest.repos.listReleases, {
        ...context.repo, per_page: 100
      });
      core.info(`Release lookup for ${tag}: ${releases.filter(release => release.draft).map(release => `${release.name || '(unnamed)'} [${release.tag_name}]`).join(', ') || 'no drafts visible'}.`);
      const repairable = findRepairableDraft({releases, tag, branch, commitSha: context.sha});
      if (repairable) {
        core.warning(`Asserting ${tag} on draft release ${repairable.id} (currently ${repairable.tag_name}).`);
        const repaired = (await github.rest.repos.updateRelease({
          ...context.repo,
          release_id: repairable.id,
          tag_name: tag,
          name: tag,
          target_commitish: branch,
          draft: true
        })).data;
        const byId = (await github.rest.repos.getRelease({
          ...context.repo, release_id: repairable.id
        })).data;
        if (repaired.tag_name !== tag || byId.tag_name !== tag) {
          throw new Error(`GitHub did not persist ${tag} on release ${repairable.id}.`);
        }
        core.info(`Draft release ${repairable.id} now reports ${tag} by release ID.`);
        // A draft release may remain unavailable through getReleaseByTag even
        // after GitHub has persisted the repair. The tag already points at the
        // tested commit, and the release ID has now confirmed the association;
        // do not turn that eventual-consistency window into a failed release.
        return byId;
      }
    }

    if (attempt === RELEASE_LOOKUP_ATTEMPTS) break;
    const delay = Math.min(1000 * 2 ** (attempt - 1), 8000);
    core.info(`${tag} is not visible yet; retrying release verification in ${delay}ms.`);
    await wait(delay);
  }
  throw new Error(`No stable correctly tagged release or safe matching draft found for ${tag}.`);
}

async function releaseByTag({github, context, core, tag, wait = delay => new Promise(resolve => setTimeout(resolve, delay))}) {
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    try {
      return (await github.rest.repos.getReleaseByTag({...context.repo, tag})).data;
    } catch (error) {
      if (error.status !== 404 || attempt === 6) throw error;
      const drafts = await github.paginate(github.rest.repos.listReleases, {
        ...context.repo, per_page: 100
      });
      const draft = drafts.find(release => release.draft && release.tag_name === tag);
      if (draft) {
        core.info(`${tag} is available as a draft release.`);
        return draft;
      }
      const delay = Math.min(1000 * 2 ** (attempt - 1), 8000);
      core.info(`${tag} is not visible yet; retrying the draft lookup in ${delay}ms.`);
      await wait(delay);
    }
  }
}

async function applyReleaseEditorial({github, context, core, getTag = releaseTagAtHead, wait}) {
  const tag = getTag({branch: context.ref.replace('refs/heads/', '')});
  if (!tag) {
    core.info('No release tag points at this commit; no draft editorial is needed.');
    return false;
  }
  const release = await releaseByTag({github, context, core, tag, wait});
  if (!release.draft) {
    core.info(`${tag} is already published; leaving its release notes unchanged.`);
    return false;
  }
  const promotion = await promotionPullRequest(github, context);
  const editorial = promotion ? extractEditorial(promotion.body) : '';
  if (promotion && editorial === null) {
    throw new Error(`Promotion PR #${promotion.number} has an invalid release editorial block.`);
  }
  const result = replaceEditorial(release.body, editorial || '');
  if (!result.replaced) {
    core.info(`${tag} has already been edited; leaving the draft notes unchanged.`);
    return false;
  }
  await github.rest.repos.updateRelease({...context.repo, release_id: release.id, body: result.notes});
  core.info(editorial
    ? `Added the editorial text from promotion PR #${promotion.number} to ${tag}.`
    : `Removed the unused editorial placeholder from ${tag}.`);
  return true;
}

module.exports = {
  START, END, isPromotion, editorialBlock, extractEditorial, replaceEditorial,
  releaseTagAtHead, promotionPullRequest, releaseByTag, applyReleaseEditorial,
  RELEASE_LOOKUP_ATTEMPTS, isUntaggedRelease, findRepairableDraft,
  releaseTagMatchesHead, reconcileReleaseTag
};
