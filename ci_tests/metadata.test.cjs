'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {routing} = require('../.github/scripts/pr-metadata.cjs');

function fixture(base, head, {fork = false, files = []} = {}) {
  const pr = {number:657, user:{login:'contributor'},
    base:{ref:base, repo:{full_name:'owner/repo'}},
    head:{ref:head, repo:{full_name:fork ? 'fork/repo' : 'owner/repo'}}};
  const calls = {files:0, comments:[]};
  const listFiles = () => {};
  const github = {
    rest:{pulls:{get:async()=>({data:pr}), listFiles}, issues:{
      listComments(){}, createComment:async({body})=>calls.comments.push(body),
    }},
    paginate:async(method)=>{
      if (method !== listFiles) return [];
      calls.files++;
      if (files instanceof Error) throw files;
      return files;
    },
  };
  return {github, calls, context:{repo:{owner:'owner',repo:'repo'}, payload:{pull_request:pr}}};
}

test('own release promotions do not request a potentially unavailable diff', async()=>{
  for (const [base, head] of [['main','beta'], ['beta','dev']]) {
    const data = fixture(base, head, {files:Object.assign(new Error('diff unavailable'), {status:422})});
    await routing(data);
    assert.equal(data.calls.files, 0);
    assert.deepEqual(data.calls.comments, []);
  }
});

test('fork branches named beta still undergo routing validation', async()=>{
  const data = fixture('main', 'beta', {fork:true, files:[{filename:'code.py'}]});
  await routing(data);
  assert.equal(data.calls.files, 1);
  assert.match(data.calls.comments[0], /Code follows/);
});

test('content routing still inspects files and previous names', async()=>{
  for (const file of [{filename:'code.py'}, {filename:'docs/page.md', previous_filename:'code.py'}]) {
    const data = fixture('content', 'contribution', {files:[file]});
    await routing(data);
    assert.equal(data.calls.files, 1);
    assert.match(data.calls.comments[0], /use dev for code/);
  }
  const data = fixture('main', 'content', {files:[{filename:'docs/page.md'}]});
  await routing(data);
  assert.equal(data.calls.files, 1);
  assert.deepEqual(data.calls.comments, []);
});

test('unavailable content diffs never produce a success message', async()=>{
  const error = Object.assign(new Error('diff unavailable'), {status:422});
  const data = fixture('content', 'contribution', {files:error});
  await assert.rejects(routing(data), error);
  assert.deepEqual(data.calls.comments, []);
});
