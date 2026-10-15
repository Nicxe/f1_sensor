'use strict';

const {execFileSync} = require('node:child_process');

const START = '<!-- release-editorial:start -->';
const END = '<!-- release-editorial:end -->';

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
  return pulls.find(pr => pr.merged && isPromotion({
    base: {ref: pr.baseRefName}, head: {ref: pr.headRefName}
  }));
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
  releaseTagAtHead, promotionPullRequest, releaseByTag, applyReleaseEditorial
};
