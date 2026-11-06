const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { mountRaceTrace } = require('./race-trace-fixture.cjs');

test('Race Trace editor keeps an explicit reference and distinguishes the anchor from the visible range', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'lap_chart' }] } });
    window.fixtureCard.entries = window.fixtureDemo.preview.entries;
  });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByRole('checkbox', { name: 'Pit stop', exact: true })).toHaveCount(0);
  await editor.getByLabel('Measure', { exact: true }).selectOption({ label: 'Race Trace' });
  await expect(editor.getByRole('checkbox', { name: 'Pit stop', exact: true })).not.toBeChecked();
  await editor.getByRole('checkbox', { name: 'Pit stop', exact: true }).check();
  await editor.getByRole('checkbox', { name: 'Safety Car', exact: true }).check();
  await expect(editor.getByLabel('Reference driver', { exact: true })).toHaveValue('');
  await editor.getByLabel('Reference driver', { exact: true }).selectOption('4');
  await editor.getByRole('checkbox', { name: 'Charles Leclerc', exact: true }).check();
  await editor.getByLabel('Reset after lap (0 = automatic)', { exact: true }).fill('12');
  await editor.getByLabel('Reset after lap (0 = automatic)', { exact: true }).press('Tab');
  await editor.getByLabel('First lap (0 = first observed)', { exact: true }).fill('20');
  await editor.getByLabel('First lap (0 = first observed)', { exact: true }).press('Tab');
  await expect(editor.getByLabel('Maximum drivers', { exact: true })).toHaveCount(0);
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].options).toMatchObject({ metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['16'], anchor_lap: 12, start_lap: 20, event_markers: ['pit', 'sc'] });
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ editor: true, config }), saved);
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByLabel('Reference driver', { exact: true })).toHaveValue('4');
  await expect(editor.getByLabel('Reset after lap (0 = automatic)', { exact: true })).toHaveValue('12');
  await expect(editor.getByLabel('First lap (0 = first observed)', { exact: true })).toHaveValue('20');
  await expect(editor.getByRole('checkbox', { name: 'Pit stop', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'Safety Car', exact: true })).toBeChecked();
  await editor.getByLabel('Measure', { exact: true }).selectOption('lap_time');
  await expect(editor.getByRole('checkbox', { name: 'Pit stop', exact: true })).toHaveCount(0);
  await editor.getByLabel('Measure', { exact: true }).selectOption('cumulative_lap_delta');
  await expect(editor.getByRole('checkbox', { name: 'Pit stop', exact: true })).toBeChecked();
});

test('Race Trace presents the same signed millisecond values in the chart, keyboard details and table', async ({ page }) => {
  await mountRaceTrace(page);
  const chart = page.locator('f1-series-chart');
  await expect(chart.getByText('Zeroed after lap 1', { exact: true })).toBeVisible();
  await expect(chart.getByText('Reference: Lando Norris · 4', { exact: true })).toBeVisible();
  await expect(chart.locator('.zero-line')).toHaveCount(1);
  const rows = chart.locator('tbody tr');
  await expect(rows.nth(0).locator('td').nth(1)).toHaveText('0.000 s');
  await expect(rows.nth(1).locator('td').nth(1)).toHaveText('-0.500 s');
  await expect(rows.nth(2).locator('td').nth(1)).toHaveText('+0.500 s');
  await expect(rows.nth(3).locator('td').nth(1)).toHaveText('+20.500 s');
  const inspect = chart.getByRole('slider', { name: 'Inspect lap', exact: true });
  await inspect.focus();
  await inspect.press('ArrowRight');
  await expect(chart.getByRole('tooltip')).toContainText('Lap 2');
  await expect(chart.getByRole('tooltip')).toContainText('-0.500 s');
  await expect(inspect).toHaveAttribute('aria-valuetext', /Oscar Piastri: -0.500 s/);
  await inspect.press('End');
  await expect(chart.getByRole('tooltip')).toContainText('+20.500 s');
  await inspect.press('Escape');
  await expect(chart.getByRole('tooltip')).toHaveCount(0);
  const calls = await page.evaluate(() => window.raceTrace.calls);
  expect(calls.filter(call => Array.isArray(call) || call.type?.includes('seek'))).toEqual([]);
  const localized = await page.evaluate(() => {
    const card = window.raceTrace.cards[0];
    card.hass = { ...card.hass, locale: { ...card.hass.locale, language: 'sv' } };
    return `${new Intl.NumberFormat('sv', { minimumFractionDigits: 3, maximumFractionDigits: 3, signDisplay: 'exceptZero' }).format(-0.5)} s`;
  });
  await expect(rows.nth(1).locator('td').nth(1)).toHaveText(localized);
});

