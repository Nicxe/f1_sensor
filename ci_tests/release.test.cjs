const {test, mock} = require('node:test');
const assert = require('node:assert/strict');
const child = require('node:child_process');
const fs = require('node:fs');

async function runCase({tag='',published=false,changesDuringBuild=false,branch='beta'}={}) {
  const calls=[]; const fetchCalls=[];
  const old={branch:process.env.GITHUB_REF_NAME,repo:process.env.GITHUB_REPOSITORY};
  process.env.GITHUB_REF_NAME=branch;process.env.GITHUB_REPOSITORY='Nicxe/f1_sensor';
  const mocked=mock.method(child,'execFileSync',(command,args)=>{
    calls.push([command,args]);
    if(command==='git')return tag;
    if(command==='gh' && args[0]==='api') {
      if (args.some(arg=>String(arg).endsWith('/assets'))) return '[]';
      if (args.includes('--method') && args.includes('POST')) return '{}';
      const release={id:42,tag_name:tag.trim(),name:tag.trim(),target_commitish:branch,
        upload_url:'https://uploads.github.com/repos/Nicxe/f1_sensor/releases/42/assets{?name,label}',
        draft:!published};
      if (changesDuringBuild && args.some(arg=>String(arg).endsWith('/releases/42'))) {
        release.draft=false;
      }
      if (args.some(arg=>String(arg).endsWith('/releases/42'))) return JSON.stringify(release);
      return JSON.stringify([[release]]);
    }
    return '';
  });
  const mockedFetch=mock.method(globalThis,'fetch',async(...args)=>{
    fetchCalls.push(args);return {ok:true,status:201,text:async()=>''};
  });
  const originalReadFile=fs.readFileSync;
  const mockedRead=mock.method(fs,'readFileSync',(file,...args)=>
    String(file).includes('/f1_sensor.zip') ? Buffer.from('asset') : originalReadFile(file,...args));
  delete require.cache[require.resolve('../.github/scripts/run-release.cjs')];
  try {await require('../.github/scripts/run-release.cjs').main();calls.fetchCalls=fetchCalls;return calls;}
  finally {mockedRead.mock.restore();mockedFetch.mock.restore();mocked.mock.restore();for(const [key,value] of [['GITHUB_REF_NAME',old.branch],['GITHUB_REPOSITORY',old.repo]]) {if(value===undefined)delete process.env[key];else process.env[key]=value;}}
}
test('new release retains semantic-release version and notes policy',async()=>{
  const calls=await runCase();assert.deepEqual(calls.at(-1),['npx',['--no-install','semantic-release']]);
});
test('a published version is never rebuilt or replaced',async()=>{
  const calls=await runCase({tag:'v5.5.0-beta.2\n',published:true});assert.ok(!calls.some(([command])=>command==='python3'));assert.ok(!calls.some(([,args])=>args.includes('upload')));
});
test('an existing draft is rebuilt at its original version and verified before upload',async()=>{
  const calls=await runCase({tag:'v5.5.0-beta.2\n'});
  assert.ok(calls.some(([c,a])=>c==='git' && a.includes('worktree') && a.at(-1)==='v5.5.0-beta.2'));
  assert.ok(calls.some(([c,a])=>c==='python3' && a.includes('scripts/verify_release.py') && a.includes('5.5.0-beta.2')));
  assert.equal(calls.fetchCalls.length,3);
  assert.ok(calls.fetchCalls.every(([url])=>String(url).startsWith('https://uploads.github.com/')));
  assert.ok(!calls.some(([,a])=>a.includes('release') && a.includes('create')));
});
test('publication during recovery prevents asset replacement',async()=>{
  await assert.rejects(runCase({tag:'v5.5.0-beta.2\n',changesDuringBuild:true}),/no longer a draft/);
});
test('release branch and multiple-tag ambiguities fail closed',async()=>{
  await assert.rejects(runCase({branch:'dev'}),/require beta or main/);
  await assert.rejects(runCase({tag:'v5.5.0-beta.1\nv5.5.0-beta.2'}),/Ambiguous/);
});
test('the latest unnoted beta tag without a release is recovered',()=>{
  const mocked=mock.method(child,'execFileSync',(command,args)=>{
    if(command==='git' && args[0]==='show-ref')throw new Error('missing note');
    return '';
  });
  delete require.cache[require.resolve('../.github/scripts/run-release.cjs')];
  try {
    const {interruptedReleaseTag}=require('../.github/scripts/run-release.cjs');
    assert.equal(interruptedReleaseTag({
      branch:'beta',tags:['v6.1.0-beta.2','v6.1.0-beta.1'],
      releases:[{tag_name:'v6.1.0-beta.1',prerelease:true}]
    }),'v6.1.0-beta.2');
    assert.equal(interruptedReleaseTag({
      branch:'beta',tags:['v6.1.0-beta.2','v6.1.0-beta.1'],
      releases:[{tag_name:'v6.1.0-beta.2',prerelease:true}]
    }),'');
    assert.equal(interruptedReleaseTag({
      branch:'beta',tags:['v6.1.0-beta.2','v6.1.0-beta.1'],
      releases:[{id:42,tag_name:'v6.1.0-beta.2',name:'v6.1.0-beta.2',
        target_commitish:'beta',draft:true,prerelease:true}]
    }),'v6.1.0-beta.2');
  } finally {mocked.mock.restore();}
});
