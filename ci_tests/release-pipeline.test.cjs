const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('release verification reuses matching source checks but keeps target release work', () => {
  const workflow = read('.github/workflows/release-pipeline.yml');
  assert.match(workflow, /checks:\n\s+uses: \.\/\.github\/workflows\/ci-checks\.yml\n\s+with:\n\s+allow_reuse: true/);
  assert.match(workflow, /release:\n\s+needs: checks/);
  assert.match(workflow, /deploy:\n\s+needs: checks/);
});

test('Context7 runs only after a successful main documentation deployment', () => {
  const workflow = read('.github/workflows/release-pipeline.yml');
  assert.match(workflow, /context7:\n\s+needs: deploy/);
  assert.match(workflow, /needs\.deploy\.result == 'success'/);
  assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
  assert.equal(fs.existsSync(path.join(root, '.github/workflows/context7-refresh.yml')), false);
});
