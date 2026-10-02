const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('phase profiles switch modules without rewriting their saved configuration', async ({ page }) => {
  const config = {
    modules: [
      { id: 'before', type: 'overview', when: ['before'] },
      { id: 'active', type: 'calendar', when: ['active'] },
    ],
  };
  await page.evaluate(config => window.mountModular({ config, scene: 'race' }), config);
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Schedule', exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCard.config.modules.map(module => module.when))).toEqual([['before'], ['active']]);

  await page.evaluate(config => window.mountModular({ config, scene: 'before' }), config);
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Schedule', exact: true })).toHaveCount(0);
});

test('an unavailable pinned session is retained and never replaced by current data', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{
    type: 'overview',
    selection: { mode: 'pinned', source: 'live', season: 2026, meeting_key: 'demo-meeting', session_key: 'different-session' },
  }] } }));
  await expect(page.getByText('The pinned session is not available from the selected source. The saved identity has been kept.')).toBeVisible();
  await expect(page.getByText('Demo Grand Prix', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].selection.session_key)).toBe('different-session');
});

test('the editor offers typed card and module session choices plus all phase controls', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'timing' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByLabel('Session selection', { exact: true })).toBeVisible();
  for (const phase of ['Before', 'Active or interrupted', 'Finished', 'Unknown']) await expect(editor.getByLabel(phase, { exact: true })).toBeChecked();
  await editor.getByLabel('Before', { exact: true }).uncheck();
  expect(await page.evaluate(() => window.savedConfig.modules[0].when)).toEqual(['active', 'finished', 'unknown']);

  await editor.getByText('Layout and shared focus', { exact: true }).click();
  await expect(editor.getByLabel('Card session', { exact: true })).toBeVisible();
  await editor.getByLabel('Share driver focus with a named group', { exact: true }).check();
  await expect(editor.getByLabel('Share temporary session selection', { exact: true })).toBeVisible();
  await editor.getByLabel('Share temporary session selection', { exact: true }).check();
  expect(await page.evaluate(() => window.savedConfig.context.share)).toEqual(['focus', 'selection']);
});
