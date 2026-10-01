const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T13:32:00Z') });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { context: { viewing_controls: true }, modules: [
      { type: 'calendar' }, { type: 'documents' }, { type: 'race_control' }, { type: 'map' },
    ] } });
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].entities.delay_calibration_switch;
    card.hass = { ...card.hass, locale: { language: 'en-US', time_format: '24', time_zone: 'server' }, config: { ...card.hass.config, time_zone: 'UTC' } };
    card.hass.states[id].attributes.last_result = { seconds: 42, completed_at: '2026-09-13T13:30:00Z' };
  });
  await page.locator('f1-viewing-controls > details > summary').click();
  await page.locator('f1-viewing-controls .calibration summary').click();
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
});

async function profile(page, time_format, language = 'en-US', time_zone = 'server') {
  await page.evaluate(locale => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, locale, config: { ...card.hass.config, time_zone: 'UTC' } };
  }, { language, time_format, time_zone });
}

async function clocks(page, twelve) {
  const values = [
    [page.locator('.schedule time').first(), twelve ? /10:30\s*AM/ : /10:30/],
    [page.locator('.documents li').first().getByText(/^Published:/), twelve ? /03:00\s*PM|3:00\s*PM/ : /15:00/],
    [page.locator('.event-meta time').first(), twelve ? /01:29:12\s*PM/ : /13:29:12/],
    [page.locator('f1-track-map-view .driver-list button').first(), twelve ? /01:30:00\s*PM/ : /13:30:00/],
    [page.getByText(/^Last calibration:/), twelve ? /01:30\s*PM|1:30\s*PM/ : /13:30/],
    [page.locator('.frozen'), twelve ? /01:30:00\s*PM/ : /13:30:00/],
  ];
  for (const [node, pattern] of values) {
    await expect(node).toContainText(pattern);
    if (!twelve) await expect(node).not.toContainText(/AM|PM/);
  }
}

test('all clock displays follow explicit 12 and 24 hour profile changes without a reload', async ({ page }) => {
  await profile(page, '12');
  await clocks(page, true);
  await profile(page, '24');
  await clocks(page, false);
});

test('language and system clock preferences are independent of the interface language', async ({ page }) => {
  await profile(page, 'language', 'en-US');
  await clocks(page, true);
  await profile(page, 'system', 'en-US');
  // The fixture browser uses en-GB: system preference must override en-US UI language.
  await clocks(page, false);
});

test('24 hour midnight is 00 and clock displays honor local and explicit time zones', async ({ page }) => {
  await page.evaluate(() => { window.fixtureCard.frozenAt = Date.parse('2026-09-13T00:00:00Z'); });
  await profile(page, '24');
  await expect(page.locator('.frozen')).toContainText('00:00:00');
  await profile(page, '24', 'en-US', 'local');
  await expect(page.locator('.frozen')).toContainText('17:00:00');
  await profile(page, '24', 'en-US', 'Europe/Stockholm');
  await expect(page.locator('.frozen')).toContainText('02:00:00');
});
