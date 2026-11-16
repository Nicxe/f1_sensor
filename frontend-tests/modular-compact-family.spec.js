const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.setViewportSize({ width: 1200, height: 1100 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

const moduleView = (page, id) => page.locator(`f1-module-view[data-module-id="${id}"]`);
const normalizedText = value => value.replace(/\s+/g, ' ').trim();

async function compact(page) {
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
}

for (const mode of ['dark', 'light']) {
  test(`results and standings retain classification, source meaning and numeric alignment in compact ${mode} mode`, async ({ page }) => {
    await page.evaluate(mode => window.mountModular({ config: {
      appearance: { mode, logos: false },
      modules: [
        { id: 'results', type: 'results', fields: ['result_position', 'driver', 'team', 'result_time', 'points'], options: { rows: 3 } },
        { id: 'standings', type: 'standings', fields: ['result_position', 'driver', 'team', 'points', 'wins'], options: { rows: 3 } },
      ],
    } }), mode);
    const results = moduleView(page, 'results'), standings = moduleView(page, 'standings');
    await expect(results.locator('tbody tr')).toHaveCount(3);
    await expect(standings.locator('tbody tr')).toHaveCount(3);
    await expect(results).toContainText('1:24:10.456');
    await expect(standings).toContainText('Published standings');
    const before = {
      results: (await results.locator('tbody tr').allTextContents()).map(normalizedText),
      standings: (await standings.locator('tbody tr').allTextContents()).map(normalizedText),
      fields: await page.evaluate(() => window.fixtureCard.config.modules.map(module => module.fields)),
      padding: await results.locator('tbody td').first().evaluate(node => parseFloat(getComputedStyle(node).paddingTop)),
    };
    await compact(page);
    await expect(results).toHaveAttribute('data-presentation', 'minimal');
    await expect(standings).toHaveAttribute('data-presentation', 'minimal');
    expect((await results.locator('tbody tr').allTextContents()).map(normalizedText)).toEqual(before.results);
    expect((await standings.locator('tbody tr').allTextContents()).map(normalizedText)).toEqual(before.standings);
    expect(await page.evaluate(() => window.fixtureCard.config.modules.map(module => module.fields))).toEqual(before.fields);
    await expect(standings).toContainText('Published standings');
    await expect(results.locator('tbody tr').first().locator('td').nth(1)).toHaveCSS('text-align', 'left');
    await expect(results.locator('tbody tr').first().locator('td').nth(2)).toHaveCSS('text-align', 'left');
    await expect(results.locator('tbody tr').first().locator('td').nth(4)).toHaveCSS('text-align', 'right');
    const afterPadding = await results.locator('tbody td').first().evaluate(node => parseFloat(getComputedStyle(node).paddingTop));
    expect(afterPadding).toBeLessThan(before.padding);
    await results.getByRole('button', { name: /LEC/ }).click();
    await expect(results).toContainText('Charles Leclerc');
  });

  test(`compact planning keeps the full schedule, time zones and unknown status in ${mode} mode`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await page.evaluate(mode => window.mountModular({ config: {
      appearance: { mode, logos: false, flags: false },
      modules: [
        { id: 'overview', type: 'overview', fields: ['meeting', 'session', 'track_status', 'lap_progress', 'session_rain_risk'] },
        { id: 'calendar', type: 'calendar', options: { timezone: 'utc', show_track_time: true } },
      ],
    } }), mode);
    const overview = moduleView(page, 'overview'), calendar = moduleView(page, 'calendar');
    await expect(calendar.locator('.schedule li')).toHaveCount(5);
    await expect(overview).toContainText('Demo Grand Prix');
    await expect(overview).toContainText('Session rain risk');
    const before = {
      rows: (await calendar.locator('.schedule li').allTextContents()).map(normalizedText),
      times: await calendar.locator('time').evaluateAll(nodes => nodes.map(node => node.dateTime)),
    };
    await compact(page);
    await expect(overview).toHaveAttribute('data-presentation', 'minimal');
    await expect(calendar).toHaveAttribute('data-presentation', 'minimal');
    expect((await calendar.locator('.schedule li').allTextContents()).map(normalizedText)).toEqual(before.rows);
    expect(await calendar.locator('time').evaluateAll(nodes => nodes.map(node => node.dateTime))).toEqual(before.times);
    await expect(calendar).toContainText('UTC');
    await expect(calendar).toContainText('Europe/Rome');
    await expect(overview).toContainText('Session rain risk');
    await page.evaluate(() => {
      const demo = window.fixtureDemo;
      demo.hass.states[demo.preview.entries[0].entities.track_status].state = 'unavailable';
      window.fixtureCard.hass = { ...demo.hass };
    });
    const status = overview.locator('.metric').filter({ hasText: 'Track status' });
    await expect(status).toContainText('—');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('compact incidents and documents retain decisions, long titles, missing links and full published context on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1100 });
  const title = 'Demo · Provisional starting grid · ' + 'Additional notes from the stewards about the current session. '.repeat(5);
  await page.evaluate(title => {
    window.mountModular({ config: { appearance: { logos: false }, modules: [
      { id: 'incidents', type: 'incidents' },
      { id: 'documents', type: 'documents' },
    ] } });
    const demo = window.fixtureDemo, entity = demo.preview.entries[0].entities.fia_documents;
    demo.hass.states[entity].attributes.documents[0].name = title;
    window.fixtureCard.hass = { ...demo.hass };
  }, title);
  const incidents = moduleView(page, 'incidents'), documents = moduleView(page, 'documents');
  await expect(incidents).toContainText('Under investigation');
  await expect(incidents).toContainText('5 SECOND TIME PENALTY');
  await expect(documents.getByRole('link', { name: /Provisional starting grid/ })).toBeVisible();
  const before = (await incidents.locator('dl').allTextContents()).map(normalizedText);
  await compact(page);
  await expect(incidents).toHaveAttribute('data-presentation', 'minimal');
  await expect(documents).toHaveAttribute('data-presentation', 'minimal');
  expect((await incidents.locator('dl').allTextContents()).map(normalizedText)).toEqual(before);
  await expect(incidents).toContainText('Under investigation');
  await expect(incidents).toContainText('5 SECOND TIME PENALTY');
  const link = documents.getByRole('link', { name: /Provisional starting grid/ });
  await expect(link).toContainText(title.trim());
  await expect(link).toHaveAttribute('href', 'https://www.fia.com/documents');
  await expect(documents).toContainText('Document link unavailable');
  await expect(documents).toContainText('Published:');
  const lines = await link.evaluate(node => node.getBoundingClientRect().height / parseFloat(getComputedStyle(node).lineHeight));
  expect(lines).toBeGreaterThan(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const audit = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(audit.violations.filter(item => ['critical', 'serious'].includes(item.impact))).toEqual([]);
});

test('compact analysis keeps local estimates, evidence limits and unavailable event inspection honest', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { appearance: { logos: false }, modules: [
    { id: 'strategy', type: 'strategy', fields: ['driver', 'tyre', 'clean_pace', 'clean_samples', 'analysis_quality'] },
    { id: 'battles', type: 'battles', fields: ['battle_status', 'incident_drivers', 'battle_gap', 'analysis_source', 'analysis_quality'] },
    { id: 'timeline', type: 'timeline', options: { event_focus: true } },
  ] } }));
  const strategy = moduleView(page, 'strategy'), battles = moduleView(page, 'battles'), timeline = moduleView(page, 'timeline');
  await expect(strategy).toContainText('Local estimate');
  await expect(strategy.locator('tbody tr')).toHaveCount(5);
  await expect(battles.locator('.incident-list li')).toHaveCount(1);
  const before = {
    strategy: (await strategy.locator('tbody tr').allTextContents()).map(normalizedText),
    battles: (await battles.locator('.incident-list dl').allTextContents()).map(normalizedText),
    timeline: (await timeline.locator('.incident-list dl').allTextContents()).map(normalizedText),
  };
  await compact(page);
  for (const view of [strategy, battles, timeline]) await expect(view).toHaveAttribute('data-presentation', 'minimal');
  expect((await strategy.locator('tbody tr').allTextContents()).map(normalizedText)).toEqual(before.strategy);
  expect((await battles.locator('.incident-list dl').allTextContents()).map(normalizedText)).toEqual(before.battles);
  expect((await timeline.locator('.incident-list dl').allTextContents()).map(normalizedText)).toEqual(before.timeline);
  await expect(strategy).toContainText('Local estimate');
  await expect(strategy).toContainText('Evidence score measures support, not probability.');
  await expect(battles.getByText(/Timing/).first()).toBeVisible();
  const focus = timeline.getByRole('button', { name: 'Inspect event', exact: true }).first();
  await expect(focus).toBeVisible();
  await expect(focus).toBeDisabled();
  await expect(timeline).toContainText('Demo · cars 16 and 4 exchanged position');
});

