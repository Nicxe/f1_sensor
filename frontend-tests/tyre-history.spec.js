const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

async function mountHistory(page, options = {}) {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(options => {
    window.mountModular({ config: { modules: [{ id: 'tyres', type: 'tyres', options: { content: 'history', ...options } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const attrs = demo.hass.states[entry.entities.current_tyres].attributes;
    Object.assign(attrs, { lap_current: 34, lap_total: 56, drivers: [
      { racing_number: '1', tla: 'VER', position: 1, compound: 'HARD', stint_laps: 16, new: true, completed_laps: 34, stint_history_complete: true, stints: [
        { stint_index: 0, compound: 'MEDIUM', new: true, first_lap: 1, last_lap: 18, stint_laps: 18, tyre_age_at_start: 0, total_laps: 18, is_current: false, coverage: 'complete' },
        { stint_index: 1, compound: 'HARD', new: true, first_lap: 19, last_lap: 34, stint_laps: 16, tyre_age_at_start: 0, total_laps: 16, is_current: true, coverage: 'complete' },
      ] },
      { racing_number: '4', tla: 'NOR', position: 2, compound: 'HARD', stint_laps: 17, new: false, completed_laps: 34, stint_history_complete: true, stints: [
        { stint_index: 0, compound: 'MEDIUM', new: true, first_lap: 1, last_lap: 20, stint_laps: 20, tyre_age_at_start: 0, total_laps: 20, is_current: false, coverage: 'complete' },
        { stint_index: 1, compound: 'HARD', new: false, first_lap: 21, last_lap: 34, stint_laps: 14, tyre_age_at_start: 3, total_laps: 17, is_current: true, coverage: 'complete' },
      ] },
    ] });
    window.fixtureCard.hass = { ...demo.hass };
  }, options);
  await expect(page.locator('f1-tyre-history-view')).toBeVisible();
}

test.beforeEach(({ page }) => page.on('pageerror', error => { throw error; }));

test('tyre history retains completed stints and separates used tyre age from race distance', async ({ page }) => {
  await mountHistory(page);
  const history = page.locator('f1-tyre-history-view');
  await expect(history.locator('.lap-progress')).toHaveText('Lap 34 / 56');
  const driver = history.locator('[data-tyre-driver="4"]');
  await expect(driver.locator('.age')).toHaveText('17');
  const bar = driver.locator('.segment').last();
  await expect(bar).toHaveClass(/used/);
  const bounds = await bar.evaluate(node => ({ left: parseFloat(node.style.left), width: parseFloat(node.style.width) }));
  expect(bounds.left).toBeCloseTo(20 / 56 * 100);
  expect(bounds.width).toBeCloseTo(14 / 56 * 100);
  await driver.getByRole('button', { name: 'Show stints for NOR', exact: true }).click();
  await expect(driver.locator('.stints tbody tr')).toHaveCount(2);
  await expect(driver.locator('.stints tbody tr').first().getByRole('cell')).toHaveText(['M1 · MediumCompleted', '1–20', '20', '0', '20']);
  await expect(driver.locator('.stints tbody tr').last().getByRole('cell')).toHaveText(['H2 · HardCurrent · Used at fitting', '21–34', '14', '3', '17']);
  await expect(driver.locator('.driver-detail')).not.toContainText('NOR');
  await expect(history.locator('.legend')).toBeVisible();
  const results = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(results.violations).toEqual([]);
});

test('driver expansion follows driver identity through lap and position updates and resets with session', async ({ page }) => {
  await mountHistory(page);
  const history = page.locator('f1-tyre-history-view');
  const driver = history.locator('[data-tyre-driver="4"]');
  const button = driver.locator('button');
  await button.click();
  await button.focus();
  await page.evaluate(() => {
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const attrs = demo.hass.states[entry.entities.current_tyres].attributes;
    attrs.drivers[0].position = 2;
    Object.assign(attrs.drivers[1], { position: 1, stint_laps: 18, completed_laps: 35 });
    Object.assign(attrs.drivers[1].stints[1], { last_lap: 35, stint_laps: 15, total_laps: 18 });
    attrs.lap_current = 35;
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(history.locator('.drivers > li').first()).toHaveAttribute('data-tyre-driver', '4');
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await expect(button).toBeFocused();
  await expect(driver.locator('.age')).toHaveText('18');
  await expect(driver.locator('.stints tbody tr').last().getByRole('cell').last()).toHaveText('18');
  await page.evaluate(() => {
    const view = window.fixtureCard.shadowRoot.querySelector('f1-module-view').tyreHistoryNode;
    view.model = { ...view.model, context: { ...view.model.context, key: 'another-session' } };
  });
  await expect(button).toHaveAttribute('aria-expanded', 'false');
  await expect(driver.locator('.driver-detail')).toHaveCount(0);
});

test('legend is optional and known history remains usable at narrow widths with forced colors', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await mountHistory(page, { show_legend: false });
  const history = page.locator('f1-tyre-history-view');
  await expect(history.locator('.legend')).toHaveCount(0);
  await history.getByRole('button', { name: 'Show stints for NOR', exact: true }).press('Enter');
  await expect(history.locator('.stints')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: 'active' });
  await expect(history.locator('.segment.used')).toContainText('H 14');
  await expect(history.locator('.stints tbody tr')).toHaveCount(2);
  await history.getByRole('button', { name: 'Hide stints for NOR', exact: true }).press('Enter');
  await expect(history.locator('.driver-detail')).toHaveCount(0);
});

test('partial and unknown stint data stay unknown and are never drawn at invented lap positions', async ({ page }) => {
  await mountHistory(page);
  await page.evaluate(() => {
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const driver = demo.hass.states[entry.entities.current_tyres].attributes.drivers[1];
    driver.stint_history_complete = false;
    driver.stints = [{ stint_index: 3, compound: 'HARD', new: false, first_lap: null, last_lap: null, stint_laps: null, tyre_age_at_start: null, total_laps: 17, is_current: true, coverage: 'partial' }];
    window.fixtureCard.hass = { ...demo.hass };
  });
  const driver = page.locator('f1-tyre-history-view [data-tyre-driver="4"]');
  await expect(driver.locator('.segment')).toHaveCount(0);
  await expect(driver.locator('.missing-range')).toHaveText('Lap range unavailable');
  await driver.getByRole('button').click();
  await expect(driver.locator('.partial')).toHaveText('Earlier stints or lap ranges may be missing');
  await expect(driver.locator('.stints tbody tr').getByRole('cell').nth(1)).toHaveText('—');
  await expect(driver.locator('.stints tbody tr').getByRole('cell').nth(2)).toHaveText('—');
  await expect(driver.locator('.stints tbody tr').getByRole('cell').nth(3)).toHaveText('—');
  await expect(driver.locator('.stints tbody tr').getByRole('cell').last()).toHaveText('17');
  await expect(driver.locator('.stint-status')).toContainText('Used at fitting');
  await page.evaluate(() => {
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const attrs = demo.hass.states[entry.entities.current_tyres].attributes;
    attrs.drivers = [attrs.drivers[1]];
    attrs.drivers[0].completed_laps = null;
    attrs.lap_current = null;
    attrs.lap_total = null;
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.locator('f1-tyre-history-view .axis span')).toHaveCount(0);
});

test('history editor previews known stints and saves its legend setting independently', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'tyres', options: { content: 'history' } }] } });
    window.fixtureCard.entries = window.fixtureDemo.preview.entries;
  });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  const legend = editor.getByRole('checkbox', { name: 'Show compound legend', exact: true });
  await expect(legend).toBeChecked();
  const preview = page.locator('f1-sensor-card');
  await expect(preview.locator('f1-tyre-history-view .segment').first()).toBeVisible();
  await legend.uncheck();
  await expect(preview.locator('f1-tyre-history-view .legend')).toHaveCount(0);
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.show_legend)).toBe(false);
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('current');
  await expect(legend).toHaveCount(0);
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('history');
  await expect(legend).not.toBeChecked();
});
