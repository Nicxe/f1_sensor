'use strict';

const PERMANENT = new Set(['main', 'beta', 'content', 'dev']);

function missingReference(error) {
  if (error.status === 404) return true;
  const message = error.response?.data?.message || error.message || '';
  return error.status === 422 && /^Reference does not exist\.?$/.test(message.trim());
}

async function cleanupMergedBranch({github, context, core}) {
  const pr = context.payload.pull_request;
  const branch = pr?.head?.ref;
  const repository = `${context.repo.owner}/${context.repo.repo}`;
  if (!pr?.merged || pr.head.repo?.full_name !== repository || PERMANENT.has(branch)) {
    core.info(`Preserving branch ${branch || '<unknown>'}.`);
    return 'preserved';
  }
  try {
    const ref = (await github.rest.git.getRef({...context.repo, ref: `heads/${branch}`})).data;
    if (ref.object.sha !== pr.head.sha) {
      core.info(`Preserving ${branch}; it has advanced since the merged pull request.`);
      return 'preserved';
    }
    await github.rest.git.deleteRef({...context.repo, ref: `heads/${branch}`});
    core.info(`Deleted merged temporary branch ${branch}.`);
    return 'deleted';
  } catch (error) {
    if (!missingReference(error)) throw error;
    core.info(`Branch ${branch} was already deleted.`);
    return 'already_missing';
  }
}

module.exports = {cleanupMergedBranch, missingReference};
