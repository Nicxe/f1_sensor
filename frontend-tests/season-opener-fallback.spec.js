const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const provisionalNotice = 'The race date is confirmed. The start time and countdown use a provisional estimate until the start time is published.';

async function mountFallback(page, { language = 'en', scene = 'race' } = {}) {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(({ language, scene }) => {
    window.mountModular({ language, scene, config: { modules: [
      { type: 'overview', fields: ['meeting', 'countdown'] },
      { type: 'calendar', options: { sessions: ['race'], timezone: 'circuit' } },
    ] } });
    const card = window.fixtureCard, id = card.entry.entities.next_race;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: {
      state: '2027-03-14T15:00:00+00:00', attributes: {
        season: '2027', round: '1', race_name: 'Bahrain Grand Prix',
        circuit_name: 'Bahrain International Circuit', circuit_locality: 'Sakhir', circuit_country: 'Bahrain',
        circuit_timezone: 'Asia/Bahrain', race_start_utc: '2027-03-14T15:00:00+00:00',
        schedule_source: 'official_calendar_fallback', race_start_estimated: true,
        schedule_source_url: 'https://www.formula1.com/en/racing/2027/bahrain',
      },
    } } };
    card.previewData = { ...card.previewData, now: Date.parse('2027-03-13T15:00:00Z') };
  }, { language, scene });
}

test('season opener countdown and schedule disclose the provisional start until the API replaces it', async ({ page }) => {
  await mountFallback(page);
  const overview = page.getByRole('region', { name: 'Overview', exact: true });
  const countdown = overview.locator('.metric').filter({ hasText: 'Countdown' });
  const race = page.locator('.schedule li');
  await expect(countdown.locator('strong')).toHaveText('1 day 0 hours');
  await expect(countdown.getByText('Provisional start time', { exact: true })).toBeVisible();
  await expect(overview.getByText(provisionalNotice, { exact: true })).toBeVisible();
  await expect(race.getByText('Provisional start time', { exact: true })).toBeVisible();
  await expect(race.locator('time')).toContainText('18:00');
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);

  await page.evaluate(() => {
    const card = window.fixtureCard, id = card.entry.entities.next_race, previous = card.hass.states[id];
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: {
      ...previous, state: '2027-03-14T16:00:00+00:00', attributes: {
        ...previous.attributes, race_start_utc: '2027-03-14T16:00:00+00:00',
        schedule_source: 'jolpica', race_start_estimated: false, schedule_source_url: null,
      },
    } } };
  });
  await expect(countdown.locator('strong')).toHaveText('1 day 1 hour');
  await expect(page.getByText('Provisional start time', { exact: true })).toHaveCount(0);
  await expect(page.getByText(provisionalNotice, { exact: true })).toHaveCount(0);
  await expect(race.locator('time')).toContainText('19:00');
});

test('untranslated provisional schedule text falls back to the English source catalog', async ({ page }) => {
  await mountFallback(page, { language: 'sv' });
  await expect(page.getByText('Provisional start time', { exact: true })).toHaveCount(2);
  await expect(page.getByText(provisionalNotice, { exact: true })).toBeVisible();
});

test('a replay overview does not inherit the upcoming season opener estimate', async ({ page }) => {
  await mountFallback(page, { scene: 'replay' });
  const overview = page.getByRole('region', { name: 'Overview', exact: true });
  await expect(overview.getByText('Not available for replay', { exact: true })).toBeVisible();
  await expect(overview.getByText('Provisional start time', { exact: true })).toHaveCount(0);
  await expect(overview.getByText(provisionalNotice, { exact: true })).toHaveCount(0);
});
