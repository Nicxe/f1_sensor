const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test('timing explanation is compact, keyboard accessible, complete and stable during updates', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'timing' }] } }));
  const legend = page.locator('.timing-legend');
  const toggle = legend.locator('summary');
  await expect(toggle).toHaveText('Timing explained');
  await expect(legend).not.toHaveAttribute('open', '');
  await toggle.focus(); await page.keyboard.press('Enter');
  await expect(legend).toHaveAttribute('open', '');
  for (const text of ['Overall fastest', 'Personal best', 'Recorded time', 'Previous lap', 'Deleted time', 'Invalid time', 'Not available']) {
    await expect(legend.getByText(text, { exact: true })).toBeVisible();
  }
  await expect(legend).toContainText('▼');
  await expect(legend).toContainText('▲');
  await expect(legend).toContainText('previous completed lap');
  await expect(legend).toContainText('same lap');
  await page.evaluate(() => { window.fixtureCard.hass = { ...window.fixtureCard.hass }; });
  await expect(legend).toHaveAttribute('open', '');
  await expect(toggle).toBeFocused();
  const results = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(results.violations.filter(v => ['critical', 'serious'].includes(v.impact))).toEqual([]);
  await page.keyboard.press('Space');
  await expect(legend).not.toHaveAttribute('open', '');
});

test('timing explanation describes mixed laps in Swedish and survives narrow forced-color rendering', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { accessibility: { signals: 'text' }, modules: [{ type: 'timing', options: { sectors: 'latest' } }] } });
    window.fixtureCard.hass = { ...window.fixtureCard.hass, language: 'sv', locale: { ...window.fixtureCard.hass.locale, language: 'sv' } };
  });
  const legend = page.locator('.timing-legend');
  await legend.locator('summary').click();
  await expect(legend).toContainText('olika varv');
  await expect(legend).toContainText('Raderad tid');
  await expect(legend).toContainText('Ogiltig tid');
  await expect(legend).toContainText('Gul betyder registrerad');
  expect(await legend.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
});
