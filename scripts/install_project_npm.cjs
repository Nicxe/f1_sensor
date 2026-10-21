'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');

function installProjectNpm({cwd = process.cwd(), execute = spawnSync} = {}) {
  const {packageManager} = JSON.parse(fs.readFileSync(path.join(cwd, 'package.json'), 'utf8'));
  if (typeof packageManager !== 'string' || !/^npm@\d+\.\d+\.\d+$/.test(packageManager)) {
    throw new Error('package.json must declare an exact npm version in packageManager.');
  }
  const result = execute('npm', ['install', '--global', packageManager, '--no-audit', '--no-fund'], {cwd, stdio: 'inherit'});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Installing ${packageManager} failed (${result.signal || result.status}).`);
}

if (require.main === module) installProjectNpm();
module.exports = {installProjectNpm};
