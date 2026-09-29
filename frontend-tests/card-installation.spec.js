const { test, expect } = require('@playwright/test');

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
    }));
    expect(registered.modern).toBe(true);
    expect(registered.legacy).toBe(legacy);
    expect(registered.editor).toBe(legacy);
    if (!legacy) expect(registered.cards).toEqual(['f1-sensor-card']);
    else expect(registered.cards).toContain('f1-next-race-card');
    expect(requests.some(url => url.includes('/f1-sensor-live-data-card.js'))).toBe(legacy);
    expect(requests.some(url => url.includes('/modular/migration-editor.js'))).toBe(legacy);
  });
}
