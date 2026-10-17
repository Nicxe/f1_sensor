'use strict';
// Recovery is restricted to a tag on the tested commit, and never edits a
// published release. New releases still use the unchanged semantic-release config.
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { setReleaseContributors } = require('./release-contributors.cjs');
const run = (command, args, options={}) => execFileSync(command,args,{encoding:'utf8',...options});
const releaseTagPattern = /^v\d+\.\d+\.\d+(?:-beta\.\d+)?$/;

function releaseTagsAtHead(branch) {
  return run('git',['tag','--points-at','HEAD']).trim().split('\n').filter(tag =>
    releaseTagPattern.test(tag) && (branch === 'beta') === tag.includes('-beta.')
  );
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

function hydrateBetaReleaseNotes(branch) {
  if (branch !== 'beta') return;
  try {
    const releases = JSON.parse(run('gh',[
      'api',`repos/${process.env.GITHUB_REPOSITORY}/releases?per_page=100`,'--paginate','--slurp'
    ])).flat();
    for (const release of releases) {
      const tag = String(release.tag_name || '');
      if (!release.prerelease || !releaseTagPattern.test(tag) || !tag.includes('-beta.')) continue;
      const ref = noteRefForTag(tag);
      if (localRefExists(ref)) continue;
      run('git',[
        'notes','--ref',`semantic-release-${tag}`,'add','-f','-m',JSON.stringify({channels:['beta']}),tag
      ],{env:gitIdentityEnvironment(),stdio:'ignore'});
    }
  } catch (error) {
    // Release metadata is an aid for reruns; it must never block a release.
    console.warn(`Unable to hydrate semantic-release notes: ${error.message}`);
  }
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
  hydrateBetaReleaseNotes(branch);
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

async function recoverDraft({branch, tag}) {
  const version = tag.slice(1);
  setReleaseContributors({ branch, head: 'HEAD', excludeTag: tag });
  const directory = fs.mkdtempSync(path.join(os.tmpdir(),'f1-release-'));
  try {
    const releases = JSON.parse(run('gh',['api',`repos/${process.env.GITHUB_REPOSITORY}/releases?per_page=100`,'--paginate','--slurp'])).flat();
    const existing = releases.find(r => r.tag_name === tag);
    if (existing && !existing.draft) {
      console.log(`${tag} is already published; leaving it untouched.`);
      return;
    }
    run('python3',['scripts/build_release.py','--component','custom_components/f1_sensor','--output','f1_sensor.zip','--version',version],{stdio:'inherit'});
    run('python3',['scripts/verify_release.py','f1_sensor.zip','--version',version],{stdio:'inherit'});
    if (!existing) {
      const config = require('../../release.config.cjs');
      // Recover the rare interruption between pushing the version tag and
      // creating its draft, using the same release-notes plugin and template.
      const previous = run('git',['tag','--merged','HEAD','--sort=-version:refname']).trim().split('\n').find(t => t!==tag && /^v\d+\.\d+\.\d+(?:-beta\.\d+)?$/.test(t) && (branch==='beta' || !t.includes('-')));
      const hashes = run('git',['rev-list','--reverse', previous ? `${previous}..HEAD` : 'HEAD']).trim().split('\n').filter(Boolean);
      const commits = hashes.map(hash => ({hash, message:run('git',['show','-s','--format=%B',hash]).trim(), committerDate:run('git',['show','-s','--format=%cI',hash]).trim()}));
      const [,options] = config.plugins.find(p => p[0]==='@semantic-release/release-notes-generator');
      const {generateNotes} = await import('@semantic-release/release-notes-generator');
      const notes = await generateNotes(options, {cwd:process.cwd(), env:process.env, logger:console, options:{repositoryUrl:`https://github.com/${process.env.GITHUB_REPOSITORY}.git`}, commits, lastRelease:previous ? {gitTag:previous,version:previous.slice(1)} : {}, nextRelease:{gitTag:tag,version,channel:branch==='beta'?'beta':undefined}});
      const file = path.join(directory,'notes.md');fs.writeFileSync(file,notes);
      const args=['release','create',tag,'--draft','--verify-tag','--target',branch,'--title',tag,'--notes-file',file];
      if(branch==='beta')args.push('--prerelease');
      run('gh',args,{stdio:'inherit'});
    }
    const current = JSON.parse(run('gh',['api',`repos/${process.env.GITHUB_REPOSITORY}/releases?per_page=100`,'--paginate','--slurp'])).flat().find(r=>r.tag_name===tag);
    if (!current?.draft) throw new Error('The release is no longer a draft; refusing to replace assets.');
    run('gh',['release','upload',tag,'f1_sensor.zip','f1_sensor.zip.sha256','f1_sensor.zip.spdx.json','--clobber'],{stdio:'inherit'});
    console.log(`Recovered draft ${tag}; publication remains manual.`);
  } finally { fs.rmSync(directory,{recursive:true,force:true}); }
}
module.exports = {
  main,
  hydrateBetaReleaseNotes,
  localRefExists,
  noteRefForTag,
  releaseTagsAtHead,
  retryNotePush
};
if (require.main === module) main().catch(error=>{console.error(error.message);process.exitCode=1;});
