'use strict';
// Recovery is restricted to a release tag contained in the tested history and
// never edits a published release. New releases still use semantic-release.
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { setReleaseContributors } = require('./release-contributors.cjs');
const {
  extractEditorial,
  findRepairableDraft,
  replaceEditorial
} = require('./release-editorial.cjs');
const run = (command, args, options={}) => execFileSync(command,args,{encoding:'utf8',...options});
const releaseTagPattern = /^v\d+\.\d+\.\d+(?:-beta\.\d+)?$/;

function lines(value) {
  return String(value || '').trim().split('\n').filter(Boolean);
}

function isBranchTag(tag, branch) {
  return releaseTagPattern.test(tag) && (branch === 'beta') === tag.includes('-beta.');
}

function releaseTagsAtHead(branch) {
  return lines(run('git',['tag','--points-at','HEAD'])).filter(tag => isBranchTag(tag, branch));
}

function releaseTagsMerged(branch, head='HEAD') {
  return lines(run('git',['tag','--merged',head,'--sort=-version:refname']))
    .filter(tag => isBranchTag(tag, branch));
}

function noteRefForTag(tag) {
  return `refs/notes/semantic-release-${tag}`;
}

function localRefExists(ref) {
  try {
    run('git',['show-ref','--verify','--quiet',ref],{stdio:'ignore'});
    return true;
  } catch {
    return false;
  }
}

function gitIdentityEnvironment() {
  return {
    ...process.env,
    GIT_AUTHOR_NAME: 'semantic-release-bot',
    GIT_AUTHOR_EMAIL: 'semantic-release-bot@martynus.net',
    GIT_COMMITTER_NAME: 'semantic-release-bot',
    GIT_COMMITTER_EMAIL: 'semantic-release-bot@martynus.net'
  };
}

function addLocalReleaseNote(tag, branch) {
  const ref = noteRefForTag(tag);
  if (localRefExists(ref)) return false;
  run('git',[
    'notes','--ref',`semantic-release-${tag}`,'add','-f','-m',
    JSON.stringify({channels:[branch === 'beta' ? 'beta' : null]}),tag
  ],{env:gitIdentityEnvironment(),stdio:'ignore'});
  return true;
}

function listReleases() {
  return JSON.parse(run('gh',[
    'api',`repos/${process.env.GITHUB_REPOSITORY}/releases?per_page=100`,'--paginate','--slurp'
  ])).flat();
}

function fetchReleaseNotes() {
  run('git',['fetch','--',repositoryUrl(),'+refs/notes/*:refs/notes/*'],{stdio:'ignore'});
}

function hydrateBetaReleaseNotes(branch, releases=listReleases()) {
  if (branch !== 'beta') return;
  try {
    for (const release of releases) {
      const tag = String(release.tag_name || '');
      if (!release.prerelease || !releaseTagPattern.test(tag) || !tag.includes('-beta.')) continue;
      addLocalReleaseNote(tag, branch);
    }
  } catch (error) {
    // Release metadata is an aid for reruns; it must never block a release.
    console.warn(`Unable to hydrate semantic-release notes: ${error.message}`);
  }
}

function recoverableRelease({branch, releases, tag}) {
  const commitSha = run('git',['rev-list','-n','1',tag]).trim();
  return releases.find(release => release.tag_name === tag)
    || findRepairableDraft({releases, tag, branch, commitSha});
}

function interruptedReleaseTag({branch, releases, tags=releaseTagsMerged(branch)}) {
  const latestTag = tags[0];
  if (!latestTag) return '';
  const release = recoverableRelease({branch, releases, tag: latestTag});
  if (release && !release.draft) return '';
  // A draft still needs asset recovery even when semantic-release managed to
  // publish its channel note. A note without any draft is an intentional
  // historical boundary and must not be turned into a release retroactively.
  if (!release && localRefExists(noteRefForTag(latestTag))) return '';
  return latestTag;
}

function repositoryUrl() {
  if (process.env.GITHUB_REPOSITORY) return `https://github.com/${process.env.GITHUB_REPOSITORY}`;
  return run('git',['remote','get-url','origin']).trim();
}