test('compact replay keeps selected session, transport, position, secondary selectors and scope context', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: {
    modules: [{ id: 'replay', type: 'replay', options: { display: 'full', secondary_selects: true, start_reference: true, status_details: true } }],
  } }));
  const replay = moduleView(page, 'replay');
  await expect(replay).toContainText('Demo Grand Prix · Race');
  await expect(replay.getByRole('button', { name: 'Play replay', exact: true })).toBeDisabled();
  await replay.getByText('Choose replay', { exact: true }).click();
  await expect(replay.getByLabel('Start reference', { exact: true })).toBeVisible();
  const before = {
    options: await page.evaluate(() => structuredClone(window.fixtureCard.config.modules[0].options)),
    year: await replay.getByLabel('Replay year', { exact: true }).inputValue(),
    session: await replay.getByLabel('Recorded session', { exact: true }).inputValue(),
    position: await replay.getByRole('slider', { name: 'Replay position in seconds', exact: true }).inputValue(),
  };
  await compact(page);
  await expect(replay).toHaveAttribute('data-presentation', 'minimal');
  await expect(replay.getByLabel('Replay year', { exact: true })).toHaveValue(before.year);
  await expect(replay.getByLabel('Recorded session', { exact: true })).toHaveValue(before.session);
  await expect(replay.getByRole('slider', { name: 'Replay position in seconds', exact: true })).toHaveValue(before.position);
  await expect(replay.getByLabel('Start reference', { exact: true })).toBeVisible();
  await expect(replay).toContainText('Controls replay for');
  await expect(replay).toContainText('Replay controls are disabled in previews.');
  await expect(replay.getByRole('button', { name: 'Play replay', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].options)).toEqual(before.options);
});
