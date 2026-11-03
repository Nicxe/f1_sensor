const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const build = path.resolve(__dirname, '..', process.env.F1_DOCS_TEST_BUILD_DIR || 'build');
const docsPath = process.env.F1_DOCS_BASE_URL || '/f1_sensor/';
const files = fs.readdirSync(build, {recursive: true});
test('production documentation contains a usable local search index', () => {
  const indexes = files.filter(name => /search-index.*\.json$/.test(name));
  assert.ok(indexes.length, 'No production search index was generated');
  const content = indexes.map(name => fs.readFileSync(path.join(build, name), 'utf8')).join('\n');
  assert.match(content, /track map/i);
  for (const name of indexes) JSON.parse(fs.readFileSync(path.join(build, name), 'utf8'));
});

test('the module finder covers every current card module exactly once', async () => {
  const {pathToFileURL} = require('node:url');
  const {cardsCatalog} = await import(pathToFileURL(path.resolve(__dirname, '../src/data/cardsCatalog.js')));
  const {MODULES, label} = await import(pathToFileURL(path.resolve(__dirname, '../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js')));
  const html = fs.readFileSync(path.join(build, 'cards/cards-overview.html'), 'utf8');
  const start = html.indexOf('aria-label="Dashboard module catalogue"');
  assert.ok(start >= 0, 'Missing server-rendered module catalogue');
  const catalogue = html.slice(start, html.indexOf('</section>', start));
  const links = [...catalogue.matchAll(/\bhref=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3]);
  assert.deepEqual(cardsCatalog.map(entry => entry.id).sort(), Object.keys(MODULES).sort());
  for (const entry of cardsCatalog) {
    assert.equal(entry.title, label(MODULES[entry.id]), `Module name differs from the editor: ${entry.id}`);
    assert.deepEqual(entry.sources, MODULES[entry.id].sources, `Data sources differ: ${entry.id}`);
    assert.ok(links.includes(docsPath.replace(/\/$/, '') + entry.href), `Module guide missing without JavaScript: ${entry.id}`);
  }
});

for (const baselineName of ['../quality/docs-legacy-routes.json', './fixtures/reorganization-routes.json']) {
test(`existing documentation routes and fragment links still resolve (${baselineName})`, () => {
  const baseline = require(baselineName);
  for (const {path: route, anchors} of baseline.routes) {
    const file = path.join(build, route === '/' ? 'index.html' : `${route.slice(1)}.html`);
    assert.ok(fs.existsSync(file), `Missing legacy route: ${route}`);
    const html = fs.readFileSync(file, 'utf8');
    const ids = new Set([...html.matchAll(/\bid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3]));
    for (const id of anchors) assert.ok(ids.has(id), `Missing legacy anchor: ${route}#${id}`);
  }
});
}

test('published pages do not expose unparsed admonition directives', () => {
  for (const filename of files.filter(name => name.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(build, filename), 'utf8');
    assert.doesNotMatch(html, /<p[^>]*>\s*:::(?:warning|tip|info|danger)(?:\s|\[)/, filename);
  }
});


test('every built document has unique IDs and resolves its local images', () => {
  for (const filename of files.filter(name => name.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(build, filename), 'utf8');
    const ids = [...html.matchAll(/\bid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3]);
    assert.equal(new Set(ids).size, ids.length, `Duplicate IDs in ${filename}`);
    for (const match of html.matchAll(/<img\b[^>]*?\bsrc=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)) {
      const src = match[1] || match[2] || match[3];
      if (!src.startsWith(docsPath)) continue;
      const relative = decodeURIComponent(src.slice(docsPath.length).split('?')[0]);
      assert.ok(fs.existsSync(path.join(build, relative)), `${filename} has a missing image: ${src}`);
    }
  }
});

test('stylesheet assets resolve inside the current documentation channel', () => {
  for (const filename of files.filter(name => name.startsWith(path.join('assets', 'css') + path.sep) && name.endsWith('.css'))) {
    const css = fs.readFileSync(path.join(build, filename), 'utf8');
    for (const [, url] of css.matchAll(/url\(\s*["']?(\/[^)"'\s]+)["']?\s*\)/g)) {
      if (url.startsWith('//')) continue;
      assert.ok(url.startsWith(docsPath), `Wrong channel in ${filename}: ${url}`);
      const relative = decodeURIComponent(url.slice(docsPath.length).split('?')[0]);
      assert.ok(fs.existsSync(path.join(build, relative)), `Missing stylesheet asset in ${filename}: ${url}`);
    }
  }
});

test('community downloads keep the channel base path and complete inline examples', () => {
  const html = fs.readFileSync(path.join(build, 'example/custom-card-by.html'), 'utf8');
  const links = [...html.matchAll(/\bhref=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3]);
  const source = fs.readFileSync(path.resolve(__dirname, '../docs/example/custom-card-by.md'), 'utf8');
  for (const name of ['myfont.css', 'templates.yaml', 'drivers-standings-card.yaml', 'constructors-standings-card.yaml']) {
    const relative = `downloads/community/boredmthfkr/${name}`;
    assert.ok(links.includes(`${docsPath}${relative}`), `Wrong download URL: ${name}`);
    const download = fs.readFileSync(path.join(build, relative), 'utf8');
    const original = fs.readFileSync(path.resolve(__dirname, '../static', relative), 'utf8');
    assert.equal(download, original, `Build changed download: ${name}`);
    const language = name.endsWith('.css') ? 'css' : 'yaml';
    assert.ok(source.includes('```' + language + '\n' + download + '```'), `Download differs from its full inline example: ${name}`);
  }
});

test('the Token Helper privacy policy keeps its complete contractual content', () => {
  const {createHash} = require('node:crypto');
  const source = fs.readFileSync(path.resolve(__dirname, '../docs/help/f1tv-token-helper-privacy.md'), 'utf8');
  const body = source.split('---').slice(2).join('---');
  assert.equal(createHash('sha256').update(body).digest('hex'), require('../quality/docs-legacy-routes.json').helperPrivacyBodySha256);
});
