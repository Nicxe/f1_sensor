const test = require('node:test');
const assert = require('node:assert/strict');
const {matchingPull, matchingRun, route} = require('../.github/scripts/ci-routing.cjs');
const pr = {number:1,state:'open',head:{ref:'dev',sha:'a',repo:{full_name:'owner/repo'}},base:{ref:'beta'}};
const run = {event:'pull_request',path:'.github/workflows/ci.yml',head_sha:'a',pull_requests:[{number:1}],status:'in_progress',conclusion:null};
test('only the unchanged own promotion PR can replace a push run',()=>{
  assert.equal(matchingPull(pr,'owner/repo','dev','a'),true);
  assert.equal(matchingPull(pr,'owner/repo','dev','b'),false);
  assert.equal(matchingPull(pr,'fork/repo','dev','a'),false);
  assert.equal(matchingPull({...pr,state:'closed'},'owner/repo','dev','a'),false);
});
test('missing, failed, cancelled or unrelated runs never suppress push tests',()=>{
  assert.equal(matchingRun(run,pr,'a'),true);
  for(const changed of [{event:'push'},{head_sha:'b'},{pull_requests:[]},
    {status:'completed',conclusion:'failure'},{status:'completed',conclusion:'cancelled'},
    {path:'another.yml'}]) assert.equal(matchingRun({...run,...changed},pr,'a'),false);
});
test('GitHub outage falls back to testing the push',async()=>{
  const outputs={};
  await route({github:{paginate:async()=>{throw new Error('503')},rest:{pulls:{list(){}}}},
    context:{repo:{owner:'owner',repo:'repo'},ref:'refs/heads/dev',sha:'a'},
    core:{setOutput:(k,v)=>outputs[k]=v,warning(){}}});
  assert.equal(outputs.run_checks,'true');
});

test('confirmed PR verification owns the work while unconfirmed registration stays safe',async()=>{
  for (const available of [[],[run]]) {
    const outputs={};
    const summaries=[];
    const core={setOutput:(k,v)=>outputs[k]=v,warning(){},summary:{
      addRaw(text){summaries.push(text);return this;},async write(){}}};
    const github={paginate:async()=>[pr],rest:{pulls:{list(){}},actions:{
      listWorkflowRunsForRepo:async()=>({data:{workflow_runs:available}})}}};
    await route({github,core,context:{repo:{owner:'owner',repo:'repo'},ref:'refs/heads/dev',sha:'a'}});
    assert.equal(outputs.run_checks,available.length?'false':'true');
    assert.equal(summaries.length,available.length);
  }
});
