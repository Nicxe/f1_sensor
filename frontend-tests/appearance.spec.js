const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('graphical editor choices save and reload without changing timing content or palette', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, config: { appearance: { palette: { personal: '#2255bb' } }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.locator('summary').filter({ hasText: /^Appearance$/ }).click();
  await editor.getByText('Headings and surface', { exact: true }).click();
  await editor.getByLabel('Heading font', { exact: true }).selectOption('system');
  await editor.getByLabel('Style', { exact: true }).selectOption('minimal');
  await editor.getByLabel('Density', { exact: true }).selectOption('spacious');
  await editor.getByRole('checkbox', { name: 'Show card title', exact: true }).uncheck();
  await editor.getByText('Module appearance', { exact: true }).click();
  await editor.getByRole('checkbox', { name: 'Show module title', exact: true }).uncheck();
  await editor.getByRole('checkbox', { name: 'Show table header', exact: true }).uncheck();
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.appearance).toMatchObject({ style: 'minimal', font: 'system', density: 'spacious', show_header: false, palette: { personal: '#2255bb' } });
  expect(saved.modules[0]).toMatchObject({ show_header: false, show_table_header: false, fields: ['driver', 'last_lap'] });
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.locator('ha-card')).toHaveAttribute('data-font', 'system');
  await expect(page.locator('.heading')).toHaveCount(0);
  await expect(page.locator('button.driver').first()).toBeVisible();
  expect(await page.locator('f1-module-view h2').evaluate(node => getComputedStyle(node).fontFamily)).not.toContain('Barlow');
});

test('hidden titles and headers keep native names, session badges, focus and keyboard actions', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(() => {
    window.mountModular({ scene: 'qualifying', config: { title: 'My timing', appearance: { show_header: false }, tap_action: { action: 'navigate', navigation_path: '/lovelace/f1' }, modules: [{ type: 'timing', show_header: false, show_table_header: false, fields: ['driver', 'last_lap'] }, { type: 'standings', show_header: false, show_table_header: false, fields: ['driver', 'points'] }] } });
    window.actions = [];
    window.fixtureCard.addEventListener('hass-action', event => window.actions.push(event.detail.action));
  });
  const card = page.locator('f1-sensor-card');
  await expect(card.getByRole('button', { name: 'Freeze view', exact: true })).toBeVisible();
  await expect(card.getByRole('combobox', { name: 'Driver focus', exact: true })).toBeVisible();
  await expect(card.locator('.chip').filter({ hasText: /^Q[123]$/ })).toBeVisible();
  await expect(card.locator('.heading')).toHaveCount(0);
  const snapshot = await card.ariaSnapshot();
  expect(snapshot).toContain('columnheader "Last lap"');
  expect(snapshot).toContain('columnheader "Points"');
  expect(snapshot).toContain('heading "Timing"');
  for (const header of await card.locator('thead').all()) expect(await header.evaluate(node => node.getBoundingClientRect().height)).toBeLessThan(2);
  await card.getByText('Card actions', { exact: true }).click();
  await card.getByRole('button', { name: 'Tap action', exact: true }).focus();
  await page.keyboard.press('Enter');
  expect(await page.evaluate(() => window.actions)).toEqual([]);
  await card.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await expect(card.getByRole('button', { name: 'Resume', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const violations = (await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(item => ['serious', 'critical'].includes(item.impact));
  expect(violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { window.fixtureCard.entries = window.fixtureDemo.preview.entries; window.fixtureCard.previewData = null; });
  await card.getByRole('button', { name: 'Tap action', exact: true }).focus();
  await page.keyboard.press('Enter');
  expect(await page.evaluate(() => window.actions)).toEqual(['tap']);
});

test('three densities affect nested chart data without shrinking controls or table text', async ({ page }) => {
  const heights = [];
  for (const density of ['compact', 'comfortable', 'spacious']) {
    await page.evaluate(density => window.mountModular({ config: { appearance: { density }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }, { type: 'progression', options: { presentation: 'table' } }] } }), density);
    const row = page.locator('f1-series-chart tbody tr').first();
    await expect(row).toBeVisible();
    heights.push(await row.evaluate(node => node.getBoundingClientRect().height));
    const font = await row.locator('td').first().evaluate(node => parseFloat(getComputedStyle(node).fontSize));
    expect(font).toBeGreaterThanOrEqual(16);
    const target = await page.locator('button.driver').first().boundingBox();
    expect(target.height).toBeGreaterThanOrEqual(44);
  }
  expect(heights[0]).toBeLessThan(heights[1]);
  expect(heights[1]).toBeLessThan(heights[2]);
});

test('explicit heading fonts stay independent of every style and automatic font follows style', async ({ page }) => {
  for (const font of ['auto', 'f1', 'system']) {
    for (const style of ['f1', 'ha', 'minimal']) {
      await page.evaluate(({ font, style }) => window.mountModular({ config: { appearance: { font, style }, modules: [{ type: 'timing' }] } }), { font, style });
      const expected = font === 'auto' ? style === 'f1' ? 'f1' : 'system' : font;
      await expect(page.locator('ha-card')).toHaveAttribute('data-font', expected);
      const family = await page.locator('f1-module-view h2').evaluate(node => getComputedStyle(node).fontFamily);
      expect(family.includes('Barlow')).toBe(expected === 'f1');
    }
  }
});
