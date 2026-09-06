const {test} = require('node:test');
const assert = require('node:assert/strict');
const {enable, eligible} = require('../.github/scripts/auto-merge.cjs');
const rules = [
  {type:'pull_request'},
  {type:'required_status_checks', parameters:{strict_required_status_checks_policy:true,
    required_status_checks:[{context:'CI required', integration_id:15368}]}},
];
const pr = {number:1, node_id:'PR_1', state:'open', draft:false, head:{sha:'head'}, base:{ref:'main', sha:'base'}};

test('main requires an open security advisory; ordinary dev updates retain patch/minor policy', () => {
  assert.equal(eligible('main', {alert:'OPEN', ghsa:'GHSA-5qpg-rh4j-qp35'}), true);
  for (const alert of ['', 'FIXED', 'DISMISSED']) assert.equal(eligible('main', {alert,ghsa:'GHSA-1234'}),false);
  assert.equal(eligible('main', {alert:'OPEN',ghsa:''}),false);
  assert.equal(eligible('dev', {update:'version-update:semver-minor'}),true);
  assert.equal(eligible('dev', {update:'version-update:semver-major'}),false);
  assert.equal(eligible('beta', {alert:'OPEN',ghsa:'GHSA-1234'}),false);
});

test('automatic merging requires strict app-bound checks and an unchanged PR', async () => {
  const calls=[];
  const env={context:{repo:{owner:'Nicxe',repo:'f1_sensor'}},github:{
    paginate:async()=>rules,
    rest:{pulls:{get:async()=>({data:pr})}},
    graphql:async(query,variables)=>calls.push({query,variables}),
  }};
  await enable(env,pr);
  assert.equal(calls[0].variables.head,'head');
  assert.match(calls[0].query,/mergeMethod:MERGE/);
  for(const changed of [[],rules.slice(1),[rules[0]],
    [rules[0],{...rules[1],parameters:{...rules[1].parameters,strict_required_status_checks_policy:false}}],
    [rules[0],{...rules[1],parameters:{...rules[1].parameters,required_status_checks:[{context:'CI required',integration_id:1}]}}]]) {
    env.github.paginate=async()=>changed;
    await assert.rejects(enable(env,pr));
  }
  env.github.paginate=async()=>rules;
  for(const changed of [{draft:true},{state:'closed'},{head:{sha:'new'}},{base:{ref:'main',sha:'new'}}]) {
    env.github.rest.pulls.get=async()=>({data:{...pr,...changed}});
    await assert.rejects(enable(env,pr));
  }
  assert.equal(calls.length,1);
});

test('every dependency commit is checked, not just the first signed commit',async()=>{
  const {verifyDependabot}=require('../.github/scripts/auto-merge.cjs');
  const signed={author:{login:'dependabot[bot]'},commit:{verification:{verified:true}}};
  let commits=[signed];
  const env={context:{repo:{}},github:{paginate:async()=>commits,rest:{pulls:{listCommits(){}},repos:{compareCommits:async()=>({data:{status:'ahead'}})}}}};
  const dependency={...pr,user:{login:'dependabot[bot]'},head:{repo:{full_name:'own/repo'}},base:{sha:'base',repo:{full_name:'own/repo'}}};
  await verifyDependabot(env,dependency);
  commits=[signed,{...signed,author:{login:'someone-else'}}];
  await assert.rejects(verifyDependabot(env,dependency));
  commits=[signed,{...signed,author:{login:'github-actions[bot]'},parents:[{sha:'head'},{sha:'base'}]}];
  await verifyDependabot(env,dependency);
  env.github.rest.repos.compareCommits=async()=>({data:{status:'diverged'}});
  await assert.rejects(verifyDependabot(env,dependency));
});

test('a behind dependency PR refreshes its exact head and explicitly restarts CI',async()=>{
  const {refresh}=require('../.github/scripts/auto-merge.cjs');
  const calls=[];let refreshed=false;
  const env={context:{repo:{}},github:{rest:{pulls:{
    get:async()=>({data:{...pr,mergeable_state:'behind',head:{sha:refreshed?'new':'head'}}}),
    updateBranch:async data=>{calls.push(data);refreshed=true;},
  },actions:{createWorkflowDispatch:async data=>calls.push(data)}}}};
  await refresh(env,pr);
  assert.equal(calls[0].expected_head_sha,'head');
  assert.equal(calls[1].inputs.pull_request,'1');
  assert.equal(calls[1].ref,'main');
});

test('reopened dependency events refresh the base without trusting a changed dependency head',async()=>{
  const {queueDependabot}=require('../.github/scripts/auto-merge.cjs');
  let current={...pr,base:{ref:'main',sha:'advanced'}};
  let queued=0;
  const env={context:{repo:{}},github:{paginate:async()=>rules,
    rest:{pulls:{get:async()=>({data:current})}},graphql:async()=>queued++}};
  await queueDependabot(env,pr);
  assert.equal(queued,1);
  current={...current,head:{sha:'changed'}};
  await assert.rejects(queueDependabot(env,pr));
  assert.equal(queued,1);
});