function retryNotePush(noteRef) {
  if (!localRefExists(noteRef)) return false;
  for (const [attempt, delay] of [0,5000,15000].entries()) {
    if (delay) run('node',['-e',`setTimeout(() => process.exit(0), ${delay})`],{stdio:'ignore'});
    try {
      run('git',['push','--',repositoryUrl(),noteRef],{stdio:'inherit'});
      console.log(`Pushed ${noteRef} after semantic-release interrupted during note publication.`);
      return true;
    } catch (error) {
      console.warn(`GitHub rejected ${noteRef} (attempt ${attempt + 1}/3): ${error.message}`);
    }
  }
  return false;
}

async function main() {
  const branch = process.env.GITHUB_REF_NAME;
  if (!['main','beta'].includes(branch)) throw new Error('Releases require beta or main');
  fetchReleaseNotes();
  const releases = listReleases();
  const interruptedTag = interruptedReleaseTag({branch, releases});
  if (interruptedTag) {
    addLocalReleaseNote(interruptedTag, branch);
    retryNotePush(noteRefForTag(interruptedTag));
    console.warn(`Recovering interrupted release ${interruptedTag} from its tagged commit.`);
    await recoverDraft({branch, tag: interruptedTag, releases});
    if (releaseTagsAtHead(branch).includes(interruptedTag)) return;
  }
  hydrateBetaReleaseNotes(branch, releases);
  const tags = releaseTagsAtHead(branch);
  if (!tags.length) {
    setReleaseContributors({ branch });
    try {
      run('npx',['--no-install','semantic-release'],{stdio:'inherit'});
      return;
    } catch (error) {
      // semantic-release creates the version tag and its local note before
      // pushing the note. GitHub can reject that final write transiently;
      // recover the already-created tag instead of losing the release draft.
      const partialTags = releaseTagsAtHead(branch);
      if (partialTags.length !== 1 || !localRefExists(noteRefForTag(partialTags[0]))) throw error;
      const tag = partialTags[0];
      retryNotePush(noteRefForTag(tag));
      console.warn(`semantic-release stopped after creating ${tag}; recovering its draft release.`);
      await recoverDraft({branch, tag});
      return;
    }
  }
  if (tags.length !== 1) throw new Error('Ambiguous release tags on the tested commit');
  await recoverDraft({branch, tag: tags[0]});
}

function promotionEditorial({branch, tag}) {
  const commit = run('git',['rev-list','-n','1',tag]).trim();
  const pulls = JSON.parse(run('gh',[
    'api',`repos/${process.env.GITHUB_REPOSITORY}/commits/${commit}/pulls`,
    '--header','Accept: application/vnd.github+json'
  ]));
  const source = branch === 'beta' ? 'dev' : 'beta';
  const promotion = pulls.find(pr => pr.merged_at
    && pr.merge_commit_sha === commit
    && pr.base?.ref === branch
    && pr.head?.ref === source);
  if (!promotion) return '';
  const editorial = extractEditorial(promotion.body);
  if (editorial === null) throw new Error(`Promotion PR #${promotion.number} has an invalid release editorial block.`);
  return editorial;
}

async function uploadReleaseAsset({release, filename, request=globalThis.fetch}) {
  const template = String(release.upload_url || '');
  if (!template.startsWith('https://uploads.github.com/')) {
    throw new Error(`Draft release ${release.id} has no trusted asset upload URL.`);
  }
  const url = `${template.replace(/\{.*$/, '')}?name=${encodeURIComponent(filename)}`;
  const response = await request(url,{
    method:'POST',
    headers:{
      Accept:'application/vnd.github+json',
      Authorization:`Bearer ${process.env.GITHUB_TOKEN}`,
      'Content-Type':'application/octet-stream',
      'X-GitHub-Api-Version':'2022-11-28'
    },
    body:fs.readFileSync(path.resolve(filename))
  });
  if (!response.ok) {
    throw new Error(`Could not upload ${filename} to draft release ${release.id}: ${response.status} ${await response.text()}`);
  }
}

