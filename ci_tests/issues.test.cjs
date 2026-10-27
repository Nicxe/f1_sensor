const {test} = require('node:test');
const assert = require('node:assert/strict');
const {extractField, versionState, componentLabels, dashboardCardVersion, releaseIssues} = require('../.github/scripts/issue-fields.cjs');
const releaseComment = require('../.github/scripts/release-comment.cjs');
const {upsertComment, ensureLabel, removeLabel, updateIssue, releasedIssues} = require('../.github/scripts/issue-automation.cjs');

test('release comments use all pages and never duplicate an earlier bot comment', async () => {
  let writes = 0;
  const github = {paginate: async () => [...Array.from({length:100}, () => ({body:'user reply', user:{login:'person'}})), {id:101, body:'<!-- marker -->\nmessage', user:{login:'github-actions[bot]'}}], rest:{issues:{listComments(){}, createComment:async()=>writes++, updateComment:async()=>writes++}}};
  await upsertComment(github, {}, '<!-- marker -->', 'message');
  assert.equal(writes, 0);
});

test('stable release comments are not confused with a beta URL prefix', async () => {
  const created = [], removed = [];
  const github = {
    paginate: async () => [{
      id: 1,
      body: 'This feature has been implemented in https://github.com/Nicxe/f1_sensor/releases/tag/v5.6.0-beta.1',
      user: {login:'github-actions[bot]'},
    }],
    rest: {issues: {
      get: async () => ({data: {
        title: '[Feature]: optional cards',
        body: '### Component\n\nIntegration',
        labels: [{name:'In BETA-testing'}, {name:'enhancement'}],
      }}),
      removeLabel: async ({name}) => removed.push(name),
      listComments() {},
      createComment: async ({body}) => created.push(body),
      updateComment: async () => assert.fail('stable release must create its own comment'),
    }},
  };
  const context = {
    repo: {owner:'Nicxe', repo:'f1_sensor'},
    payload: {release: {
      id: 2,
      draft: false,
      prerelease: false,
      tag_name: 'v5.6.0',
      html_url: 'https://github.com/Nicxe/f1_sensor/releases/tag/v5.6.0',
      body: 'Fixes #705.',
    }},
  };

  await releasedIssues({github, context});

  assert.deepEqual(removed, ['In BETA-testing']);
  assert.equal(created.length, 1);
  assert.match(created[0], /<!-- f1-release:2 -->/);
  assert.match(created[0], /v5\.6\.0/);
  assert.doesNotMatch(created[0], /beta\.1/);
});

test('manual backfills use the supplied issues even when the published notes lack references', async () => {
  const fetched = [], labels = [], comments = [];
  const github = {
    paginate: async () => [],
    rest: {issues: {
      get: async ({issue_number}) => {
        fetched.push(issue_number);
        return {data: {title: '[Bug]: session state', body: '', labels: []}};
      },
      getLabel: async () => ({data: {}}),
      addLabels: async ({issue_number, labels: next}) => labels.push({issue_number, labels: next}),
      listComments() {},
      createComment: async ({issue_number, body}) => comments.push({issue_number, body}),
      updateComment: async () => assert.fail('a backfill should create its release comment'),
    }},
  };
  const context = {repo: {owner:'Nicxe', repo:'f1_sensor'}, payload: {}};
  const release = {
    id: 3,
    draft: false,
    prerelease: true,
    tag_name: 'v5.8.0-beta.3',
    html_url: 'https://github.com/Nicxe/f1_sensor/releases/tag/v5.8.0-beta.3',
    body: 'No issue reference was rendered.',
  };

  await releasedIssues({github, context}, {release, issueNumbers: [829]});

  assert.deepEqual(fetched, [829]);
  assert.deepEqual(labels, [{issue_number: 829, labels: ['In BETA-testing']}]);
  assert.equal(comments.length, 1);
  assert.match(comments[0].body, /v5\.8\.0-beta\.3/);
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
  assert.equal(dashboardCardVersion('### Dashboard Card Version\n\nModular F1 Sensor Live Data Card'), 'modular');
  assert.equal(dashboardCardVersion('### Dashboard Card Version\n\nLegacy standalone F1 Sensor card (deprecated)'), 'legacy');
  assert.equal(componentLabels('### Component\n\nNew modular Live Data Card').includes('card'), true);
  assert.equal(componentLabels('### Component\n\nLegacy standalone F1 Sensor card (deprecated)').includes('card'), true);
  assert.equal(dashboardCardVersion('### Component\n\nNew modular Live Data Card'), 'modular');
  assert.equal(dashboardCardVersion('### Component\n\nLegacy standalone F1 Sensor card (deprecated)'), 'legacy');
  assert.equal(dashboardCardVersion('### Dashboard Card Version\n\nNot sure'), 'unknown');
});

