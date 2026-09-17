const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test('calendar options survive editor reload and show meaningful past, next and empty states', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'calendar', options: { range: 'season', sessions: ['race'] } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  for (const name of ['Round', 'Circuit', 'Location']) await editor.getByRole('checkbox', { name, exact: true }).check();
  await editor.getByLabel('Past session starts', { exact: true }).selectOption('dim');
  await editor.getByLabel('Next session marker', { exact: true }).selectOption('label');
  const saved = await page.evaluate(() => JSON.parse(JSON.stringify(window.savedConfig)));
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(config => {
    window.mountModular({ config });
    const card = window.fixtureCard, entry = card.entry;
    entry.entities.current_season = 'sensor.audit_season';
    card.hass = { ...card.hass, states: { ...card.hass.states, 'sensor.audit_season': { state: '2026', attributes: { races: [
      { round: '1', raceName: 'Past meeting', date: '2026-09-01', time: '12:00:00Z', Circuit: { circuitName: 'First circuit', Location: { locality: 'Town', country: 'Country' } } },
      { round: '2', raceName: 'Next meeting', date: '2026-10-01', time: '12:00:00Z' },
    ] } } } };
    card.previewData = { ...card.previewData, now: Date.parse('2026-09-14T12:00:00Z') };
  }, saved);
  const card = page.locator('f1-sensor-card');
  await expect(card.getByText('Round 1', { exact: true })).toBeVisible();
  await expect(card.getByText('First circuit', { exact: true })).toBeVisible();
  await expect(card.getByText('Town, Country', { exact: true })).toBeVisible();
  await expect(card.getByText('Start time passed', { exact: true })).toBeVisible();
  await expect(card.getByText('Next session', { exact: true })).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);
  await page.evaluate(() => { const card = window.fixtureCard; const config = structuredClone(card.config); config.modules[0].options.past = 'hide'; card.setConfig(config); });
  await expect(card.getByText('Past meeting', { exact: true })).toHaveCount(0);
  await expect(card.getByText('Next meeting', { exact: true })).toBeVisible();
  await page.evaluate(() => { const card = window.fixtureCard; card.previewData = { ...card.previewData, now: Date.parse('2027-01-01T00:00:00Z') }; });
  await expect(card.getByText('All selected sessions are in the past and are hidden.', { exact: true })).toBeVisible();
});

test('calendar flags obey appearance settings and recover from image failure without losing the event', async ({ page }) => {
  await page.route('https://flags.example/**', route => route.request().url().endsWith('/missing.svg') ? route.abort() : route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="27"><rect width="40" height="27" fill="#2266bb"/></svg>' }));
  await page.goto('/frontend-tests/modular.html'); await page.waitForFunction(() => window.modularReady);
  await page.setViewportSize({ width: 320, height: 900 });
  await page.evaluate(() => {
    window.mountModular({ config: { appearance: { flags: true }, modules: [{ type: 'calendar', options: { sessions: ['race'] } }] } });
    const card = window.fixtureCard, id = card.entry.entities.next_race;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], attributes: { ...card.hass.states[id].attributes, country_flag_url: 'https://flags.example/first.svg', circuit_country: 'Test country' } } } };
  });
  const card = page.locator('f1-sensor-card'), flag = card.getByRole('img', { name: 'Test country', exact: true });
  await expect(flag).toBeVisible();
  await expect(card.locator('.schedule time')).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, id = card.entry.entities.next_race;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], attributes: { ...card.hass.states[id].attributes, country_flag_url: 'https://flags.example/missing.svg' } } } };
  });
  await expect(flag).toHaveCount(0);
  await expect(card.locator('.flag-fallback')).toBeVisible();
  await expect(card.locator('.flag-fallback')).toHaveText('Test country');
  await expect(card.locator('.schedule time')).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, id = card.entry.entities.next_race;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], attributes: { ...card.hass.states[id].attributes, country_flag_url: 'https://flags.example/recovered.svg' } } } };
  });
  await expect(flag).toBeVisible();
  await expect(card.locator('.flag-fallback')).toBeHidden();
  await page.emulateMedia({ forcedColors: 'active' });
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { const card = window.fixtureCard; const config = structuredClone(card.config); config.appearance.flags = false; card.setConfig(config); });
  await expect(card.locator('.schedule img')).toHaveCount(0);
  await expect(card.locator('.schedule time')).toBeVisible();
});

test('date-only calendar entries keep their published date across timezones and gain a clock only when published', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html'); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { appearance: { flags: false }, modules: [{ type: 'calendar', options: { range: 'season', sessions: ['race'], next: 'label' } }] } });
    const card = window.fixtureCard;
    card.entry.entities.current_season = 'sensor.dates';
    card.hass = { ...card.hass, locale: { ...card.hass.locale, time_format: '12', time_zone: 'America/Los_Angeles' }, states: { ...card.hass.states, 'sensor.dates': { state: '2026', attributes: { races: [
      { round: '1', raceName: 'Time pending', date: '2026-09-14', circuit_timezone: 'UTC' },
      { round: '2', raceName: 'Confirmed session', date: '2026-09-14', time: '12:00:00Z', circuit_timezone: 'UTC' },
    ] } } } };
    card.previewData = { ...card.previewData, now: Date.parse('2026-09-13T12:00:00Z') };
  });
  const pending = page.locator('.schedule li').filter({ hasText: 'Time pending' });
  await expect(pending.getByText('Start time not published', { exact: true })).toBeVisible();
  await expect(pending.locator('time')).toHaveAttribute('datetime', '2026-09-14');
  await expect(pending.locator('time')).toContainText('Sep 14');
  await expect(pending.locator('time')).not.toContainText(/AM|PM|:/);
  await expect(page.getByText('Next session', { exact: true })).toHaveCount(0);
  await page.evaluate(() => {
    const card = window.fixtureCard, old = card.hass.states['sensor.dates'];
    card.hass = { ...card.hass, states: { ...card.hass.states, 'sensor.dates': { ...old, attributes: { ...old.attributes, races: old.attributes.races.map((race, i) => i === 0 ? { ...race, time: '10:00:00Z' } : race) } } } };
  });
  await expect(pending.getByText('Start time not published', { exact: true })).toHaveCount(0);
  await expect(pending.locator('time')).toContainText(/03:00\s*AM/);
  await expect(pending.getByText('Next session', { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);
});
