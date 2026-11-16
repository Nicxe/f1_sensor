const { test, expect } = require('@playwright/test');

for (const rootSize of [14, 16, 20]) {
  test(`compact data and captions stay readable with a ${rootSize}px Home Assistant font base`, async ({ page }) => {
    page.on('pageerror', error => { throw error; });
    await page.route('https://**/*', route => route.abort());
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.evaluate(size => {
      document.documentElement.style.fontSize = `${size}px`;
      window.mountModular({ scene: 'replay', config: {
        appearance: { style: 'ha', font: 'system', logos: false },
        modules: [
          { id: 'results', type: 'results' },
          { id: 'map', type: 'map' },
          { id: 'chart', type: 'progression' },
          { id: 'telemetry', type: 'telemetry' },
          { id: 'radio', type: 'team_radio' },
          { id: 'history', type: 'tyres', options: { content: 'history' } },
        ],
      } });
    }, rootSize);
    const tags = ['f1-module-view', 'f1-track-map-view', 'f1-series-chart', 'f1-telemetry-view', 'f1-team-radio-view', 'f1-tyre-history-view'];
    for (const tag of tags) await expect(page.locator(tag).first()).toHaveCSS('font-size', `${rootSize}px`);
    await page.evaluate(() => {
      const card = window.fixtureCard;
      card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
    });
    for (const tag of tags) {
      await expect(page.locator(tag).first()).toHaveCSS('font-size', `${Math.max(rootSize * 0.875, 14)}px`);
    }
    const captions = page.locator('f1-module-view[data-module-id="results"] th, f1-team-radio-view .meta');
    await expect(captions.first()).toBeVisible();
    for (const caption of await captions.all()) {
      expect(await caption.evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(11.99);
    }
    await page.evaluate(() => {
      const card = window.fixtureCard;
      card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'current' } });
    });
    for (const tag of tags) await expect(page.locator(tag).first()).toHaveCSS('font-size', `${rootSize}px`);
  });
}