async function recoverDraft({branch, tag, releases=listReleases()}) {
  run('git',['merge-base','--is-ancestor',tag,'HEAD'],{stdio:'ignore'});
  const version = tag.slice(1);
  setReleaseContributors({ branch, head: tag, excludeTag: tag });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(),'f1-release-'));
  const source = path.join(directory,'source');
  const archive = path.resolve('f1_sensor.zip');
  let worktreeAdded = false;
  try {
    let existing = recoverableRelease({branch, releases, tag});
    if (existing && !existing.draft) {
      console.log(`${tag} is already published; leaving it untouched.`);
      return;
    }
    run('git',['worktree','add','--detach',source,tag],{stdio:'ignore'});
    worktreeAdded = true;
    run('python3',[
      'scripts/build_release.py','--component','custom_components/f1_sensor',
      '--output',archive,'--version',version
    ],{cwd:source,stdio:'inherit'});
    run('python3',['scripts/verify_release.py',archive,'--version',version],{cwd:source,stdio:'inherit'});
    if (!existing) {
      const config = require('../../release.config.cjs');
      // Recover the rare interruption between pushing the version tag and
      // creating its draft, using the same release-notes plugin and template.
      const previous = releaseTagsMerged(branch,tag).find(candidate => candidate !== tag);
      const hashes = lines(run('git',['rev-list','--reverse', previous ? `${previous}..${tag}` : tag]));
      const commits = hashes.map(hash => ({hash, message:run('git',['show','-s','--format=%B',hash]).trim(), committerDate:run('git',['show','-s','--format=%cI',hash]).trim()}));
      const [,options] = config.plugins.find(p => p[0]==='@semantic-release/release-notes-generator');
      const {generateNotes} = await import('@semantic-release/release-notes-generator');
      const generated = await generateNotes(options, {cwd:process.cwd(), env:process.env, logger:console, options:{repositoryUrl:`https://github.com/${process.env.GITHUB_REPOSITORY}.git`}, commits, lastRelease:previous ? {gitTag:previous,version:previous.slice(1)} : {}, nextRelease:{gitTag:tag,version,channel:branch==='beta'?'beta':undefined}});
      const notes = replaceEditorial(generated,promotionEditorial({branch,tag})).notes;
      const payload = path.join(directory,'release.json');
      fs.writeFileSync(payload,JSON.stringify({
        tag_name:tag,target_commitish:branch,name:tag,body:notes,draft:true,
        prerelease:branch==='beta'
      }));
      existing = JSON.parse(run('gh',[
        'api','--method','POST',`repos/${process.env.GITHUB_REPOSITORY}/releases`,
        '--input',payload
      ]));
    }
    if (existing.tag_name !== tag) {
      existing = JSON.parse(run('gh',[
        'api','--method','PATCH',
        `repos/${process.env.GITHUB_REPOSITORY}/releases/${existing.id}`,
        '-f',`tag_name=${tag}`,'-f',`target_commitish=${branch}`,'-f',`name=${tag}`,
        '-F','draft=true','-F',`prerelease=${branch==='beta'}`
      ]));
    }
    const current = JSON.parse(run('gh',[
      'api',`repos/${process.env.GITHUB_REPOSITORY}/releases/${existing.id}`
    ]));
    if (!current?.draft) throw new Error('The release is no longer a draft; refusing to replace assets.');
    if (current.tag_name !== tag) throw new Error(`Draft release ${current.id} is not associated with ${tag}.`);
    const assets = JSON.parse(run('gh',[
      'api',`repos/${process.env.GITHUB_REPOSITORY}/releases/${current.id}/assets`
    ]));
    for (const filename of ['f1_sensor.zip','f1_sensor.zip.sha256','f1_sensor.zip.spdx.json']) {
      for (const asset of assets.filter(candidate => candidate.name === filename)) {
        run('gh',['api','--method','DELETE',
          `repos/${process.env.GITHUB_REPOSITORY}/releases/assets/${asset.id}`]);
      }
      await uploadReleaseAsset({release:current,filename});
    }
    console.log(`Recovered draft ${tag}; publication remains manual.`);
  } finally {
    if (worktreeAdded) {
      try {run('git',['worktree','remove','--force',source],{stdio:'ignore'});} catch {}
    }
    fs.rmSync(directory,{recursive:true,force:true});
  }
}
module.exports = {
  addLocalReleaseNote,
  interruptedReleaseTag,
  main,
  hydrateBetaReleaseNotes,
  localRefExists,
  noteRefForTag,
  promotionEditorial,
  recoverableRelease,
  recoverDraft,
  releaseTagsMerged,
  releaseTagsAtHead,
  retryNotePush,
  uploadReleaseAsset
};
if (require.main === module) main().catch(error=>{console.error(error.message);process.exitCode=1;});
