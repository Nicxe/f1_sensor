'use strict';

// Audit runs intentionally do not install project dependencies. Use the exact
// same maintained semver implementation as the pinned npm performing the audit.
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');

function auditSemver(npmCli, expectedVersion) {
  const cli = fs.realpathSync(npmCli);
  const manifest = JSON.parse(fs.readFileSync(path.resolve(cli, '../../package.json'), 'utf8'));
  if (manifest.name !== 'npm' || manifest.version !== expectedVersion) {
    throw new Error(`Audit requires npm ${expectedVersion}; found ${manifest.name}@${manifest.version}`);
  }
  return createRequire(cli)('semver');
}

function matchRanges(records, semver) {
  if (!Array.isArray(records)) throw new Error('Audit version evidence must be an array');
  // Match @npmcli/metavuln-calculator's advisory evaluation, including beta
  // dependencies which are not exempt from vulnerable ranges.
  const options = {includePrerelease: true, loose: true};
  return records.map(({version, range}) => {
    if (typeof version !== 'string' || !semver.valid(version, options) ||
        typeof range !== 'string' || !range.trim() || !semver.validRange(range, options)) {
      throw new Error('Audit version evidence contains an invalid version or advisory range');
    }
    return semver.satisfies(version, range, options);
  });
}

if (require.main === module) {
  try {
    const records = JSON.parse(fs.readFileSync(0, 'utf8'));
    process.stdout.write(JSON.stringify(matchRanges(records, auditSemver(process.argv[2], process.argv[3]))));
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = {auditSemver, matchRanges};
