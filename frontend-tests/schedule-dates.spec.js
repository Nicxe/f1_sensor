const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test('an ambiguous archive with a hidden selector offers keyboard access to temporary selection without saving configuration', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'archive', options: { year: 2024, show_session_selector: false } }] } });
    const card = window.fixtureCard;
    card.previewData = { ...card.previewData, history: query => ({ status: 'ready', data: { payload: query.type.endsWith('/catalog') ? {
      year: 2024, meetings: [{ meeting_key: 'ambiguous', round: 1, name: 'Dated Grand Prix', circuit_timezone: 'UTC', sessions: [
        { session_key: 'sprint', kind: 'sprint', name: 'Sprint', date: '2024-03-09', start: null, start_precision: 'date' },
        { session_key: 'qualifying', kind: 'qualifying', name: 'Qualifying', start: '2024-03-09T15:00:00Z' },
      ] }],
    } : { results: [] } } }) };
  });
  const session = page.getByRole('combobox', { name: 'Session', exact: true });
  await expect(session).toHaveCount(0);
  const choose = page.getByRole('button', { name: 'Choose a recorded session', exact: true });
  await choose.focus();
  await page.keyboard.press('Enter');
  await expect(session).toBeFocused();
  await session.selectOption('sprint');
  await expect(session).toHaveValue('sprint');
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].options.show_session_selector)).toBe(false);
  expect(await page.evaluate(() => window.savedConfig)).toBeUndefined();
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);
});

test('an explicitly cancelled archive session remains manually selectable with an explanation', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'archive', options: { year: 2024, round: '1', session_key: 'race' } }] } });
    const card = window.fixtureCard;
    card.previewData = { ...card.previewData, history: query => ({ status: 'ready', data: { payload: query.type.endsWith('/catalog') ? {
      year: 2024, meetings: [{ meeting_key: 'cancelled', round: 1, name: 'Cancelled Grand Prix', sessions: [
        { session_key: 'race', kind: 'race', name: 'Race', start: '2024-03-09T15:00:00Z', cancelled: true },
      ] }],
    } : { results: [] } } }) };
  });
  await expect(page.getByRole('combobox', { name: 'Session', exact: true })).toHaveValue('race');
  await expect(page.getByText('This session was cancelled. Any available records are shown below.', { exact: true })).toBeVisible();
});

for (const transport of ['entity', 'direct']) {
  test(`next-race dates remain readable without a timestamp through ${transport} data`, async ({ page }) => {
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.evaluate(transport => {
      window.mountModular({ config: { modules: [
        { type: 'overview', fields: ['meeting', 'countdown'] },
        { type: 'calendar', options: { sessions: ['race', 'practice_1'] } },
      ] } });
      const card = window.fixtureCard, id = card.entry.entities.next_race;
      const attributes = { race_name: 'Time pending Grand Prix', race_date: '2026-09-20', first_practice_date: '2026-09-18', race_start_utc: null, circuit_timezone: 'Europe/Rome' };
      card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { state: 'unknown', attributes } } };
      if (transport === 'direct') {
        card.entry.data_api = { enabled: ['next_race'] };
        card.entry.card_data = { next_race: { status: 'ready', data: { status: 'ready', source: 'static', payload: { state: null, attributes } } } };
      }
      card.previewData = { ...card.previewData, now: Date.parse('2026-09-17T12:00:00Z') };
    }, transport);
    await expect(page.locator('.schedule time')).toHaveCount(2);
    await expect(page.getByText('Start time not published', { exact: true })).toHaveCount(2);
    const overview = page.getByRole('region', { name: 'Overview', exact: true });
    await expect(overview.locator('.metric').filter({ hasText: 'Countdown' }).locator('strong')).toHaveText('—');
    for (const time of await page.locator('.schedule time').all()) await expect(time).not.toContainText(':');
    expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);
  });
}

test('legacy archive does not use final as proof of a date-only start and retains old dated races', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-09-20T12:00:00Z'));
  await page.goto('/frontend-tests/fixture.html');
  await page.waitForFunction(() => typeof window.mountF1Element === 'function');
  await page.evaluate(async () => {
    await window.mountF1Element({ type: 'f1-last-race-results-card' });
    const card = document.querySelector('f1-last-race-results-card');
    window.dateCatalog = { year: 2026, meetings: [{ meeting_key: 'dated-meeting', round: 1, name: 'Dated Grand Prix', circuit_timezone: 'UTC', sessions: [
      { session_key: 'qualifying', name: 'Qualifying', kind: 'qualifying', start: '2026-09-19T15:00:00Z', coverage: { results: 'available' }, final: true },
      { session_key: 'race', name: 'Race', kind: 'race', date: '2026-09-20', start: null, start_precision: 'date', coverage: { results: 'available' }, final: true },
    ] }] };
    card.hass = { ...card.hass, callWS: async query => query.type.endsWith('/catalog') ? window.dateCatalog : { results: [] } };
    card.setConfig({ ...card.config, history_entry_id: 'dates', history_year: 2026 });
    await card._switchResultScope('archive');
  });
  const session = page.getByRole('combobox', { name: 'Session', exact: true });
  await expect(session).toHaveValue('qualifying');
  await page.evaluate(async () => {
    window.dateCatalog.meetings[0].sessions[1].date = '2026-09-19';
    await document.querySelector('f1-last-race-results-card')._loadArchiveCatalog(true);
  });
  // An unknown time on the same day as qualifying cannot establish which was last.
  await expect(session).toHaveValue('');
  await expect(page.getByText('No session matches this selection. Choose another event or session.', { exact: true })).toBeVisible();
  await session.selectOption('race');
  await expect(session).toHaveValue('race');
  await expect(page.getByText('No classification is available for this session.', { exact: true })).toBeVisible();
  await page.evaluate(async () => {
    window.dateCatalog.meetings[0].sessions[1].cancelled = true;
    await document.querySelector('f1-last-race-results-card')._loadArchiveCatalog(true);
  });
  await expect(session).toHaveValue('race');
  await expect(page.getByText('This session was cancelled. Any available records are shown below.', { exact: true })).toBeVisible();
});
