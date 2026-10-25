'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const root = path.resolve(__dirname, '..');

// semantic-release hooks process stdout. Run the real API outside node:test's
// worker so those hooks cannot intercept the test runner's reporting protocol.
async function dryRunInChild({root, checkout, remote, branch, createRc}) {
  const assert = require('node:assert/strict');
  const path = require('node:path');
  const {pathToFileURL} = require('node:url');
  const {Writable} = require('node:stream');
  process.chdir(checkout);
  process.env.GITHUB_REF_NAME = branch;
  process.env.CREATE_RC = String(createRc);
  const config = require(path.join(root, 'release.config.cjs'));
  const github = config.plugins.find(plugin => plugin[0] === '@semantic-release/github');
  assert.equal(github[1].draftRelease, true, 'The real config must keep manual publication');
  const analyzer = config.plugins.find(plugin => plugin[0] === '@semantic-release/commit-analyzer');
  const notes = config.plugins.find(plugin => plugin[0] === './.github/scripts/release-notes.cjs');
  assert.ok(analyzer);
  assert.ok(notes);
  const plugins = [
    [require.resolve(path.join(root, 'node_modules', analyzer[0])), analyzer[1]],
    [path.join(root, notes[0]), notes[1]]
  ];
  const log = [];
  const output = new Writable({write(chunk, encoding, callback) {
    log.push(String(chunk));
    callback();
  }});
  const {default: semanticRelease} = await import(path.join(root, 'node_modules/semantic-release/index.js'));
  try {
    const result = await semanticRelease({
      dryRun: true,
      ci: false,
      repositoryUrl: pathToFileURL(remote).href,
      tagFormat: config.tagFormat,
      branches: config.branches,
      plugins
    }, {cwd: checkout, env: process.env, stdout: output, stderr: output});
    assert.ok(result?.nextRelease, log.join(''));
    return result;
  } catch (error) {
    process.stderr.write(log.join(''));
    throw error;
  }
}

test('real semantic-release carries a beta through cumulative RCs, stable and the next beta cycle',
  {timeout: 30000}, async t => {
    const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'f1-release-cycle-'));
    const checkout = path.join(temporary, 'checkout');
    const remote = path.join(temporary, 'remote.git');
    fs.mkdirSync(checkout);
    const gitEnv = {
      PATH: process.env.PATH,
      GIT_CONFIG_NOSYSTEM: '1',
      GIT_CONFIG_GLOBAL: '/dev/null',
      GIT_TERMINAL_PROMPT: '0',
      GIT_ALLOW_PROTOCOL: 'file'
    };
    const git = (...args) => execFileSync('git', args, {
      cwd: checkout, env: gitEnv, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']
    }).trim();
    t.after(() => fs.rmSync(temporary, {recursive: true, force: true}));
    git('init', '--bare', '--initial-branch=main', remote);
    git('init', '--initial-branch=main');
    git('config', 'user.name', 'Release cycle test');
    git('config', 'user.email', 'release-cycle@example.invalid');
    git('remote', 'add', 'origin', pathToFileURL(remote).href);
    let content = 0;
    const commit = message => {
      fs.writeFileSync(path.join(checkout, 'content.txt'), `${++content}\n`);
      git('add', 'content.txt');
      git('commit', '-m', message);
      return git('rev-parse', 'HEAD');
    };
    const tag = (name, channel) => {
      git('tag', name);
      git('notes', '--ref', `semantic-release-${name}`, 'add', '-m',
        JSON.stringify({channels: [channel]}), name);
    };
    const push = () => {
      git('push', 'origin', 'main', 'beta', '--tags');
      git('push', 'origin', 'refs/notes/*:refs/notes/*');
    };

    commit('feat: Initial stable release');
    tag('v6.0.0', null);
    git('switch', '-c', 'beta');
    commit('feat: Add candidate timing view');
    tag('v6.1.0-beta.1', 'beta');
    const finalBetaHead = commit('fix: Correct candidate gap formatting');
    tag('v6.1.0-beta.2', 'beta');
    push();

    const run = async ({branch='beta', createRc=false}={}) => {
      const tagsBefore = git('tag');
      const script = `(${dryRunInChild.toString()})(JSON.parse(process.argv[1]))
        .then(result => process.stdout.write(JSON.stringify(result)))
        .catch(error => { process.stderr.write(String(error.stack || error)); process.exitCode = 1; });`;
      const result = JSON.parse(execFileSync(process.execPath, ['-e', script,
        JSON.stringify({root, checkout, remote, branch, createRc})], {
        cwd: checkout, env: gitEnv, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']
      }));
      assert.equal(git('tag'), tagsBefore, 'Dry-run must not create release tags');
      return result;
    };

    const firstRc = await run({createRc: true});
    assert.equal(firstRc.nextRelease.version, '6.1.0-rc.1');
    assert.equal(firstRc.nextRelease.gitHead, finalBetaHead,
      'RC creation must work on the exact already-tagged final beta commit');
    assert.equal(firstRc.lastRelease.gitTag, 'v6.0.0');
    assert.match(firstRc.nextRelease.notes, /Add candidate timing view/);
    assert.match(firstRc.nextRelease.notes, /Correct candidate gap formatting/);
    assert.match(firstRc.nextRelease.notes, /release candidate/);
    assert.match(firstRc.nextRelease.notes, /all changes since the previous stable release/);
    tag(firstRc.nextRelease.gitTag, 'beta');

    commit('fix: Keep candidate radio playback available');
    push();
    const secondRc = await run();
    assert.equal(secondRc.nextRelease.version, '6.1.0-rc.2');
    assert.equal(secondRc.lastRelease.gitTag, 'v6.1.0-rc.1');
    for (const change of ['Add candidate timing view', 'Correct candidate gap formatting',
      'Keep candidate radio playback available']) {
      assert.ok(secondRc.nextRelease.notes.includes(change), change);
      assert.equal(secondRc.nextRelease.notes.split(change).length - 1, 1,
        'Each change should appear once in the complete RC list');
    }
    tag(secondRc.nextRelease.gitTag, 'beta');
    push();

    git('switch', 'main');
    git('merge', '--no-ff', 'beta', '-m', 'Merge beta into main');
    push();
    const stable = await run({branch: 'main'});
    assert.equal(stable.nextRelease.version, '6.1.0');
    assert.match(stable.nextRelease.notes, /Add candidate timing view/);
    assert.match(stable.nextRelease.notes, /Keep candidate radio playback available/);
    tag(stable.nextRelease.gitTag, null);
    push();

    git('switch', 'beta');
    git('merge', '--no-ff', 'main', '-m', 'Merge stable history into beta');
    commit('feat: Add next cycle session summary');
    push();
    const nextBeta = await run();
    assert.equal(nextBeta.nextRelease.version, '6.2.0-beta.1');
    assert.equal(nextBeta.lastRelease.gitTag, 'v6.1.0');
    assert.match(nextBeta.nextRelease.notes, /Add next cycle session summary/);
    assert.doesNotMatch(nextBeta.nextRelease.notes, /Add candidate timing view/);
    assert.doesNotMatch(nextBeta.nextRelease.notes, /Keep candidate radio playback available/);
  });
