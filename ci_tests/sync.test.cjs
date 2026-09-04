const {test} = require('node:test');
const assert = require('node:assert/strict');
const {syncOne} = require('../.github/scripts/sync-branches.cjs');

function environment(status, protectedBranch=false) {
  const writes=[];
  return {writes, context:{repo:{owner:'Nicxe',repo:'f1_sensor'}}, core:{info(){}}, github:{
    paginate:async()=>[],
    rest:{
      repos:{compareCommits:async()=>({data:{status}})},
      git:{updateRef:async x=>{writes.push(['update',x]); if(protectedBranch) throw {status:422};}, createRef:async x=>writes.push(['snapshot',x])},
      pulls:{list(){},create:async x=>{writes.push(['pr',x]);return {data:{number:42}};}},
      actions:{createWorkflowDispatch:async x=>writes.push(['ci',x])},
    },
  }};
}

test('already contained history is untouched', async()=>{
  for (const status of ['identical','behind']) {
    const env=environment(status);
    assert.equal(await syncOne(env,'beta','a'.repeat(40),'dev'),'contained');
    assert.deepEqual(env.writes,[]);
  }
});
test('fast-forward explicitly verifies the new head and never forces',async()=>{
  const env=environment('ahead');
  assert.equal(await syncOne(env,'beta','a'.repeat(40),'dev'),'fast-forward');
  assert.equal(env.writes[0][1].force,false);
  assert.equal(env.writes[1][0],'ci');
});
test('divergence or branch protection preserves both histories in a PR',async()=>{
  for(const env of [environment('diverged'),environment('ahead',true)]) {
    assert.equal(await syncOne(env,'main','b'.repeat(40),'beta'),'pull-request');
    assert.equal(env.writes.find(([kind])=>kind==='snapshot')[1].sha,'b'.repeat(40));
    assert.equal(env.writes.at(-1)[1].inputs.pull_request,'42');
    assert.equal(env.writes.some(([,v])=>v.force===true),false);
  }
});

test('real Git divergence keeps later development commits and published ancestry',async()=>{
  const {mkdtempSync,writeFileSync,rmSync}=require('node:fs');
  const {tmpdir}=require('node:os');const {join}=require('node:path');
  const {execFileSync}=require('node:child_process');
  const dir=mkdtempSync(join(tmpdir(),'f1-sync-'));
  const git=(...args)=>execFileSync('git',args,{cwd:dir,encoding:'utf8',stdio:['pipe','pipe','pipe']}).trim();
  try {
    git('init','-b','dev');git('config','user.name','CI test');git('config','user.email','ci@example.invalid');
    writeFileSync(join(dir,'base'),'base');git('add','.');git('commit','-m','base');git('branch','beta');
    writeFileSync(join(dir,'development'),'later work');git('add','.');git('commit','-m','later development');const dev=git('rev-parse','HEAD');
    git('checkout','beta');writeFileSync(join(dir,'release'),'release evidence');git('add','.');git('commit','-m','published beta');const published=git('rev-parse','HEAD');
    const env=environment('diverged');
    env.github.rest.git.createRef=async({ref,sha})=>git('update-ref',ref,sha);
    env.github.rest.pulls.create=async({head,base})=>{assert.equal(git('rev-parse',base),dev);assert.equal(git('rev-parse',head),published);return {data:{number:42}};};
    await syncOne(env,'beta',published,'dev');assert.equal(git('rev-parse','dev'),dev);
    git('checkout','dev');git('merge','--no-ff',published,'-m','merge released history');
    git('merge-base','--is-ancestor',dev,'HEAD');git('merge-base','--is-ancestor',published,'HEAD');
  } finally {rmSync(dir,{recursive:true,force:true});}
});

test('failure to dispatch verification is not misreported as a protection conflict',async()=>{
  const env=environment('ahead');env.github.rest.actions.createWorkflowDispatch=async()=>{throw {status:403};};
  await assert.rejects(syncOne(env,'beta','a'.repeat(40),'dev'));
  assert.ok(!env.writes.some(([kind])=>kind==='pr'));
});
