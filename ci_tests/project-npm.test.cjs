const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const yaml = require('js-yaml');
const {installProjectNpm} = require('../scripts/install_project_npm.cjs');

function temporaryPackage(t, packageManager) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'f1-project-npm-'));
  t.after(() => fs.rmSync(directory, {recursive: true}));
  fs.writeFileSync(path.join(directory, 'package.json'), JSON.stringify({packageManager}));
  return directory;
}

test('the declared exact npm version is consumed without a matching workflow edit', t => {
  for (const version of ['npm@10.9.8', 'npm@11.7.0']) {
    const cwd = temporaryPackage(t, version);
    const calls = [];
    installProjectNpm({cwd, execute: (...args) => {calls.push(args); return {status: 0};}});
    assert.deepEqual(calls, [['npm', ['install', '--global', version, '--no-audit', '--no-fund'], {cwd, stdio: 'inherit'}]]);
  }
});

test('missing, ranged or non-npm declarations cannot silently select another package or version', t => {
  for (const invalid of [undefined, 'npm@latest', 'npm@^10.0.0', 'pnpm@10.0.0', 'npm@10.0.0;echo secret']) {
    const cwd = temporaryPackage(t, invalid);
    assert.throws(() => installProjectNpm({cwd, execute() {throw new Error('must not install');}}), /must declare an exact npm/);
  }
  const cwd = temporaryPackage(t, 'npm@10.9.8');
  assert.throws(() => installProjectNpm({cwd, execute: () => ({status: 1})}), /Installing npm@10.9.8 failed/);
});

test('check and release wrappers consume the checkout Node and npm pins', () => {
  const workflow = name => yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows', name), 'utf8'));
  for (const name of ['frontend.yml', 'translations.yml', 'automation-tests.yml', 'audit.yml', 'release.yml']) {
    const job = Object.values(workflow(name).jobs)[0];
    const node = job.steps.find(step => step.uses?.startsWith('actions/setup-node@'));
    assert.equal(node.with['node-version-file'], '.node-version', name);
    assert.ok(job.steps.some(step => step.run === 'node scripts/install_project_npm.cjs'), name);
  }
  const docs = workflow('documentation.yml').jobs.documentation;
  const install = docs.steps.find(step => step.run === 'node scripts/install_project_npm.cjs');
  assert.equal(install['working-directory'], 'tested');
  assert.equal(docs.steps.find(step => step.uses?.startsWith('actions/setup-node@')).with['node-version-file'], 'tested/.node-version');
  const build = workflow('deploy.yml').jobs.build;
  for (const channel of ['stable', 'beta']) {
    const setup = build.steps.find(step => step.with?.['node-version-file'] === '${{ steps.runtime.outputs.' + channel + '_version_file }}');
    const execute = build.steps.find(step => step['working-directory'] === `${channel}-docs`);
    assert.ok(setup, channel);
    assert.match(execute.run, /^node \.\.\/publication-tools\/scripts\/install_project_npm\.cjs\nnpm ci/m);
    assert.ok(build.steps.indexOf(setup) < build.steps.indexOf(execute));
  }
  const weekly = workflow('maintenance.yml');
  assert.equal(weekly.jobs.compatibility.steps.find(step => step.run?.startsWith('pip install')).run, 'pip install --upgrade pytest-homeassistant-custom-component');
  assert.equal(weekly.jobs['minimum-compatibility'].steps.find(step => step.uses?.startsWith('actions/setup-python@')).with['python-version'], '3.12');
});

test('all shared Python check wrappers and release tooling consume the repository Python pin', () => {
  for (const name of ['frontend.yml', 'translations.yml', 'automation-tests.yml', 'audit.yml', 'release.yml', 'ci-checks.yml', 'tests.yml', 'package.yml', 'ruff.yml', 'documentation.yml']) {
    const workflow = yaml.load(fs.readFileSync(path.join(__dirname, '../.github/workflows', name), 'utf8'));
    for (const job of Object.values(workflow.jobs).filter(job => job.steps)) {
      const setup = job.steps.find(step => step.uses?.startsWith('actions/setup-python@'));
      assert.ok(setup, `${name}: no implicit runner Python version`);
      assert.equal(setup.with['python-version-file'], name === 'documentation.yml' ? 'tested/.python-version' : '.python-version', name);
    }
  }
});
