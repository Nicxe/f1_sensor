const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('status-only minisectors keep source counts, order and accessible meanings', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'minisectors' }] } }));
  const module = page.getByRole('region', { name: 'Minisectors', exact: true });
  await expect(module.getByRole('columnheader', { name: 'S1 minisectors', exact: true })).toBeVisible();
  const row = module.locator('tr[data-driver="16"]');
  await expect(row.locator('.minisector-strip').nth(0).locator('.minisector-block')).toHaveCount(6);
  await expect(row.locator('.minisector-strip').nth(1).locator('.minisector-block')).toHaveCount(7);
  await expect(row.locator('.minisector-strip').nth(2).locator('.minisector-block')).toHaveCount(9);
  await expect(row.getByLabel('Minisector 1: Overall best')).toBeVisible();
  expect(await row.locator('.minisector-block').evaluateAll(blocks => [...new Set(blocks.map(block => getComputedStyle(block).borderRadius))])).toEqual(['4px']);
  await module.locator('.timing-legend summary').click();
  await expect(module.getByText('Minisectors show provider status only. They do not contain or estimate minisector times.', { exact: true })).toBeVisible();
  await expect(module.getByText('Special status', { exact: true })).toBeVisible();
  const result = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(result.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
});

test('timing supports separate, combined and time-only sector fields without changing defaults', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'timing', fields: ['driver', 'sector_1', 'minisector_1', 'sector_2_with_minisectors'] }] } }));
  const module = page.getByRole('region', { name: 'Timing', exact: true });
  await expect(module.getByRole('columnheader', { name: 'S1', exact: true })).toBeVisible();
  await expect(module.getByRole('columnheader', { name: 'S1 minisectors', exact: true })).toBeVisible();
  await expect(module.getByRole('columnheader', { name: 'S2 with minisectors', exact: true })).toBeVisible();
  const row = module.locator('tr[data-driver="16"]');
  await expect(row.locator('td').nth(1).locator('.time')).toHaveText('24.321');
  await expect(row.locator('td').nth(2).locator('.minisector-block')).toHaveCount(6);
  await expect(row.locator('td').nth(3).locator('.time')).toHaveText('30.543');
  await expect(row.locator('td').nth(3).locator('.minisector-block')).toHaveCount(7);
  const dimensions = await row.locator('td').nth(3).evaluate(cell => {
    const time = cell.querySelector('.signal')?.getBoundingClientRect(), strip = cell.querySelector('.minisector-strip')?.getBoundingClientRect();
    return time && strip ? { time: Math.round(time.width), strip: Math.round(strip.width) } : null;
  });
  expect(dimensions).not.toBeNull();
  expect(dimensions.time).toBe(dimensions.strip);
});

test('independent minisector modules work on mobile and light mode', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(() => window.mountModular({ config: {
    appearance: { mode: 'light' },
    modules: [
      { type: 'minisectors', title: 'Leclerc sectors', driver: '16', focus_mode: 'independent', fields: ['driver', 'minisector_1'] },
      { type: 'minisectors', title: 'Norris sectors', driver: '4', focus_mode: 'independent', fields: ['driver', 'sector_2_with_minisectors'], options: { show_legend: false } },
    ],
  } }));
  await expect(page.getByRole('region', { name: 'Leclerc sectors', exact: true }).locator('tbody > tr:not(.details)')).toHaveCount(1);
  await expect(page.getByRole('region', { name: 'Norris sectors', exact: true }).locator('tbody > tr:not(.details)')).toHaveCount(1);
  await expect(page.getByRole('region', { name: 'Norris sectors', exact: true }).locator('.timing-legend')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.locator('ha-card')).toHaveAttribute('style', /--_f1-surface:#ffffff/);
});

test('visual editor exposes the module and warns about duplicate sector presentation', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: { modules: [{ type: 'minisectors', fields: ['driver', 'sector_1', 'minisector_1', 'sector_1_with_minisectors'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await expect(editor.getByLabel('Add module', { exact: true }).locator('option[value="minisectors"]')).toHaveText('Minisectors');
  await expect(editor.getByRole('checkbox', { name: 'S1 minisectors', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'S1 with minisectors', exact: true })).toBeChecked();
  await expect(editor.getByText(/Sectors 1 are shown more than once/)).toBeVisible();
  await expect(editor.getByLabel('Show status legend', { exact: true })).toBeChecked();
});
