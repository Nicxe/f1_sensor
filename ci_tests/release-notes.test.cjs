'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {commitsBetween, generateNotes} = require('../.github/scripts/release-notes.cjs');
const config = require('../release.config.cjs');
const [, notesOptions] = config.plugins.find(plugin => Array.isArray(plugin)
  && plugin[0] === './.github/scripts/release-notes.cjs');

function repository(t) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'f1-rc-notes-'));
  t.after(() => fs.rmSync(cwd, {recursive: true, force: true}));
  const env = {...process.env, RELEASE_CONTRIBUTORS: '[]',
    GIT_AUTHOR_DATE: '2026-01-01T12:00:00Z', GIT_COMMITTER_DATE: '2026-01-01T12:00:00Z'};
  const git = args => execFileSync('git', args, {cwd, env, encoding: 'utf8'}).trim();
  git(['init', '--quiet']);
  git(['config', 'user.name', 'Release fixture']);
  git(['config', 'user.email', 'release-fixture@example.invalid']);
  const commit = message => {
    git(['commit', '--quiet', '--allow-empty', '-m', message]);
    return git(['rev-parse', 'HEAD']);
  };
  const context = (version, previous) => ({
    cwd, env, logger: {log() {}},
    options: {repositoryUrl: 'https://github.com/Nicxe/f1_sensor.git'},
    commits: commitsBetween(previous, 'HEAD', {cwd, env}),
    lastRelease: previous ? {gitTag: previous, gitHead: previous, version: previous.slice(1)} : {},
    nextRelease: {gitTag: `v${version}`, gitHead: git(['rev-parse', 'HEAD']), version, channel: 'beta'}
  });
  commit('feat: Original stable behavior');
  git(['tag', 'v1.0.0']);
  return {git, commit, context};
}

test('every RC renders the complete stable-to-candidate list while beta stays incremental', async t => {
  const fixture = repository(t);
  fixture.commit('feat(integration): Add scheduled laps');
  fixture.git(['tag', 'v1.1.0-beta.1']);
  fixture.commit('fix(card): Correct timing gaps');
  fixture.git(['tag', 'v1.1.0-beta.2']);

  const beta = await generateNotes(notesOptions, fixture.context('1.1.0-beta.2', 'v1.1.0-beta.1'));
  assert.match(beta, /Correct timing gaps/);
  assert.doesNotMatch(beta, /Add scheduled laps/);
  assert.match(beta, /\*\*beta release\*\*/);

  const firstContext = fixture.context('1.1.0-rc.1', 'v1.1.0-beta.2');
  const originalCommits = firstContext.commits;
  const originalLastRelease = firstContext.lastRelease;
  const first = await generateNotes(notesOptions, firstContext);
  assert.match(first, /Add scheduled laps/);
  assert.match(first, /Correct timing gaps/);
  assert.match(first, /\*\*release candidate\*\*/);
  assert.match(first, /all changes since the previous stable release/);
  assert.doesNotMatch(first, /Original stable behavior|\*\*beta release\*\*/);
  assert.strictEqual(firstContext.commits, originalCommits, 'notes must not alter version-analysis commits');
  assert.strictEqual(firstContext.lastRelease, originalLastRelease, 'notes must not alter version selection');

  fixture.git(['tag', 'v1.1.0-rc.1']);
  fixture.commit('fix(integration): Preserve session weather');
  const nextContext = fixture.context('1.1.0-rc.2', 'v1.1.0-rc.1');
  const second = await generateNotes(notesOptions, nextContext);
  const repeated = await generateNotes(notesOptions, nextContext);
  for (const change of ['Add scheduled laps', 'Correct timing gaps', 'Preserve session weather']) {
    assert.match(second, new RegExp(change));
    assert.equal(second.split(change).length - 1, 1, 'each change is listed once');
  }
  assert.equal(repeated, second, 'a fresh render must retain changes after an earlier render');
  assert.match(second, /### New features/);
  assert.match(second, /### Bug fixes/);
  assert.match(second, /GitHub Sponsors/);
  assert.match(second, /github\/downloads\/Nicxe\/f1_sensor\/v1\.1\.0-rc\.2/);
});

test('cumulative RC notes omit reverted features and internal-only changes', async t => {
  const fixture = repository(t);
  const reverted = fixture.commit('feat: Add experimental timing');
  fixture.git(['tag', 'v1.1.0-beta.1']);
  fixture.commit(`Revert "feat: Add experimental timing"\n\nThis reverts commit ${reverted}.`);
  fixture.commit('chore: Refresh the internal build cache');
  fixture.commit('fix(integration): Restore race status\n\nPreserve the latest status during reconnects.\n\nFixes #123');
  const notes = await generateNotes(notesOptions, fixture.context('1.1.0-rc.1', 'v1.1.0-beta.1'));
  assert.doesNotMatch(notes, /experimental timing|internal build cache|Original stable behavior/);
  assert.match(notes, /Restore race status/);
  assert.match(notes, /Preserve the latest status during reconnects/);
  assert.match(notes, /Fixes/);
  assert.match(notes, /123/);
});

test('RC comparison metadata uses the stable baseline instead of the previous candidate', async t => {
  const fixture = repository(t);
  fixture.commit('feat: Add driver information');
  fixture.git(['tag', 'v1.1.0-rc.1']);
  fixture.commit('fix: Correct driver information');
  const options = {createOptions() {
    const renderer = notesOptions.createOptions();
    renderer.writerOpts.mainTemplate =
      '[Compare]({{host}}/{{owner}}/{{repository}}/compare/{{previousTag}}...{{currentTag}})\n'
      + renderer.writerOpts.mainTemplate;
    return renderer;
  }};
  const notes = await generateNotes(options, fixture.context('1.1.0-rc.2', 'v1.1.0-rc.1'));
  assert.match(notes, /compare\/v1\.0\.0\.\.\.v1\.1\.0-rc\.2/);
  assert.doesNotMatch(notes, /compare\/v1\.1\.0-rc\.1/);
});

test('the next RC cycle uses the latest reachable stable baseline', async t => {
  const fixture = repository(t);
  fixture.commit('feat: First release feature');
  fixture.git(['tag', 'v1.1.0-rc.1']);
  fixture.git(['tag', 'v1.1.0']);
  fixture.commit('feat: Next release feature');
  fixture.git(['tag', 'v1.2.0-beta.1']);
  fixture.commit('fix: Correct next release feature');
  const notes = await generateNotes(notesOptions, fixture.context('1.2.0-rc.1', 'v1.2.0-beta.1'));
  assert.match(notes, /Next release feature/);
  assert.match(notes, /Correct next release feature/);
  assert.doesNotMatch(notes, /First release feature|Original stable behavior/);
});

test('stable release notes omit both testing notices while preserving branding and editorial', async t => {
  const fixture = repository(t);
  fixture.commit('feat: Add stable session details');
  const notes = await generateNotes(notesOptions, fixture.context('1.1.0', 'v1.0.0'));
  assert.match(notes, /Add stable session details/);
  assert.doesNotMatch(notes, /\*\*beta release\*\*|\*\*release candidate\*\*|all changes since the previous stable release/);
  assert.match(notes, /Enjoying \*\*F1 Sensor\*\*/);
  assert.match(notes, /GitHub Sponsors/);
  assert.match(notes, /github\/downloads\/Nicxe\/f1_sensor\/v1\.1\.0/);
  assert.match(notes, /<!-- release-editorial:start -->/);
  assert.match(notes, /<!-- release-editorial:end -->/);
});
