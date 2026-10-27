const {test, expect} = require('@playwright/test');
const {catalogs, filenames, expectedMessage} = require('./localization-fixture.cjs');

const base = '/custom_components/f1_sensor/www/f1-sensor-live-data-card/localization/';
const resolvedCatalogs = Object.fromEntries(Object.keys(catalogs).map(language => [language,
  Object.fromEntries(Object.keys(catalogs.en).map(key => [key, expectedMessage(language, key)]))]));

test('every shipped locale loads through the HTTP manifest and resolves the independently read catalog', async ({page}) => {
  const errors = [], requested = new Set();
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requested.add(new URL(request.url()).pathname));
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  const result = await page.evaluate(async ({base, expected}) => {
    const {LOCALES, translate} = await import(`${base}index.js`);
    const mismatches = [];
    for (const [language, messages] of Object.entries(expected)) {
      for (const [key, message] of Object.entries(messages)) {
        if (translate(language, key) !== message) mismatches.push(`${language}: ${key}`);
      }
    }
    return {languages: Object.keys(LOCALES).sort(), mismatches};
  }, {base, expected: resolvedCatalogs});
  expect(result.languages).toEqual(Object.keys(catalogs).map(code => code.toLowerCase()).sort());
  expect(result.mismatches).toEqual([]);
  expect(requested.has(`${base}available-locales.json`)).toBe(true);
  for (const filename of filenames) expect(requested.has(`${base}locales/${filename}`), filename).toBe(true);
  expect(errors).toEqual([]);
});

for (const wording of ['Regional pause label', 'An entirely reworded pause label']) {
  test(`regional wording survives real card loading and sparse base fallback: ${wording}`, async ({page}) => {
    await page.route(`**${base}available-locales.json*`, route => route.fulfill({json: [...filenames.map(name => name.slice(0, -5)).filter(code => code.toLowerCase() !== 'pt-br'), 'pt-BR']}));
    await page.route(`**${base}locales/pt-BR.json*`, route => route.fulfill({json: {'modular.freeze_view': wording}}));
    await page.route(`**${base}locales/pt.json*`, route => route.fulfill({json: {'modular.resume': 'Base language resume label'}}));
    await page.setViewportSize({width: 360, height: 900});
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.evaluate(() => window.mountModular({language: 'pt-BR', config: {modules: [{type: 'overview'}]}}));
    const card = page.locator('f1-sensor-card');
    await card.getByRole('button', {name: wording, exact: true}).click();
    await expect(card.getByRole('button', {name: 'Base language resume label', exact: true})).toHaveAttribute('aria-pressed', 'true');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const interpolation = await page.evaluate(async base => {
      const {translate} = await import(`${base}index.js`);
      return translate('pt-BR', 'a11y.open_details', {title: 'Sentinel driver'});
    }, base);
    expect(interpolation).toBe(catalogs.en['a11y.open_details'].replaceAll('{title}', 'Sentinel driver'));
  });
}

for (const manifest of [['en', '../bad'], ['en', 'pt-BR', 'pt-br'], ['sv']]) {
  test(`invalid HTTP manifest is rejected: ${manifest.join(',')}`, async ({page}) => {
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.route(`**${base}available-locales.json*`, route => route.fulfill({json: manifest}));
    const error = await page.evaluate(async base => {
      try { await import(`${base}index.js?invalid-manifest`); return ''; }
      catch (error) { return error.message; }
    }, base);
    expect(error).toBe('F1 Sensor locale manifest is invalid');
  });
}

test('a missing delivered locale produces a loading failure instead of silently dropping the language', async ({page}) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.route(`**${base}available-locales.json*`, route => route.fulfill({json: ['en', 'zz']}));
  await page.route(`**${base}locales/zz.json*`, route => route.fulfill({status: 404, body: 'Missing locale'}));
  const error = await page.evaluate(async base => {
    try { await import(`${base}index.js?missing-locale`); return ''; }
    catch (error) { return error.message; }
  }, base);
  expect(error).toContain('Could not load F1 Sensor zz translations (404)');
});
