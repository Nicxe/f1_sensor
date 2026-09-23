const { test, expect } = require('@playwright/test');

test('independent modules retain all drivers or their own filters while group focus changes', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    const config = { context: { scope: 'group', group: 'comparison', team: 'McLaren' }, modules: [
      { id: 'follow', type: 'timing', fields: ['driver', 'last_lap'] },
      { id: 'all', type: 'timing', focus_mode: 'independent', fields: ['driver', 'last_lap'] },
      { id: 'pinned', type: 'timing', focus_mode: 'independent', driver: '16', fields: ['driver', 'last_lap'] },
      { id: 'conflict', type: 'timing', focus_mode: 'independent', driver: '16', team: 'McLaren', fields: ['driver'] },
    ] };
    window.mountModular({ config });
    const demo = window.fixtureDemo, card = window.fixtureCard;
    const hass = { ...demo.hass, connection: { connected: true, subscribeEvents: async () => () => {} }, callWS: async () => demo.preview.entries, callService: () => { throw new Error('Focus cannot write to HA'); } };
    card.entries = demo.preview.entries; card.previewData = null; card.hass = hass;
    const other = document.createElement('f1-sensor-card');
    other.setConfig({ ...config, modules: [config.modules[0]] }); other.entries = demo.preview.entries; other.hass = hass;
    document.querySelector('#root').append(other);
  });
  const first = page.locator('f1-sensor-card').nth(0), other = page.locator('f1-sensor-card').nth(1);
  await expect(first.locator('#module-all tr[data-driver="16"]')).toBeVisible();
  const count = await first.locator('#module-all tr[data-driver]').count();
  expect(count).toBeGreaterThan(1);
  await other.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('4');
  await expect(first.locator('#module-follow tr[data-driver="4"]')).toBeVisible();
  await expect(first.locator('#module-follow tr[data-driver]')).toHaveCount(1);
  await expect(first.locator('#module-all tr[data-driver]')).toHaveCount(count);
  await expect(first.locator('#module-pinned tr[data-driver="16"]')).toBeVisible();
  await expect(first.locator('#module-pinned tr[data-driver]')).toHaveCount(1);
  await expect(first.locator('#module-conflict tr[data-driver]')).toHaveCount(0);
  await expect(first.locator('#module-all').getByText('Own selection', { exact: true })).toBeVisible();
});

test('module focus behavior is editable and retained after a serialized reload', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1100 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ editor: true, config: { context: { driver: '4' }, modules: [{ type: 'timing', fields: ['driver'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Driver and team selection', { exact: true }).selectOption('independent');
  await expect(editor.getByLabel('Pinned driver', { exact: true }).locator('option:checked')).toHaveText('All');
  const saved = await page.evaluate(() => JSON.parse(JSON.stringify(window.savedConfig)));
  expect(saved.modules[0].focus_mode).toBe('independent');
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.locator('tr[data-driver="4"]')).toBeVisible();
  await expect(page.locator('tr[data-driver="16"]')).toBeVisible();
});
