'use strict';

const {
  RELEASE_TAG_PATTERN, isUntaggedRelease, missingReleaseAssets
} = require('./release-editorial.cjs');

const RELEASE_ASSETS = ['f1_sensor.zip', 'f1_sensor.zip.sha256', 'f1_sensor.zip.spdx.json'];

function expectedReleaseTag(release) {
  if (RELEASE_TAG_PATTERN.test(release.tag_name)) {
    if (RELEASE_TAG_PATTERN.test(release.name) && release.name !== release.tag_name) {
      throw new Error('The release title and version tag disagree; refusing to change either.');
    }
    return release.tag_name;
  }
  if (!isUntaggedRelease(release) || !RELEASE_TAG_PATTERN.test(release.name)) {
    throw new Error('The published release has no unambiguous supported version tag.');
  }
  return release.name;
}

function releaseContent(release) {
  return JSON.stringify({
    id: release.id, name: release.name, body: release.body,
    draft: release.draft, prerelease: release.prerelease,
    published_at: release.published_at, target_commitish: release.target_commitish,
    assets: release.assets?.map(asset => ({
      id: asset.id, name: asset.name, size: asset.size, digest: asset.digest
    })).sort((a, b) => a.id - b.id)
  });
}

async function verifyPublishedRelease({
  github, context, core, releaseId,
  assetNames = RELEASE_ASSETS,
  wait = delay => new Promise(resolve => setTimeout(resolve, delay))
}) {
  const id = Number(releaseId);
  if (!Number.isSafeInteger(id) || id <= 0) throw new Error('A valid release ID is required.');
  const getRelease = async () => (await github.rest.repos.getRelease({
    ...context.repo, release_id: id
  })).data;
  // Always reload by ID: the published event may still contain the temporary
  // draft tag, or another publication consumer may already have repaired it.
  let original;
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    original = await getRelease();
    if (original.id !== id || original.draft !== false) {
      throw new Error('Publication verification only accepts already published releases; drafts remain manual.');
    }
    const missing = missingReleaseAssets(original, assetNames);
    if (!missing.length) break;
    if (attempt === 6) throw new Error(`Published release is missing assets: ${missing.join(', ')}.`);
    await wait(Math.min(1000 * 2 ** (attempt - 1), 8000));
  }
  const tag = expectedReleaseTag(original);
  if (original.prerelease !== tag.includes('-beta.')) {
    throw new Error(`The prerelease setting does not match ${tag}.`);
  }

  if (original.tag_name !== tag) {
    const expectedCommit = (await github.rest.repos.getCommit({...context.repo, ref: tag})).data.sha;
    const publishedCommit = (await github.rest.repos.getCommit({
      ...context.repo, ref: original.tag_name
    })).data.sha;
    const branch = original.prerelease ? 'beta' : 'main';
    if (expectedCommit !== publishedCommit
      || ![branch, `refs/heads/${branch}`, expectedCommit].includes(original.target_commitish)) {
      throw new Error('Refusing to associate the release with a different commit or release branch.');
    }
    try {
      const destination = (await github.rest.repos.getReleaseByTag({...context.repo, tag})).data;
      if (destination.id !== id) throw new Error(`${tag} already belongs to another release.`);
    } catch (error) {
      if (error.status !== 404) throw error;
    }
    core.warning(`Correcting the already published release ${id} from ${original.tag_name} to ${tag}.`);
    // Only repair metadata after manual publication. Never set draft=false,
    // create a release, or move/create a Git tag here.
    await github.rest.repos.updateRelease({...context.repo, release_id: id, tag_name: tag});
  }

  for (let attempt = 1; attempt <= 6; attempt += 1) {
    const release = await getRelease();
    if (release.id !== id || release.draft !== false) {
      throw new Error('The release is no longer published; leaving its publication state unchanged.');
    }
    if (releaseContent(original) !== releaseContent(release)) {
      throw new Error('Release notes, publication settings or assets changed during tag verification.');
    }
    if (release.tag_name === tag && !missingReleaseAssets(release, assetNames).length) {
      try {
        const byTag = (await github.rest.repos.getReleaseByTag({...context.repo, tag})).data;
        if (byTag.id !== id || byTag.tag_name !== tag || byTag.draft !== false) {
          throw new Error(`${tag} does not identify the expected published release.`);
        }
        core.info(`Published release ${id} is verified at ${tag}; release notes and assets are preserved.`);
        return release;
      } catch (error) {
        if (error.status !== 404) throw error;
      }
    }
    if (attempt < 6) await wait(Math.min(1000 * 2 ** (attempt - 1), 8000));
  }
  throw new Error(`Published release ${id} could not be verified at ${tag}.`);
}

module.exports = {RELEASE_ASSETS, expectedReleaseTag, verifyPublishedRelease};
