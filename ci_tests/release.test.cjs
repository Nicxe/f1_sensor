const {test, mock} = require('node:test');
const assert = require('node:assert/strict');
const child = require('node:child_process');
const fs = require('node:fs');

async function runCase({tag='',published=false,changesDuringBuild=false,mismatched=false,branch='beta',createRc=false}={}) {
  const calls=[]; const fetchCalls=[];
  let currentTag=mismatched ? 'untagged-abc123' : tag.trim().split('\n').at(-1);
  const old={branch:process.env.GITHUB_REF_NAME,repo:process.env.GITHUB_REPOSITORY,
    createRc:process.env.CREATE_RC,stage:process.env.RELEASE_STAGE};
  process.env.GITHUB_REF_NAME=branch;process.env.GITHUB_REPOSITORY='Nicxe/f1_sensor';
  process.env.CREATE_RC=String(createRc);
  const mocked=mock.method(child,'execFileSync',(command,args)=>{
    calls.push([command,args]);
    if (command === 'npx') calls.releaseStage = process.env.RELEASE_STAGE;
    if(command==='git')return tag;
    if(command==='gh' && args[0]==='api') {
      if (args.includes('PATCH')) {
        assert.equal(changesDuringBuild,false,'A manually published release must not be edited during recovery');
        currentTag=args.find(arg=>String(arg).startsWith('tag_name=')).slice('tag_name='.length);
      }
      if (args.some(arg=>String(arg).endsWith('/assets'))) return '[]';
      if (args.includes('--method') && args.includes('POST')) return '{}';
      const release={id:42,tag_name:currentTag,name:tag.trim(),target_commitish:branch,
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
  finally {mockedRead.mock.restore();mockedFetch.mock.restore();mocked.mock.restore();for(const [key,value] of [['GITHUB_REF_NAME',old.branch],['GITHUB_REPOSITORY',old.repo],['CREATE_RC',old.createRc],['RELEASE_STAGE',old.stage]]) {if(value===undefined)delete process.env[key];else process.env[key]=value;}}
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
test('draft recovery repairs only the tag without changing notes or publication settings',async()=>{
  const calls=await runCase({tag:'v5.5.0-beta.2\n',mismatched:true});
  const patches=calls.filter(([command,args])=>command==='gh' && args.includes('PATCH'));
  assert.deepEqual(patches,[['gh',['api','--method','PATCH','repos/Nicxe/f1_sensor/releases/42','-f','tag_name=v5.5.0-beta.2']]]);
  assert.equal(calls.fetchCalls.length,3);
});
test('a mismatched draft published during recovery is never made a draft again',async()=>{
  await assert.rejects(runCase({tag:'v5.5.0-beta.2\n',mismatched:true,changesDuringBuild:true}),/no longer a draft/);
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

test('manual RC starts from the already published final beta on the same commit', async () => {
  const calls = await runCase({tag: 'v6.1.0-beta.3\n', published: true, createRc: true});
  assert.equal(calls.releaseStage, 'rc');
  assert.ok(calls.some(([command]) => command === 'npx'));
  assert.ok(!calls.some(([command]) => command === 'python3'));
});

test('RC retries select the candidate when the final beta shares its commit', async () => {
  const calls = await runCase({tag: 'v6.1.0-beta.3\nv6.1.0-rc.1\n', createRc: true});
  assert.ok(!calls.some(([command]) => command === 'npx'));
  assert.ok(calls.some(([command, args]) => command === 'python3'
    && args.includes('scripts/verify_release.py') && args.includes('6.1.0-rc.1')));
  assert.equal(calls.fetchCalls.length, 3);
});

test('published RC retry leaves the release untouched without another version', async () => {
  const calls = await runCase({tag: 'v6.1.0-beta.3\nv6.1.0-rc.1\n', createRc: true, published: true});
  assert.ok(!calls.some(([command]) => ['npx', 'python3'].includes(command)));
  assert.equal(calls.fetchCalls.length, 0);
});

test('Create RC rejects main before fetching or touching release metadata', async () => {
  await assert.rejects(runCase({branch: 'main', createRc: true}), /requires the beta branch/);
});

test('RC release metadata hydrates the existing beta distribution channel', () => {
  const notes = [];
  const mocked = mock.method(child, 'execFileSync', (command, args) => {
    if (command === 'git' && args[0] === 'show-ref') throw new Error('missing note');
    if (command === 'git' && args[0] === 'notes') notes.push(args);
    return '';
  });
  delete require.cache[require.resolve('../.github/scripts/run-release.cjs')];
  try {
    require('../.github/scripts/run-release.cjs').hydrateBetaReleaseNotes('beta', [
      {tag_name: 'v6.1.0-beta.3', prerelease: true},
      {tag_name: 'v6.1.0-rc.1', prerelease: true},
      {tag_name: 'v6.1.0', prerelease: false}
    ]);
    assert.equal(notes.length, 2);
    assert.ok(notes.every(args => args.includes('{"channels":["beta"]}')));
  } finally {mocked.mock.restore();}
});

test('a completed RC series requires stable history before continuing, while drafts and unrelated hotfixes do not', () => {
  let missing = false;
  const mocked = mock.method(child, 'execFileSync', (command, args) => {
    if (args[0] === 'rev-parse' && missing) throw new Error('missing tag');
    return '';
  });
  delete require.cache[require.resolve('../.github/scripts/run-release.cjs')];
  try {
    const {assertOpenReleaseCycle} = require('../.github/scripts/run-release.cjs');
    const request = {branch: 'beta', tags: ['v6.1.0-rc.2', 'v6.0.0'],
      releases: [{tag_name: 'v6.1.0', draft: false, prerelease: false}]};
    assert.throws(() => assertOpenReleaseCycle(request), /Merge main into dev/);
    assert.doesNotThrow(() => assertOpenReleaseCycle({...request,
      releases: [{...request.releases[0], draft: true}]}));
    assert.doesNotThrow(() => assertOpenReleaseCycle({...request,
      releases: [{...request.releases[0], tag_name: 'v6.0.1'}]}));
    assert.throws(() => assertOpenReleaseCycle({...request,
      releases: [{...request.releases[0], tag_name: 'v6.2.0'}]}), /Merge main into dev/);
    assert.doesNotThrow(() => assertOpenReleaseCycle({...request,
      tags: ['v6.1.0', ...request.tags]}));
    missing = true;
    assert.throws(() => assertOpenReleaseCycle(request), /Fetch the published/);
  } finally {mocked.mock.restore();}
});
