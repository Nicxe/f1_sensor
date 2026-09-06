const {test} = require('node:test');
const assert = require('node:assert/strict');
const {syncOne, synchronize} = require('../.github/scripts/sync-branches.cjs');
const source='a'.repeat(40), base='b'.repeat(40), merged='c'.repeat(40);
function environment(status='diverged') {
  const writes=[];
  const pr={number:42,node_id:'PR_42',state:'open',user:{login:'github-actions[bot]'},head:{sha:merged,repo:{full_name:'Nicxe/f1_sensor'}},base:{ref:'dev',sha:base}};
  const env={writes,pr,context:{repo:{owner:'Nicxe',repo:'f1_sensor'},payload:{}},core:{info(){}},github:{
    paginate:async(route)=>typeof route==='string' ? [
      {type:'pull_request'}, {type:'required_status_checks',parameters:{strict_required_status_checks_policy:true,required_status_checks:[{context:'CI required',integration_id:15368}]}}
    ] : [],
    graphql:async(_,data)=>writes.push(['queue',data]),
    rest:{
      git:{getRef:async()=>({data:{object:{sha:base}}}),createRef:async data=>writes.push(['snapshot',data]),
        createCommit:async data=>{writes.push(['commit',data]);return {data:{sha:merged}};},updateRef:async data=>writes.push(['update',data])},
      repos:{compareCommits:async()=>({data:{status}}),getCommit:async()=>({data:{sha:source,commit:{tree:{sha:'source-tree'}}}}),merge:async data=>writes.push(['merge',data])},
      pulls:{list(){},create:async data=>{writes.push(['pr',data]);return {data:pr};},get:async()=>({data:pr}),update:async data=>writes.push(['close',data])},
      checks:{listForRef(){},create:async data=>writes.push(['pending',data])},
      actions:{createWorkflowDispatch:async data=>writes.push(['ci',data])},
    },
  }};
  return env;
}

test('contained history does not start verification or mutate refs', async()=>{
  for(const status of ['identical','behind']) {
    const env=environment(status);
    assert.equal(await syncOne(env,'main',source,'dev'),'contained');
    assert.deepEqual(env.writes,[]);
  }
});
test('target snapshot is merged before CI and automatic merge is queued last', async()=>{
  const env=environment();
  assert.equal(await syncOne(env,'main',source,'dev'),'pull-request');
  assert.deepEqual(env.writes.map(x=>x[0]),['snapshot','merge','pr','pending','ci','queue']);
  assert.match(env.writes[0][1].ref,new RegExp(`${source.slice(0,12)}-${base.slice(0,12)}$`));
  assert.equal(env.writes[1][1].head,base);
  assert.equal(env.writes[3][1].external_id,`f1-pr:42:${base}:${merged}`);
  assert.equal(env.writes[4][1].inputs.pull_request,'42');
});
test('fast-forwardable targets receive separate commits so their required checks cannot collide',async()=>{
  const messages=[];
  for(const target of ['dev','beta','content']) {
    const env=environment('ahead');env.pr.base.ref=target;
    await syncOne(env,'main',source,target);
    const commit=env.writes.find(x=>x[0]==='commit')[1];
    messages.push(commit.message);
    assert.equal(commit.tree,'source-tree');
    assert.deepEqual(commit.parents,[source,base]);
    const update=env.writes.find(x=>x[0]==='update')[1];
    assert.equal(update.force,false);
    assert.notEqual(update.sha,source);
    assert.ok(env.writes.findIndex(x=>x[0]==='update') < env.writes.findIndex(x=>x[0]==='ci'));
  }
  assert.equal(new Set(messages).size,3);
});
test('conflicts, unexpected snapshots and failed dispatch never enable automatic merging',async()=>{
  for(const failure of ['conflict','snapshot','dispatch']) {
    const env=environment();
    if(failure==='conflict') env.github.rest.repos.merge=async()=>{throw {status:409};};
    if(failure==='snapshot') env.github.rest.repos.getCommit=async()=>({data:{sha:'unrelated',parents:[]}});
    if(failure==='dispatch') env.github.rest.actions.createWorkflowDispatch=async()=>{throw {status:403};};
    await assert.rejects(syncOne(env,'main',source,'dev'));
    assert.ok(!env.writes.some(x=>x[0]==='queue'));
  }
});
test('already queued PR is left running without duplicate dispatch',async()=>{
  const env=environment();env.pr.auto_merge={};
  env.github.paginate=async route=>route===env.github.rest.pulls.list?[env.pr]:[];
  assert.equal(await syncOne(env,'main',source,'dev'),'queued');
  assert.ok(!env.writes.some(x=>x[0]==='ci'));
});
test('reconciliation checks all three branches against latest main',async()=>{
  const env=environment('identical'),refs=[];
  env.github.rest.git.getRef=async ({ref})=>{refs.push(ref);return {data:{object:{sha:source}}};};
  await synchronize(env);
  assert.deepEqual(refs,['heads/main','heads/beta','heads/content','heads/dev']);
});
test('real Git snapshot retains development and published source ancestry',async()=>{
  const {mkdtempSync,writeFileSync,rmSync}=require('node:fs');
  const {tmpdir}=require('node:os');const {join}=require('node:path');
  const {execFileSync}=require('node:child_process');
  const dir=mkdtempSync(join(tmpdir(),'f1-sync-'));
  const git=(...args)=>execFileSync('git',args,{cwd:dir,encoding:'utf8',stdio:['pipe','pipe','pipe']}).trim();
  try {
    git('init','-b','dev');git('config','user.name','CI test');git('config','user.email','ci@example.invalid');
    writeFileSync(join(dir,'base'),'base');git('add','.');git('commit','-m','base');git('branch','main');
    writeFileSync(join(dir,'development'),'later work');git('add','.');git('commit','-m','development');const target=git('rev-parse','HEAD');
    git('checkout','main');writeFileSync(join(dir,'release'),'published');git('add','.');git('commit','-m','published');const published=git('rev-parse','HEAD');
    const env=environment();
    env.github.rest.git.getRef=async()=>({data:{object:{sha:target}}});
    env.github.rest.git.createRef=async({ref,sha})=>git('update-ref',ref,sha);
    env.github.rest.repos.getCommit=async({ref})=>({data:{sha:git('rev-parse',ref)}});
    env.github.rest.repos.merge=async({base,head})=>{git('checkout',base);git('merge','--no-ff',head,'-m','preserve target');};
    env.github.rest.pulls.create=async({head})=>{
      git('merge-base','--is-ancestor',target,head);git('merge-base','--is-ancestor',published,head);
      env.pr.head.sha=git('rev-parse',head);env.pr.base.sha=target;
      return {data:env.pr};
    };
    await syncOne(env,'main',published,'dev');
    assert.equal(git('rev-parse','dev'),target);
  } finally {rmSync(dir,{recursive:true,force:true});}
});
