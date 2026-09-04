const {test, mock} = require('node:test');
const assert = require('node:assert/strict');
const child = require('node:child_process');

async function runCase({tag='',published=false,changesDuringBuild=false,branch='beta'}={}) {
  const calls=[]; let queries=0;
  const old={branch:process.env.GITHUB_REF_NAME,repo:process.env.GITHUB_REPOSITORY};
  process.env.GITHUB_REF_NAME=branch;process.env.GITHUB_REPOSITORY='Nicxe/f1_sensor';
  const mocked=mock.method(child,'execFileSync',(command,args)=>{
    calls.push([command,args]);
    if(command==='git')return tag;
    if(command==='gh' && args[0]==='api') {queries++;return JSON.stringify([[{tag_name:tag.trim(),draft:!(published || (changesDuringBuild && queries>1))}]]);}
    return '';
  });
  delete require.cache[require.resolve('../.github/scripts/run-release.cjs')];
  try {await require('../.github/scripts/run-release.cjs').main();return calls;}
  finally {mocked.mock.restore();for(const [key,value] of [['GITHUB_REF_NAME',old.branch],['GITHUB_REPOSITORY',old.repo]]) {if(value===undefined)delete process.env[key];else process.env[key]=value;}}
}
test('new release retains semantic-release version and notes policy',async()=>{
  const calls=await runCase();assert.deepEqual(calls.at(-1),['npx',['--no-install','semantic-release']]);
});
test('a published version is never rebuilt or replaced',async()=>{
  const calls=await runCase({tag:'v5.5.0-beta.2\n',published:true});assert.ok(!calls.some(([command])=>command==='python3'));assert.ok(!calls.some(([,args])=>args.includes('upload')));
});
test('an existing draft is rebuilt at its original version and verified before upload',async()=>{
  const calls=await runCase({tag:'v5.5.0-beta.2\n'});assert.ok(calls.some(([c,a])=>c==='python3' && a.includes('scripts/verify_release.py') && a.includes('5.5.0-beta.2')));assert.ok(calls.at(-1)[1].includes('upload'));assert.ok(!calls.some(([,a])=>a.includes('create')));
});
test('publication during recovery prevents asset replacement',async()=>{
  await assert.rejects(runCase({tag:'v5.5.0-beta.2\n',changesDuringBuild:true}),/no longer a draft/);
});
test('release branch and multiple-tag ambiguities fail closed',async()=>{
  await assert.rejects(runCase({branch:'dev'}),/require beta or main/);
  await assert.rejects(runCase({tag:'v5.5.0-beta.1\nv5.5.0-beta.2'}),/Ambiguous/);
});
