import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import test from 'node:test';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const configUrl = pathToFileURL(path.join(root, 'docusaurus.config.js')).href;

function loadConfig(channel, baseUrl) {
  const script = `
    import config from ${JSON.stringify(configUrl)};
    const channelLink = config.themeConfig.navbar.items.find(
      (item) => item.label === 'Beta docs' || item.label === 'Stable docs',
    );
    console.log(JSON.stringify({
      baseUrl: config.baseUrl,
      announcement: config.themeConfig.announcementBar?.content,
      channelLink,
      editUrl: config.presets[0][1].docs.editUrl({docPath: 'cards/modular.md'}),
    }));
  `;
  return JSON.parse(execFileSync(
    process.execPath,
    ['--input-type=module', '--eval', script],
    {
      cwd: root,
      encoding: 'utf8',
      env: {
        ...process.env,
        F1_DOCS_BASE_URL: baseUrl,
        F1_DOCS_CHANNEL: channel,
        F1_DOCS_VERSION: channel === 'beta' ? '5.7.0-beta.1' : '5.6.0',
      },
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
