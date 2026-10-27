import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath, pathToFileURL} from 'node:url';
import yaml from 'js-yaml';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function loadConfig(channel, baseUrl, {
  directory = root,
  version = channel === 'beta' ? '5.7.0-beta.1' : '5.6.0',
} = {}) {
  const configUrl = pathToFileURL(path.join(directory, 'docusaurus.config.js')).href;
  const script = `
    import config from ${JSON.stringify(configUrl)};
    const channelLink = config.themeConfig.navbar.items.find(
      (item) => item.label === 'Beta docs' || item.label === 'Stable docs',
    );
    console.log(JSON.stringify({
      baseUrl: config.baseUrl,
      announcement: config.themeConfig.announcementBar?.content,
      channelLink,
      versionLink: config.themeConfig.navbar.items.find(
        item => item.className === 'navbar-version-chip',
      ),
      editUrl: config.presets[0][1].docs.editUrl({docPath: 'cards/modular.md'}),
    }));
  `;
  const environment = {
    ...process.env,
    F1_DOCS_BASE_URL: baseUrl,
    F1_DOCS_CHANNEL: channel,
  };
  if (version === null) delete environment.F1_DOCS_VERSION;
  else environment.F1_DOCS_VERSION = version;
  return JSON.parse(execFileSync(
    process.execPath,
    ['--input-type=module', '--eval', script],
    {
      cwd: directory,
      encoding: 'utf8',
      env: environment,
    },
  ));
}

test('stable documentation links to the beta channel', () => {
  const config = loadConfig('stable', '/f1_sensor/');

  assert.equal(config.baseUrl, '/f1_sensor/');
  assert.equal(config.announcement, undefined);
  assert.deepEqual(config.channelLink, {
    label: 'Beta docs',
    position: 'right',
    href: 'https://Nicxe.github.io/f1_sensor/beta/',
  });
  assert.match(config.editUrl, /\/edit\/content\/docs\/cards\/modular\.md$/);
});

test('beta documentation uses its nested path and beta branch', () => {
  const config = loadConfig('beta', '/f1_sensor/beta/');

  assert.equal(config.baseUrl, '/f1_sensor/beta/');
  assert.match(config.announcement, /^Beta documentation/);
  assert.deepEqual(config.channelLink, {
    label: 'Stable docs',
    position: 'right',
    href: 'https://Nicxe.github.io/f1_sensor/',
  });
  assert.match(config.editUrl, /\/edit\/beta\/docs\/cards\/modular\.md$/);
});

function git(directory, ...arguments_) {
  return execFileSync('git', arguments_, {cwd: directory, encoding: 'utf8', stdio: 'pipe'}).trim();
}

function taggedSources(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'f1-docs-versions-'));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const source = path.join(directory, 'source');
  fs.mkdirSync(source);
  git(source, 'init', '--initial-branch=main');
  fs.copyFileSync(path.join(root, 'docusaurus.config.js'), path.join(source, 'docusaurus.config.js'));
  fs.writeFileSync(path.join(source, 'package.json'), '{"type":"module"}\n');
  function commit(value) {
    fs.writeFileSync(path.join(source, 'fixture.txt'), value);
    git(source, 'add', '.');
    git(source, '-c', 'user.name=Docs fixture', '-c', 'user.email=docs@example.invalid',
      '-c', 'commit.gpgsign=false', 'commit', '-m', value);
    return git(source, 'rev-parse', 'HEAD');
  }
  commit('stable release');
  git(source, 'tag', 'v42.0.0');
  const stable = commit('untagged stable documentation');
  commit('beta release');
  git(source, 'tag', 'v42.1.0-beta.1');
  const beta = commit('untagged beta documentation');
  git(source, 'checkout', '-b', 'unrelated', stable);
  commit('unrelated newer release');
  git(source, 'tag', 'v99.0.0');
  git(source, 'checkout', 'main');
  return {directory, source, stable, beta};
}

for (const [channel, version] of [['stable', '42.0.0'], ['beta', '42.1.0-beta.1']]) {
  test(`published ${channel} keeps its pinned source version and release link`, t => {
    const fixture = taggedSources(t);
    const workflow = yaml.load(fs.readFileSync(path.join(root, '.github/workflows/deploy.yml'), 'utf8'));
    const step = workflow.jobs.build.steps.find(item => item.with?.path === `${channel}-docs`);
    assert.equal(step.with.ref, '${{ needs.refs.outputs.' + channel + '_sha }}');
    assert.equal(step.with['persist-credentials'], false);
    const checkout = path.join(fixture.directory, `${channel}-docs`);
    fs.mkdirSync(checkout);
    git(checkout, 'init');
    // Exercise checkout's fetch-depth contract with real Git, including its
    // shallow/no-tags default, rather than injecting a version into the config.
    const depth = step.with['fetch-depth'] ?? 1;
    if (depth === 0) {
      git(checkout, 'fetch', fixture.source, '+refs/heads/*:refs/remotes/origin/*', '+refs/tags/*:refs/tags/*');
    } else {
      git(checkout, 'fetch', '--depth', String(depth),
        step.with['fetch-tags'] ? '--tags' : '--no-tags', fixture.source, fixture[channel]);
    }
    git(checkout, 'checkout', '--detach', fixture[channel]);
    fs.symlinkSync(path.join(root, 'node_modules'), path.join(checkout, 'node_modules'), 'dir');
    const tree = git(fixture.source, 'rev-parse', `${fixture[channel]}^{tree}`);
    const config = loadConfig(channel, channel === 'beta' ? '/f1_sensor/beta/' : '/f1_sensor/', {
      directory: checkout,
      version: null,
    });
    assert.equal(config.versionLink.label, `v${version}`);
    assert.equal(config.versionLink.href, `https://github.com/Nicxe/f1_sensor/releases/tag/v${version}`);
    assert.equal(git(checkout, 'rev-parse', 'HEAD'), fixture[channel]);
    assert.equal(git(checkout, 'rev-parse', 'HEAD^{tree}'), tree);
  });
}
