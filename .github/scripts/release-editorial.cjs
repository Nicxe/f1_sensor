'use strict';

const {execFileSync} = require('node:child_process');

const START = '<!-- release-editorial:start -->';
const END = '<!-- release-editorial:end -->';
const RELEASE_LOOKUP_ATTEMPTS = 10;
const RELEASE_TAG_PATTERN = /^v\d+\.\d+\.\d+(?:-beta\.\d+)?$/;

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
    .trim().split('\n').filter(tag => RELEASE_TAG_PATTERN.test(tag))
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
  const matches = releases.filter(release => release.draft
    && (release.tag_name === tag || (isUntaggedRelease(release) && release.name === tag))
    && (release.target_commitish === branch || release.target_commitish === commitSha)
    // GitHub can expose the draft before its uploaded assets are visible in
    // listReleases. Assets are deliberately not part of the identity check;
    // the tag and tested commit are the safety boundary for this repair.
  );
  if (matches.length > 1) throw new Error(`Multiple matching drafts found for ${tag}.`);
  return matches[0];
}

function missingReleaseAssets(release, assetNames) {
  return assetNames.filter(name => !release.assets?.some(asset =>
    asset.name === name && asset.state === 'uploaded'));
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

  for (let attempt = 1; attempt <= RELEASE_LOOKUP_ATTEMPTS; attempt += 1) {
    // Draft URLs normally contain untagged-*. The tag endpoint is documented
    // for published releases; its 404 is not evidence of a broken draft.
    const releases = await github.paginate(github.rest.repos.listReleases, {
      ...context.repo, per_page: 100
    });
    const draft = findRepairableDraft({releases, tag, branch, commitSha: context.sha});
    let release;
    if (draft) {
      release = (await github.rest.repos.getRelease({...context.repo, release_id: draft.id})).data;
      if (release.tag_name !== tag) {
        if (!release.draft || !isUntaggedRelease(release) || release.name !== tag) {
          throw new Error(`Release ${draft.id} changed while preparing ${tag}.`);
        }
        core.warning(`Repairing the tag on draft release ${release.id} to ${tag}.`);
        // Metadata repair must never publish or unpublish a release, including
        // when the maintainer publishes it concurrently in the web interface.
        await github.rest.repos.updateRelease({
          ...context.repo, release_id: release.id, tag_name: tag
        });
        release = (await github.rest.repos.getRelease({...context.repo, release_id: draft.id})).data;
      }
    } else {
      try {
        release = (await github.rest.repos.getReleaseByTag({...context.repo, tag})).data;
      } catch (error) {
        if (error.status !== 404) throw error;
      }
    }
    if (release) {
      if (release.tag_name !== tag) throw new Error(`GitHub returned ${release.tag_name} for ${tag}.`);
      const missing = missingReleaseAssets(release, assetNames);
      if (!missing.length) {
        core.info(`${tag} is verified on release ${release.id}; ${release.draft ? 'publication remains manual' : 'already published'}.`);
        return release;
      }
      core.info(`Waiting for release assets: ${missing.join(', ')}.`);
    }

    if (attempt === RELEASE_LOOKUP_ATTEMPTS) break;
    const delay = Math.min(1000 * 2 ** (attempt - 1), 8000);
    core.info(`${tag} is not visible yet; retrying release verification in ${delay}ms.`);
    await wait(delay);
  }
  throw new Error(`No correctly tagged release with all required assets found for ${tag}.`);
}

async function releaseByTag({github, context, core, tag, wait = delay => new Promise(resolve => setTimeout(resolve, delay))}) {
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    const releases = await github.paginate(github.rest.repos.listReleases, {
      ...context.repo, per_page: 100
    });
    const drafts = releases.filter(release => release.draft && release.tag_name === tag);
    if (drafts.length > 1) throw new Error(`Multiple matching drafts found for ${tag}.`);
    if (drafts.length) return drafts[0];
    if (context.ref && context.sha) {
      const repairable = findRepairableDraft({
        releases, tag, branch: context.ref.replace('refs/heads/', ''), commitSha: context.sha
      });
      if (repairable) return repairable;
    }
    try {
      return (await github.rest.repos.getReleaseByTag({...context.repo, tag})).data;
    } catch (error) {
      if (error.status !== 404 || attempt === 6) throw error;
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
  await github.rest.repos.updateRelease({
    ...context.repo, release_id: release.id, tag_name: tag, body: result.notes
  });
  core.info(editorial
    ? `Added the editorial text from promotion PR #${promotion.number} to ${tag}.`
    : `Removed the unused editorial placeholder from ${tag}.`);
  return true;
}

module.exports = {
  START, END, isPromotion, editorialBlock, extractEditorial, replaceEditorial,
  releaseTagAtHead, promotionPullRequest, releaseByTag, applyReleaseEditorial,
  RELEASE_LOOKUP_ATTEMPTS, RELEASE_TAG_PATTERN, isUntaggedRelease, findRepairableDraft,
  missingReleaseAssets,
  releaseTagMatchesHead, reconcileReleaseTag
};
