const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const build = path.resolve(__dirname, '../build');
const files = fs.readdirSync(build, {recursive: true});
test('production documentation contains a usable local search index', () => {
  const indexes = files.filter(name => /search-index.*\.json$/.test(name));
  assert.ok(indexes.length, 'No production search index was generated');
  const content = indexes.map(name => fs.readFileSync(path.join(build, name), 'utf8')).join('\n');
  assert.match(content, /track map/i);
  for (const name of indexes) JSON.parse(fs.readFileSync(path.join(build, name), 'utf8'));
});

test('existing documentation routes and fragment links still resolve', () => {
  const baseline = require('../quality/docs-legacy-routes.json');
  for (const {path: route, anchors} of baseline.routes) {
    const file = path.join(build, route === '/' ? 'index.html' : `${route.slice(1)}.html`);
    assert.ok(fs.existsSync(file), `Missing legacy route: ${route}`);
    const html = fs.readFileSync(file, 'utf8');
    const ids = new Set([...html.matchAll(/\bid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3]));
    for (const id of anchors) assert.ok(ids.has(id), `Missing legacy anchor: ${route}#${id}`);
  }
});


test('every built document has unique IDs and resolves its local images', () => {
  for (const filename of files.filter(name => name.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(build, filename), 'utf8');
    const ids = [...html.matchAll(/\bid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3]);
    assert.equal(new Set(ids).size, ids.length, `Duplicate IDs in ${filename}`);
    for (const match of html.matchAll(/<img\b[^>]*?\bsrc=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)) {
      const src = match[1] || match[2] || match[3];
      if (!src.startsWith('/f1_sensor/')) continue;
      const relative = decodeURIComponent(src.slice('/f1_sensor/'.length).split('?')[0]);
      assert.ok(fs.existsSync(path.join(build, relative)), `${filename} has a missing image: ${src}`);
    }
  }
});

test('the Token Helper privacy policy keeps its complete contractual content', () => {
  const {createHash} = require('node:crypto');
  const source = fs.readFileSync(path.resolve(__dirname, '../docs/help/f1tv-token-helper-privacy.md'), 'utf8');
  const body = source.split('---').slice(2).join('---');
  assert.equal(createHash('sha256').update(body).digest('hex'), require('../quality/docs-legacy-routes.json').helperPrivacyBodySha256);
});
