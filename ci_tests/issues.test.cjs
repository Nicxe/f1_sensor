const {test} = require('node:test');
const assert = require('node:assert/strict');
const {extractField, versionState, componentLabels, releaseIssues} = require('../.github/scripts/issue-fields.cjs');
const releaseComment = require('../.github/scripts/release-comment.cjs');
const {upsertComment, ensureLabel, removeLabel} = require('../.github/scripts/issue-automation.cjs');

test('release comments use all pages and never duplicate an earlier bot comment', async () => {
  let writes = 0;
  const github = {paginate: async () => [...Array.from({length:100}, () => ({body:'user reply', user:{login:'person'}})), {id:101, body:'<!-- marker -->\nmessage', user:{login:'github-actions[bot]'}}], rest:{issues:{listComments(){}, createComment:async()=>writes++, updateComment:async()=>writes++}}};
  await upsertComment(github, {}, '<!-- marker -->', 'message');
  assert.equal(writes, 0);
});

test('permissions and service errors are not silently swallowed', async () => {
  for (const status of [403, 503]) {
    const github = {rest:{issues:{getLabel:async()=>{throw {status};}, removeLabel:async()=>{throw {status};}}}};
    await assert.rejects(ensureLabel(github, {}, 'beta', 'fff'), e => e.status === status);
    await assert.rejects(removeLabel(github, {}, 'beta'), e => e.status === status);
  }
  await removeLabel({rest:{issues:{removeLabel:async()=>{throw {status:404};}}}}, {}, 'beta');
});

test('issue form fields support CRLF, hashes and empty responses', () => {
  assert.equal(extractField('### Component\r\n\r\nBoth integration and card\r\n\r\n### Logs\r\nfoo #1', 'Component'), 'Both integration and card');
  assert.equal(extractField('### Logs\n\nfoo #1', 'Logs'), 'foo #1');
  assert.equal(extractField('### Component\n\n_No response_', 'Component'), '');
  assert.deepEqual(componentLabels('### Component\n\nBoth integration and card'), ['integration', 'card']);
});

test('only older stable versions are outdated', () => {
  for (const [value, expected] of [['5.3.0','outdated-version'], ['v5.4.0','current'], ['5.5.0','newer'], ['unknown','unknown'], ['5.5.0-beta.2','beta'], ['5.4.0+local','current'], ['5.4.0-dev','unknown']]) {
    assert.equal(versionState(value, 'v5.4.0'), expected, value);
  }
});

test('release references never notify a same-number issue in a different repo', () => {
  assert.deepEqual(releaseIssues('Fixes #12, other/repo#13, Nicxe/f1_sensor#14 https://github.com/other/repo/issues/15 https://github.com/Nicxe/f1_sensor/issues/16 https://github.com/Nicxe/f1_sensor/pull/17 #12', 'Nicxe/f1_sensor'), [16,14,12]);
});

test('published beta and stable instructions retain user guidance', () => {
  const issue = {title:'[Bug]: card', body:'### Component\n\nLive data card', labels:[]};
  const release = {tag_name:'v5.5.0-beta.2', html_url:'https://example.test/release', prerelease:true};
  assert.match(releaseComment(issue, release), /BETA pre-release/);
  assert.match(releaseComment(issue, release), /reload your browser/);
  release.prerelease = false;
  assert.match(releaseComment(issue, release), /latest stable release/);
});