test('legacy card reports receive migration guidance', async () => {
  const comments = [];
  const github = {
    paginate: async () => [],
    rest: {issues: {
      get: async () => ({data: {
        body: '### Component\n\nLegacy standalone F1 Sensor card (deprecated)',
        labels: [],
      }}),
      getLabel: async () => ({data: {}}),
      addLabels: async () => {},
      listComments() {},
      createComment: async ({body}) => comments.push(body),
    }},
  };
  const context = {
    repo: {owner:'Nicxe', repo:'f1_sensor'},
    payload: {issue: {number: 42}},
  };

  await updateIssue({github, context}, 'component');

  assert.equal(comments.length, 1);
  assert.match(comments[0], /<!-- f1-deprecated-card -->/);
  assert.match(comments[0], /\[new modular F1 Sensor Live Data Card\]\(https:\/\/nicxe\.github\.io\/f1_sensor\/cards\/modular-migration\)/);
});

test('only older stable versions are outdated', () => {
  for (const [value, expected] of [['5.3.0','outdated-version'], ['v5.4.0','current'], ['5.5.0','newer'], ['unknown','unknown'], ['5.5.0-beta.2','beta'], ['v5.5.0-rc.1','beta'], ['5.5.0-rc.2+local','beta'], ['5.4.0+local','current'], ['5.4.0-dev','unknown']]) {
    assert.equal(versionState(value, 'v5.4.0'), expected, value);
  }
});

test('beta and RC issue reports retain preview labeling and update guidance for the reported stage', async () => {
  for (const [version, stage] of [['6.1.0-beta.3', 'beta'], ['6.1.0-rc.1', 'release candidate']]) {
    const added = [], removed = [], updated = [];
    const issue = {number: 42, labels: ['bug', 'beta', 'outdated-version'],
      body: `### F1 Sensor Version\n\n${version}\n\n### Component\n\nLive data card`};
    const github = {
      paginate: async () => [{id: 9, body: '<!-- f1-version-check -->\nEarlier beta guidance', user: {login: 'github-actions[bot]'}}],
      rest: {
        repos: {getLatestRelease: async () => ({data: {tag_name: 'v6.0.0'}})},
        issues: {
          get: async () => ({data: issue}),
          getLabel: async () => ({data: {}}),
          addLabels: async ({labels}) => added.push(...labels),
          removeLabel: async ({name}) => removed.push(name),
          listComments() {},
          createComment: async () => assert.fail('Updating the reported stage should reuse the existing comment'),
          updateComment: async ({body}) => updated.push(body)
        }
      }
    };
    await updateIssue({github, context: {repo: {owner: 'Nicxe', repo: 'f1_sensor'}, payload: {issue}}}, 'version');
    assert.deepEqual(added, ['beta']);
    assert.deepEqual(removed, ['outdated-version']);
    assert.equal(updated.length, 1);
    assert.match(updated[0], new RegExp(`Thanks for testing the ${stage}`));
    assert.match(updated[0], /a pre-release version/);
    assert.match(updated[0], /reload your browser/);
    assert.match(updated[0], /choose the stable version/);
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

test('published release candidates identify the final testing stage and retain HACS and card instructions', () => {
  for (const title of ['[Bug]: card', '[Feature]: card']) {
    const issue = {title, body:'### Component\n\nLive data card', labels:[]};
    const release = {tag_name:'v6.1.0-rc.1', html_url:'https://example.test/release', prerelease:true};
    const comment = releaseComment(issue, release);
    assert.match(comment, /a release candidate of F1 Sensor/);
    assert.match(comment, /To test the release candidate/);
    assert.match(comment, /Show beta versions/);
    assert.match(comment, /reload your browser/);
    assert.match(comment, /feedback on the release candidate/);
  }
});

test('foreign Markdown link labels cannot become local issue references',()=>{
  assert.deepEqual(releaseIssues('[#42](https://github.com/another/project/issues/42) and [#43](https://github.com/Nicxe/f1_sensor/pull/43) and [#44](https://github.com/Nicxe/f1_sensor/issues/44)', 'Nicxe/f1_sensor'), [44]);
});
