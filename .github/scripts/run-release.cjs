'use strict';
// Recovery is restricted to a tag on the tested commit, and never edits a
// published release. New releases still use the unchanged semantic-release config.
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const run = (command, args, options={}) => execFileSync(command,args,{encoding:'utf8',...options});

async function main() {
  const branch = process.env.GITHUB_REF_NAME;
  if (!['main','beta'].includes(branch)) throw new Error('Releases require beta or main');
  const tags = run('git',['tag','--points-at','HEAD']).trim().split('\n').filter(tag => /^v\d+\.\d+\.\d+(?:-beta\.\d+)?$/.test(tag) && (branch==='beta')===tag.includes('-beta.'));
  if (!tags.length) {
    run('npx',['--no-install','semantic-release'],{stdio:'inherit'});
    return;
  }
  if (tags.length !== 1) throw new Error('Ambiguous release tags on the tested commit');
  const tag = tags[0];
  const version = tag.slice(1);
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
module.exports = {main};
if (require.main === module) main().catch(error=>{console.error(error.message);process.exitCode=1;});
