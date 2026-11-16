const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('matched strategy explains signed pairs, spread and exclusions accessibly on mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'strategy', options: { content: 'teammates' } }] } }));
  await expect(page.getByText('-0.200 s', { exact: true })).toBeVisible();
  const summary = page.locator('.strategy-evidence summary');
  await summary.focus(); await page.keyboard.press('Enter');
  await expect(page.getByText('Matched / possible pairs: 5 / 8 · laps: 2–6', { exact: true })).toBeVisible();
  await expect(page.getByText('Spread (Q1–Q3): -0.200 – -0.200 s', { exact: true })).toBeVisible();
  await expect(page.getByText('Lap quality is not eligible for pace comparison: 3', { exact: true })).toBeVisible();
  await expect(page.getByText('Lap 2: 1:21.120 − 1:21.320 = -0.200 s', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(axe.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('strategy-evidence-mobile.png'), fullPage: true });
});

test('older strategy data keeps descriptive pace without a paired winner or legacy trend', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [
      { type: 'strategy', options: { content: 'teammates' } },
      { type: 'strategy', driver: '16', fields: ['driver', 'degradation', 'strategy_pit_loss'] },
    ] } });
    const demo = window.fixtureDemo;
    delete demo.preview.analysis.strategy.teammate_comparisons[0].matched_comparison;
    for (const stint of demo.preview.analysis.strategy.stints) {
      delete stint.lap_time_trend; delete stint.stint_change_estimate;
      stint.pit_loss_seconds = 99;
    }
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.getByText('HAM: 1:21.320', { exact: true })).toBeVisible();
  await expect(page.getByText('-0.200 s', { exact: true })).toHaveCount(0);
  await expect(page.getByText('+0.053 s/lap', { exact: true })).toHaveCount(0);
  await expect(page.getByText('+99.000 s', { exact: true })).toHaveCount(0);
  await page.locator('.strategy-evidence summary').first().click();
  await expect(page.getByText('Descriptive observations; laps are not matched for a comparison.', { exact: true }).first()).toBeVisible();
});

test('stint estimates explain the transition and exact eligible baseline separately from the trend', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'strategy', driver: '16', fields: ['driver', 'degradation', 'strategy_pit_loss'] }] } });
    const demo = window.fixtureDemo;
    demo.preview.analysis.strategy.stints[0].stint_change_estimate = {
      status: 'ready', method: 'observed_transition_lap_minus_previous_eligible_median', seconds: 20,
      baseline_seconds: 90, baseline_laps: [1, 2, 3], baseline_green_phase_id: 'green:2', transition_lap: 4, sample_count: 3,
    };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(page.getByText('+20.000 s', { exact: true })).toBeVisible();
  await expect(page.getByText('+0.053 s/lap', { exact: true })).toBeVisible();
  await page.locator('.strategy-evidence summary').click();
  await expect(page.getByText("Observed transition-lap time minus the previous stint's eligible-lap median from its last observed green phase.", { exact: true })).toBeVisible();
  await expect(page.getByText('Observed transition lap: 4 · Previous eligible-lap median: 1:30.000', { exact: true })).toBeVisible();
  await expect(page.getByText('laps: 1, 2, 3', { exact: true })).toBeVisible();
});
