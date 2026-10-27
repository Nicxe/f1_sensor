const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('count-only live pit data shows driver summaries without empty timing columns', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'pit_stops', fields: ['driver', 'status', 'pit_count', 'stop_lap', 'stop_time', 'lane_time', 'pit_delta'], options: { content: 'all_stops' } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0], pit = demo.hass.states[entry.entities.pitstops];
    pit.state = '25'; pit.attributes.cars = { 16: { count: 25, stops: [] }, 4: { count: 0, stops: [] } };
    demo.hass.states[entry.entities.driver_positions].attributes.drivers.find(driver => driver.racing_number === '16').status = 'pit_in';
    window.fixtureCard.hass = { ...demo.hass };
  });
  const summary = page.getByRole('table', { name: 'Reported pit visits', exact: true });
  await expect(summary).toBeVisible();
  await expect(summary.getByRole('columnheader', { name: 'Current status', exact: true })).toBeVisible();
  await expect(summary.locator('[data-count-driver="16"]')).toContainText('25');
  await expect(summary.locator('[data-count-driver="16"]')).toContainText('In pit');
  await expect(summary.locator('[data-count-driver="16"]')).not.toContainText('pit_in');
  await expect(summary.locator('[data-count-driver="4"]')).toContainText('0');
  await expect(page.getByRole('columnheader', { name: 'Stationary time', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Stop lap', exact: true })).toHaveCount(0);
  await expect(page.getByText('No data is available for this selection yet.', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Reported pit visit counts are shown separately', { exact: false })).toBeVisible();
  await expect(page.locator('tr[data-driver]')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(axe.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('pit-counts-mobile.png'), fullPage: true });
  await page.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('4');
  await expect(summary.locator('tbody tr')).toHaveCount(1);
  await expect(summary.locator('[data-count-driver="4"]')).toContainText('0');
});

test('mixed pit data keeps count summaries separate and identifies pit lane-only records', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'pit_stops', fields: ['driver', 'status', 'pit_count', 'stop_lap', 'stop_time', 'lane_time'], options: { content: 'all_stops' } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0], pit = demo.hass.states[entry.entities.pitstops];
    pit.state = '3'; pit.attributes.cars = {
      16: { count: 2, stops: [] },
      4: { count: 1, stops: [{ lap: 18, timestamp: null, pit_stop_time: null, pit_lane_time: 23.7, source: 'PitLaneTimeCollection' }] },
    };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.locator('.pit-count-summary tbody tr')).toHaveCount(1);
  await expect(page.locator('tr[data-driver]')).toHaveCount(1);
  const detail = page.locator('tr[data-driver]');
  await expect(detail).toContainText('Pit lane timing only');
  await expect(detail.getByRole('cell').nth(4)).toHaveText('—');
  await expect(detail.getByRole('cell').nth(5)).toHaveText('23.700 s');
  await expect(page.getByText('Stationary time has not been received for those records.', { exact: false })).toBeVisible();
  await page.evaluate(() => {
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.pitstops].attributes.cars[16].stops = [{ lap: 20, timestamp: '2026-09-13T13:30:00Z', pit_stop_time: 2.3, pit_lane_time: 23.793, source: 'PitStopSeries' }];
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.locator('.pit-count-summary')).toHaveCount(0);
  await expect(page.locator('tr[data-driver]')).toHaveCount(2);
  await expect(page.getByText('Detailed records cover only some reported pit visits.', { exact: false })).toBeVisible();
  await page.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('16');
  await expect(page.getByText('Pit lane timing only', { exact: true })).toHaveCount(0);
  await expect(page.locator('tr[data-driver]')).toHaveCount(1);
});

test('unavailable and spoiler-protected sources do not leak retained pit counts', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'pit_stops' }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0], pit = demo.hass.states[entry.entities.pitstops];
    pit.state = 'unavailable'; pit.attributes.cars = { 16: { count: 25, stops: [] } };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.getByText('Pit stop timing needs F1TV access', { exact: false })).toBeVisible();
  await expect(page.locator('.pit-count-summary')).toHaveCount(0);
  await page.evaluate(() => {
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.pitstops].state = '25';
    demo.hass.states['switch.f1_demo_spoilers'].state = 'on';
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(page.locator('.pit-count-summary')).toHaveCount(0);
});
