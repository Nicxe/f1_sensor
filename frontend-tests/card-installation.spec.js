const { test, expect } = require('@playwright/test');
const { SUPPORTED_CARD_TYPES, COMPATIBILITY_CARD_TYPES } = require('./supported-cards.cjs');
const { assertManagedResources } = require('./managed-resources.cjs');

const base = '/custom_components/f1_sensor/www/f1-sensor-live-data-card/';

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('new card starts with Build your own and offers templates immediately', async ({ page }) => {
  const stub = await page.evaluate(() => customElements.get('f1-sensor-card').getStubConfig());
  expect(stub.modules).toEqual([]);
  await page.evaluate(config => window.mountModular({ editor: true, config }), stub);
  await expect(page.locator('.module-list li')).toHaveCount(0);
  await expect(page.getByText('Add your first module in the editor.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /Build your own/ })).toBeVisible();
  await page.getByRole('button', { name: /^Race weekend/ }).click();
  await expect(page.locator('.module-list li')).toHaveCount(4);
  await expect(page.getByRole('region', { name: 'Replace content', exact: true })).toHaveCount(0);
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules.map(module => module.type)).toEqual(['overview', 'calendar', 'weather', 'weather']);
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ editor: true, config }), saved);
  await expect(page.locator('.module-list li')).toHaveCount(4);
  await expect(page.locator('details.starter')).not.toHaveAttribute('open', '');
});

for (const legacy of [false, true]) {
  test(`managed registration loads ${legacy ? 'modern and legacy cards' : 'only the modern card'}`, async ({ page }) => {
    const requests = [];
    page.on('request', request => requests.push(request.url()));
    await page.evaluate(async url => { await import(url); }, `${base}register.js?v=registration-test${legacy ? '' : '&legacy=0'}`);
    const registered = await page.evaluate(() => ({
      cards: window.customCards.map(card => card.type),
      modern: Boolean(customElements.get('f1-sensor-card')),
      legacy: Boolean(customElements.get('f1-next-race-card')),
      editor: Boolean(customElements.get('f1-next-race-card-editor')),
      factories: window.customCards.map(({ type }) => ({
        type,
        card: Boolean(customElements.get(type)),
        editor: Boolean(customElements.get(type)?.getConfigElement?.()),
      })),
    }));
    expect(registered.modern).toBe(true);
    expect(registered.legacy).toBe(legacy);
    expect(registered.editor).toBe(legacy);
    if (!legacy) expect(registered.cards).toEqual(['f1-sensor-card']);
    else {
      expect(registered.cards).toEqual(expect.arrayContaining(SUPPORTED_CARD_TYPES));
      expect(await page.evaluate(types => types.every(type => Boolean(customElements.get(type))), COMPATIBILITY_CARD_TYPES)).toBe(true);
    }
    for (const card of registered.factories) {
      expect(card.card, card.type).toBe(true);
      expect(card.editor, card.type).toBe(true);
    }
    expect(requests.some(url => url.includes('/f1-sensor-live-data-card.js'))).toBe(legacy);
    expect(requests.some(url => url.includes('/modular/migration-editor.js'))).toBe(legacy);
  });
}

test('managed registration resolves the localization catalog before card entrypoints', async ({ page }) => {
  const requests = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.searchParams.get('v') === 'ios-bootstrap') requests.push(url.pathname);
  });

  await page.evaluate(async url => { await import(url); }, `${base}register.js?v=ios-bootstrap&legacy=0`);

  const catalog = requests.indexOf(`${base}modular/catalog.js`);
  const card = requests.indexOf(`${base}modular/card.js`);
  const editor = requests.indexOf(`${base}modular/editor.js`);
  expect(catalog).toBeGreaterThanOrEqual(0);
  expect(card).toBeGreaterThan(catalog);
  expect(editor).toBeGreaterThan(catalog);
});

for (const refactored of [false, true]) {
  test(`managed version reaches nested modules and tyre assets${refactored ? ' after an equivalent loader refactor' : ''}`, async ({ page }) => {
    if (refactored) await page.route(`${base}register.js?*`, async route => {
      const response = await route.fetch();
      const original = await response.text();
      const renamed = original.replace(/\bcacheKey\b/g, 'versionToken').replace(/\bcacheSuffix\b/g, 'versionQuery');
      expect(renamed).not.toBe(original);
      await route.fulfill({ response, body: renamed });
    });
    const version = 'release version+1';
    const requests = [];
    page.on('request', request => {
      const url = new URL(request.url());
      if (url.pathname.startsWith(base) && /\.(?:js|png)$/.test(url.pathname)) requests.push(url);
    });
    await page.evaluate(async url => { await import(url); }, `${base}register.js?v=${encodeURIComponent(version)}`);
    for (const compound of ['HARD', 'SOFT', 'MEDIUM', 'INTERMEDIATE', 'WET']) {
      await page.evaluate(async compound => {
        const card = document.createElement('f1-sensor-live-data-card');
        card.setConfig({ entity: 'sensor.tyres', compounds: [compound], show_team_logo: false });
        card.hass = {
          language: 'en', locale: { language: 'en', time_zone: 'UTC' },
          states: { 'sensor.tyres': { state: compound, attributes: { compounds: {} } } },
          config: { time_zone: 'UTC' },
        };
        document.querySelector('#root').replaceChildren(card);
        await card.updateComplete;
      }, compound);
      // The responsive renderer may repeat a compound in its filled columns.
      await expect(page.getByRole('img', { name: `${compound} tyre`, exact: true }).first()).toBeVisible();
    }
    assertManagedResources(requests, base, version);
  });
}