test('Race Trace shows broken cumulative lines and keeps isolated anchors visible even with points disabled', async ({ page }) => {
  await mountRaceTrace(page, { config: { modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], presentation: 'both', show_points: false } }] } });
  await page.evaluate(() => window.raceTrace.send('driver_positions', snapshot => { delete snapshot.payload.attributes.drivers[1].laps['2']; }));
  const chart = page.locator('f1-series-chart');
  await expect(chart.locator('[data-series="81"] .series-line')).toHaveCount(1);
  await expect(chart.locator('[data-series="81"] .marker')).toHaveCount(1);
  const rows = chart.locator('tbody tr');
  await expect(rows.nth(1).locator('td').nth(1)).toContainText('—');
  await expect(rows.nth(1).locator('td').nth(1)).toContainText('Lap time missing');
  await expect(rows.nth(3).locator('td').nth(1)).toContainText('An earlier lap is missing or uncertain');
  await page.evaluate(() => window.raceTrace.send('driver_positions', snapshot => { snapshot.payload.attributes.drivers[1].laps['2'] = 89.5; }));
  await expect(rows.nth(3).locator('td').nth(1)).toHaveText('+20.500 s');
});

for (const width of [360, 1280]) test(`Race Trace is readable without color and keyboard accessible at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 900 });
  await mountRaceTrace(page, { config: { modules: [{ type: 'lap_chart', show_header: false, options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81', '16', '63'], presentation: 'chart' } }] } });
  const chart = page.locator('f1-series-chart');
  await expect(chart.getByText('Reference: Lando Norris · 4', { exact: true })).toBeVisible();
  const styles = await chart.locator('.series-line').evaluateAll(lines => lines.map(line => line.style.strokeDasharray));
  expect(new Set(styles).size).toBe(4);
  const slider = chart.getByRole('slider', { name: 'Inspect lap', exact: true });
  await slider.focus(); await slider.press('End');
  await expect(chart.getByRole('tooltip')).toContainText('George Russell');
  await chart.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(chart.getByRole('columnheader', { name: 'Oscar Piastri', exact: true })).toBeVisible();
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(axe.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath(`race-trace-${width}.png`), fullPage: true });
});

test('Race Trace editor discovers driver choices on a sensor-free direct backend and explains the four-driver limit', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0, entries: 2 });
  await page.evaluate(() => {
    const editor = document.createElement('f1-sensor-card-editor');
    editor.hass = { ...window.raceTrace.hass, states: {} };
    editor.setConfig({ f1_entry_id: window.raceTrace.entries[0].entry_id, modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta' } }] });
    window.raceTrace.editor = editor; document.querySelector('#root').append(editor);
  });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByLabel('Reference driver', { exact: true }).getByRole('option', { name: 'Lando Norris', exact: true })).toHaveCount(1);
  await editor.getByLabel('Reference driver', { exact: true }).selectOption('4');
  for (const name of ['Oscar Piastri', 'Charles Leclerc', 'George Russell']) await editor.getByRole('checkbox', { name, exact: true }).check();
  await expect(editor.getByRole('checkbox', { name: 'Carlos Sainz', exact: true })).toBeDisabled();
  await expect(editor.getByText(/Choose up to three drivers in addition to the fixed reference/)).toBeVisible();
  await editor.getByRole('checkbox', { name: 'Oscar Piastri', exact: true }).uncheck();
  await expect(editor.getByRole('checkbox', { name: 'Carlos Sainz', exact: true })).toBeEnabled();
  expect(await editor.evaluate(node => node.config.modules[0].options.selected)).toEqual(['16', '63']);
  await page.evaluate(() => {
    const entryId = window.raceTrace.entries[1].entry_id;
    window.raceTrace.snapshot('driver_list', entryId).payload.attributes.drivers[0].name = 'Second roster Norris';
    const editor = window.raceTrace.editor;
    editor.setConfig({ ...editor.config, f1_entry_id: entryId });
  });
  await expect(editor.getByLabel('Reference driver', { exact: true }).getByRole('option', { name: 'Second roster Norris', exact: true })).toHaveCount(1);
  expect(await page.evaluate(() => window.raceTrace.records.filter(record => record.active && record.message?.data_keys?.includes('driver_list')).map(record => record.message.entry_id))).toEqual(['trace-1']);
  await page.evaluate(() => window.raceTrace.editor.remove());
  expect(await page.evaluate(() => window.raceTrace.diagnostics())).toMatchObject({ resources: 0, consumers: 0, activeSubscriptions: 0, connectionListeners: 0 });
});

test('native editor sample preview shows a labelled Race Trace without changing real data or allowing a seek', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['16'], event_markers: ['pit', 'vsc'] } }] } });
    window.fixtureCard.entries = window.fixtureDemo.preview.entries;
    window.traceOriginalStates = JSON.stringify(window.fixtureDemo.hass.states);
  });
  const preview = page.locator('#native-preview f1-sensor-card');
  await expect(preview.getByLabel('Preview data', { exact: true })).toHaveValue('sample');
  await expect(preview.getByText('DEMO · sample data', { exact: true })).toBeVisible();
  await expect(preview.locator('f1-series-chart')).toBeVisible();
  await expect(preview.locator('.event-point')).toHaveCount(2);
  await preview.locator('.event-point[data-kind="pit"]').click();
  await expect(preview.getByRole('tooltip')).toContainText('Pit stop · Charles Leclerc · lap 11');
  await preview.getByRole('slider', { name: 'Inspect lap', exact: true }).focus();
  await preview.getByRole('slider', { name: 'Inspect lap', exact: true }).press('End');
  await expect(preview.getByRole('tooltip')).toContainText('Charles Leclerc');
  await preview.getByLabel('Sample session', { exact: true }).selectOption('qualifying');
  await expect(preview.locator('f1-series-chart')).toHaveCount(0);
  await expect(preview.getByText('Race Trace is available for Race and Sprint sessions.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify(window.fixtureDemo.hass.states))).toBe(await page.evaluate(() => window.traceOriginalStates));
});

test('Race Trace waits for a missing fixed reference instead of silently selecting another driver', async ({ page }) => {
  await mountRaceTrace(page, { config: { modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '99', selected: ['81'] } }] } });
  await expect(page.getByText('The chosen reference is missing from this session. Choose another reference to change it.', { exact: true })).toBeVisible();
  await expect(page.locator('f1-series-chart')).toHaveCount(0);
  expect(await page.evaluate(() => window.raceTrace.cards[0].config.modules[0].options.reference_driver)).toBe('99');
});

// Renderer boundary: marker identities/anchors are validated by raceTraceMarkers.
// These fixtures isolate display equivalence; source/context guards are covered separately.
const markerEvents = [
  { id: 'pit-81', revision: 1, kind: 'pit', phase: 'point', driver: '81', lap: 2, anchor_type: 'driver_lap', source: 'PitStopSeries', description: null },
  { id: 'sc-start', revision: 1, kind: 'sc', phase: 'start', driver: '4', lap: 2, anchor_type: 'reference_driver_lap', source: 'TrackStatus', description: null },
  { id: 'vsc-ending', revision: 1, kind: 'vsc', phase: 'ending', driver: '4', lap: 3, anchor_type: 'reference_driver_lap', source: 'TrackStatus', description: null },
  { id: 'sc-end', revision: 1, kind: 'sc', phase: 'end', driver: '4', lap: 4, anchor_type: 'reference_driver_lap', source: 'TrackStatus', description: null },
  { id: 'red-start', revision: 1, kind: 'red_flag', phase: 'start', driver: '4', lap: 4, anchor_type: 'reference_driver_lap', source: 'TrackStatus', description: '<b>Observed suspension</b>' },
];
async function mountMarkerRenderer(page, markers = { status: 'ready', reason: null, events: markerEvents }) {
  await mountRaceTrace(page, { config: { modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], presentation: 'both', event_markers: ['pit', 'sc', 'vsc', 'red_flag'] } }] } });
  await page.locator('f1-series-chart .series-line').first().waitFor({ state: 'attached' });
  await page.locator('f1-series-chart').evaluate((chart, markers) => { chart.model = { ...chart.model, markers }; }, markers);
  return page.locator('f1-series-chart');
}

test('Race Trace event track, keyboard detail and table share explicit driver and reference anchors', async ({ page }) => {
  const chart = await mountMarkerRenderer(page);
  await chart.evaluate(node => {
    node.model = { ...node.model, series: node.model.series.map(item => item.id !== '81' ? item : { ...item, values: item.values.map(point => point.round !== 2 ? point : { ...point, value: null, delta_ms: null, reason: 'missing_lap' }) }) };
  });
  await expect(chart.locator('.event-point')).toHaveCount(5);
  await expect(chart.locator('tbody tr').nth(1).locator('td').nth(1)).toContainText('Lap time missing');
  const pit = 'Pit stop · Oscar Piastri · lap 2';
  const sc = 'Safety Car · Start observed · after observed reference lap 2 (Lando Norris)';
  await expect(chart.locator('tbody tr').nth(1).locator('.event-cell')).toContainText(pit);
  await expect(chart.locator('tbody tr').nth(1).locator('.event-cell')).toContainText(sc);
  const slider = chart.getByRole('slider', { name: 'Inspect lap', exact: true });
  await slider.focus(); await slider.press('ArrowRight');
  await expect(chart.getByRole('tooltip')).toContainText(pit);
  await expect(chart.getByRole('tooltip')).toContainText(sc);
  await expect(slider).toHaveAttribute('aria-valuetext', new RegExp(pit));
  await slider.press('ArrowRight');
  await expect(chart.getByRole('tooltip')).toContainText('Virtual Safety Car · Ending announced');
  await expect(chart.getByRole('tooltip')).not.toContainText('End observed');
  await slider.press('End');
  await expect(chart.getByRole('tooltip')).toContainText('Safety Car · End observed');
  await expect(chart.getByRole('tooltip')).toContainText('<b>Observed suspension</b>');
  await expect(chart.getByRole('tooltip').locator('b')).toHaveCount(0);
  expect((await page.evaluate(() => window.raceTrace.calls)).filter(call => Array.isArray(call) || call.type?.includes('seek'))).toEqual([]);
});

for (const status of ['pending', 'unsupported']) test(`Race Trace preserves the base curve with ${status} event data and replaces corrected marker details`, async ({ page }) => {
  const chart = await mountMarkerRenderer(page);
  await chart.evaluate((node, status) => { node.model = { ...node.model, markers: { status, reason: 'marker_data_unavailable', events: [] } }; }, status);
  await expect(chart.locator('.event-point')).toHaveCount(0);
  await expect(chart.locator('.event-status')).toContainText(status === 'pending' ? 'Waiting for event markers' : 'Event markers are unavailable');
  await expect(chart.locator('tbody tr').last().locator('td').nth(1)).toHaveText('+20.500 s');
  await chart.evaluate(node => { node.model = { ...node.model, markers: { status: 'ready', reason: null, events: [] } }; });
  await expect(chart.locator('.event-status')).toHaveText('No anchored events in the displayed laps.');
  await chart.evaluate((node, marker) => { node.model = { ...node.model, markers: { status: 'ready', reason: null, events: [{ ...marker, revision: 2, lap: 3 }] } }; }, markerEvents[0]);
  await expect(chart.locator('.event-point')).toHaveCount(1);
  await expect(chart.locator('tbody tr').nth(1).locator('.event-cell')).toHaveText('—');
  await expect(chart.locator('tbody tr').nth(2).locator('.event-cell')).toContainText('Pit stop · Oscar Piastri · lap 3');
});

for (const width of [360, 1280]) test(`Race Trace event markers remain keyboard accessible and equivalent in the table at ${width}px`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width, height: 1000 });
  const chart = await mountMarkerRenderer(page);
  await expect(chart.getByRole('img', { name: 'Event markers', exact: true })).toBeVisible();
  await expect(chart.getByRole('columnheader', { name: 'Event markers', exact: true })).toBeVisible();
  await chart.getByRole('slider', { name: 'Inspect lap', exact: true }).focus();
  await chart.getByRole('slider', { name: 'Inspect lap', exact: true }).press('End');
  await expect(chart.getByRole('tooltip')).toContainText('Red flag · Start observed');
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(axe.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: 'active' });
  await expect(chart.locator('.event-point')).toHaveCount(5);
  await page.screenshot({ path: testInfo.outputPath(`race-trace-markers-${width}.png`), fullPage: true });
});


test('Race Trace retains all 500 accepted marker events and makes the final lap accessible on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  const chart = await mountMarkerRenderer(page);
  await chart.evaluate(node => {
    const rounds = Array.from({ length: 500 }, (_, index) => ({ id: index + 1 }));
    const events = rounds.map(round => ({ id: `pit-${round.id}`, revision: 1, kind: 'pit', phase: 'point', driver: '81', lap: round.id, anchor_type: 'driver_lap', source: 'PitStopSeries' }));
    node.model = { ...node.model, rounds, series: node.model.series.map(item => ({ ...item, values: rounds.map(round => ({ round: round.id, value: 0, delta_ms: 0, reason: null })) })), markers: { status: 'ready', reason: null, events } };
  });
  await expect(chart.locator('.event-point')).toHaveCount(500);
  await expect(chart.locator('tbody .event-cell li')).toHaveCount(500);
  const slider = chart.getByRole('slider', { name: 'Inspect lap', exact: true });
  await slider.focus(); await slider.press('End');
  await expect(chart.getByRole('tooltip')).toContainText('Pit stop · Oscar Piastri · lap 500');
  await expect(chart.locator('tbody tr').last().locator('.event-cell')).toContainText('Pit stop · Oscar Piastri · lap 500');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const metric of ['lap_time', 'cumulative_lap_delta']) test(`disabled marker presentation leaves ${metric} unchanged`, async ({ page }) => {
  const chart = await mountMarkerRenderer(page);
  await chart.evaluate((node, metric) => {
    node.module = { ...node.module, options: { ...node.module.options, event_markers: metric === 'lap_time' ? ['pit'] : [] } };
    node.model = { ...node.model, metric };
  }, metric);
  await expect(chart.locator('.event-track, .event-status, .event-cell')).toHaveCount(0);
  await expect(chart.getByRole('columnheader', { name: 'Event markers', exact: true })).toHaveCount(0);
  await expect(chart.locator('tbody tr')).toHaveCount(4);
  await expect(chart.locator('.series-line')).toHaveCount(4);
});
