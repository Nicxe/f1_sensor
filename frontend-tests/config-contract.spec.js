const { test, expect } = require('@playwright/test');

test('unknown modules survive a real preview and do not prevent supported modules from rendering', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [
      { id: 'newer', type: 'future-module', unavailable: 'retain', fields: ['future-field'], options: { custom: 42 } },
      { id: 'schedule', type: 'calendar' },
    ] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    card.previewData = null;
    card.preview = true;
    card.hass = { ...demo.hass, connection: { connected: true, subscribeEvents: async () => () => {} }, callWS: async () => demo.preview.entries };
  });
  await expect(page.getByText('This module needs a newer card version. Its settings are preserved.', { exact: true })).toBeVisible();
  await expect(page.locator('#module-schedule .schedule time').first()).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0])).toMatchObject({ type: 'future-module', fields: ['future-field'], options: { custom: 42 } });
  expect(errors).toEqual([]);
});

test('the editor preserves unsupported content through an ordinary edit and a fresh card mount', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ editor: true, config: {
    extension: { future: true }, modules: [{ id: 'future', type: 'future-module', fields: ['future-field'], options: { custom: 42 } }, { type: 'calendar' }],
  } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByLabel('Card title', { exact: true }).fill('Recovered card');
  await editor.getByLabel('Card title', { exact: true }).press('Tab');
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved).toMatchObject({ title: 'Recovered card', extension: { future: true } });
  expect(saved.modules[0]).toMatchObject({ type: 'future-module', fields: ['future-field'], options: { custom: 42 } });
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByText('Recovered card', { exact: true })).toBeVisible();
  await expect(page.getByText('This module needs a newer card version. Its settings are preserved.', { exact: true })).toBeVisible();
  await expect(page.locator('.schedule time').first()).toBeVisible();
});
