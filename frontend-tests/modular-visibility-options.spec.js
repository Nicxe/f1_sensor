const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function reloadSaved(page) {
  const config = await page.evaluate(() => window.savedConfig);
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), config);
  return config;
}

for (const module of [
  { type: 'timing', fields: ['driver', 'last_lap'] },
  { type: 'tyres', options: { content: 'history', rows: 1 } },
]) {
  test(`${module.type} session details can be hidden in the editor without hiding its data`, async ({ page }) => {
    await page.evaluate(module => window.mountModular({ editor: true, config: { modules: [module] } }), module);
    const editor = page.locator('f1-sensor-card-editor');
    const preview = page.locator('#native-preview');
    const session = preview.locator('.module-context').filter({ hasText: 'Demo Grand Prix' });
    await expect(session).toBeVisible();
    await editor.getByText('Module options', { exact: true }).click();
    const control = editor.getByRole('checkbox', { name: 'Show session and event details', exact: true });
    await expect(control).toBeChecked();
    await control.uncheck();
    await expect(session).toHaveCount(0);
    const data = module.type === 'tyres' ? preview.locator('f1-tyre-history-view .driver-row') : preview.locator('table tbody tr');
    await expect(data.first()).toBeVisible();
    await control.check();
    await expect(session).toBeVisible();
    await control.uncheck();
    const saved = await reloadSaved(page);
    expect(saved.modules[0].options.show_context).toBe(false);
    await expect(page.locator('.module-context').filter({ hasText: 'Demo Grand Prix' })).toHaveCount(0);
    await expect(page.locator(module.type === 'tyres' ? 'f1-tyre-history-view .driver-row' : 'f1-module-view table tbody tr').first()).toBeVisible();
  });
}

test('Timing explanations can be hidden independently of time labels and restored', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const preview = page.locator('#native-preview');
  await expect(preview.locator('.timing-legend')).toBeVisible();
  await editor.getByText('Module options', { exact: true }).click();
  const control = editor.getByRole('checkbox', { name: 'Show explanations', exact: true });
  await expect(control).toBeChecked();
  await control.uncheck();
  await expect(preview.locator('.timing-legend')).toHaveCount(0);
  await expect(preview.locator('tr[data-driver="16"] .provenance').first()).toBeVisible();
  await expect(preview.locator('.module-context').filter({ hasText: 'Demo Grand Prix' })).toBeVisible();
  await control.check();
  await expect(preview.locator('.timing-legend')).toBeVisible();
  await control.uncheck();
  const saved = await reloadSaved(page);
  expect(saved.modules[0].options.show_explanation).toBe(false);
  await expect(page.locator('.timing-legend')).toHaveCount(0);
  await expect(page.locator('f1-module-view table tbody tr').first()).toBeVisible();
});

test('Minisector status legend still honors its existing option as well as explanation visibility', async ({ page }) => {
  for (const options of [{ show_legend: false }, { show_explanation: false }]) {
    await page.evaluate(options => window.mountModular({ config: { modules: [{ type: 'minisectors', options }] } }), options);
    await expect(page.locator('f1-module-view table tbody tr').first()).toBeVisible();
    await expect(page.locator('.timing-legend')).toHaveCount(0);
  }
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'minisectors' }] } }));
  await expect(page.locator('.timing-legend')).toBeVisible();
});

test('Track map can hide its session text, experimental notice and driver dropdown independently', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'map', fields: ['track_map', 'map_drivers', 'map_corners'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const preview = page.locator('#native-preview');
  const map = preview.locator('f1-track-map-view');
  await expect(map.getByRole('img', { name: 'Driver positions on the track' })).toBeVisible();
  await expect(map.locator('.annotation-experimental')).toBeVisible();
  await expect(map.locator('.map-list')).toBeVisible();
  await expect(map.locator('.map-meta strong')).toHaveText('Demo Grand Prix · Race');
  await editor.getByText('Module options', { exact: true }).click();
  const context = editor.getByRole('checkbox', { name: 'Show session and event details', exact: true });
  const notice = editor.getByRole('checkbox', { name: 'Show experimental notice', exact: true });
  const drivers = editor.getByRole('checkbox', { name: 'Show driver positions and status', exact: true });
  await context.uncheck();
  await expect(preview.locator('.module-context').filter({ hasText: 'Demo Grand Prix' })).toHaveCount(0);
  await expect(map.locator('.map-meta strong')).toHaveCount(0);
  await expect(map.getByText('Track: Clear', { exact: true })).toBeVisible();
  await expect(map.getByText('Lap 12 / 53', { exact: true })).toBeVisible();
  await notice.uncheck();
  await expect(map.locator('.annotation-heading')).toHaveCount(0);
  await expect(map.locator('.map-list')).toBeVisible();
  await drivers.uncheck();
  await expect(map.locator('.map-list')).toHaveCount(0);
  await expect(map.locator('.marker')).toHaveCount(5);
  await expect(map.getByRole('img', { name: 'Driver positions on the track' })).toBeVisible();
  await map.screenshot({ path: 'test-results/module-visibility-hidden.png' });
  await drivers.check();
  await expect(map.locator('.map-list')).toBeVisible();
  await notice.check();
  await expect(map.locator('.annotation-experimental')).toBeVisible();
  await drivers.uncheck();
  await notice.uncheck();
  const saved = await reloadSaved(page);
  expect(saved.modules[0].options).toMatchObject({ show_context: false, show_experimental_notice: false, show_driver_list: false });
  await expect(page.locator('f1-track-map-view .map-list')).toHaveCount(0);
  await expect(page.locator('f1-track-map-view .annotation-heading')).toHaveCount(0);
  await expect(page.locator('f1-track-map-view .marker')).toHaveCount(5);
});

test('hiding a list-only map presents a useful content choice instead of an empty map shell', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'map', fields: ['map_drivers'], options: { show_driver_list: false } }] } }));
  const map = page.locator('f1-track-map-view');
  await expect(map.getByText('Choose map content in the editor.', { exact: true })).toBeVisible();
  await expect(map.locator('.map-list')).toHaveCount(0);
  await expect(map.locator('.map-shell')).toHaveCount(0);
});

test('hiding the experimental map text preserves the previous-season baseline warning', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'map', fields: ['track_map', 'map_corners'], options: { show_experimental_notice: false } }] } }));
  const map = page.locator('f1-track-map-view');
  await expect(map.getByRole('img', { name: 'Driver positions on the track' })).toBeVisible();
  await map.evaluate(node => {
    node.model = { ...node.model, annotations: { ...node.model.annotations, previousSeasonBaseline: true } };
  });
  await expect(map.getByText('Some markings use the previous season’s FIA map as a baseline and may differ from this season.', { exact: true })).toBeVisible();
  await expect(map.locator('.annotation-experimental')).toHaveCount(0);
  await expect(map.getByText('Circuit markings may need corrections.', { exact: false })).toHaveCount(0);
  await expect(map.getByRole('img', { name: 'Driver positions on the track' })).toBeVisible();
});

test('Track map explanations hide the baseline note and marking list while preserving map markings', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'map', fields: ['track_map', 'map_corners'], options: { show_experimental_notice: false } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const map = page.locator('#native-preview f1-track-map-view');
  const baseline = 'Some markings use the previous season’s FIA map as a baseline and may differ from this season.';
  const setBaseline = async view => {
    await expect(view.getByRole('img', { name: 'Driver positions on the track' })).toBeVisible();
    await view.evaluate(node => {
      node.model = { ...node.model, annotations: { ...node.model.annotations, previousSeasonBaseline: true,
        corners: [{ id: 'turn_01', label: '1', point: [40, 20], offset: [0, -8] }] } };
    });
  };
  await setBaseline(map);
  await expect(map.getByText(baseline, { exact: true })).toBeVisible();
  await expect(map.locator('.annotation-summary summary')).toContainText('Track markings');
  await expect(map.locator('.annotation-corner-group').first()).toBeVisible();
  const markings = await map.locator('.annotation-corner-group').count();
  await editor.getByText('Module options', { exact: true }).click();
  const control = editor.getByRole('checkbox', { name: 'Show explanations', exact: true });
  await expect(control).toBeChecked();
  await control.uncheck();
  await setBaseline(map);
  await expect(map.getByText(baseline, { exact: true })).toHaveCount(0);
  await expect(map.locator('.annotation-summary')).toHaveCount(0);
  await expect(map.locator('.annotation-corner-group')).toHaveCount(markings);
  await expect(map.locator('#map-description')).not.toContainText('Track markings are listed below');
  await control.check();
  await setBaseline(map);
  await expect(map.getByText(baseline, { exact: true })).toBeVisible();
  await expect(map.locator('.annotation-summary summary')).toBeVisible();
  await control.uncheck();
  const saved = await reloadSaved(page);
  expect(saved.modules[0].options.show_explanation).toBe(false);
  const reloaded = page.locator('f1-track-map-view');
  await setBaseline(reloaded);
  await expect(reloaded.getByText(baseline, { exact: true })).toHaveCount(0);
  await expect(reloaded.locator('.annotation-summary')).toHaveCount(0);
  await expect(reloaded.locator('.annotation-corner-group')).toHaveCount(markings);
});

test('Tyre history lap progress can be hidden and saved independently of its axis and stint bars', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'tyres', options: { content: 'history' } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const history = page.locator('#native-preview f1-tyre-history-view');
  await expect(history.locator('.lap-progress')).toHaveText(/Lap \d+ \/ \d+/);
  await expect(history.locator('.segment').first()).toBeVisible();
  const axis = await history.locator('.axis span').allTextContents();
  const segments = await history.locator('.segment').count();
  expect(axis.length).toBeGreaterThan(1);
  await editor.getByText('Module options', { exact: true }).click();
  const control = editor.getByRole('checkbox', { name: 'Show lap progress', exact: true });
  await expect(control).toBeChecked();
  await control.uncheck();
  await expect(history.locator('.lap-progress')).toHaveCount(0);
  await expect(history.locator('.axis span')).toHaveText(axis);
  await expect(history.locator('.segment')).toHaveCount(segments);
  await expect(history.locator('.cursor').first()).toBeVisible();
  await expect(history.locator('.legend')).toBeVisible();
  await control.check();
  await expect(history.locator('.lap-progress')).toHaveText(/Lap \d+ \/ \d+/);
  await control.uncheck();
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('current');
  await expect(control).toHaveCount(0);
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('statistics');
  await expect(control).toHaveCount(0);
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('history');
  await expect(control).not.toBeChecked();
  await expect(history.locator('.lap-progress')).toHaveCount(0);
  const saved = await reloadSaved(page);
  expect(saved.modules[0].options.show_lap_progress).toBe(false);
  const reloaded = page.locator('f1-tyre-history-view');
  await expect(reloaded.locator('.lap-progress')).toHaveCount(0);
  await expect(reloaded.locator('.axis span')).toHaveText(axis);
  await expect(reloaded.locator('.segment')).toHaveCount(segments);
  await expect(reloaded.locator('.segment').first()).toBeVisible();
});

test('saved Results context preference keeps classification data and status visible', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'results', options: { show_context: false, show_status: true } }] } }));
  await expect(page.locator('f1-module-view table tbody tr').first()).toBeVisible();
  await expect(page.locator('.module-context').filter({ hasText: 'Demo Grand Prix' })).toHaveCount(0);
});

for (const { module, explanation } of [
  { module: { type: 'lap_chart', options: { selected: ['16'] } }, explanation: 'Recorded laps may include pit laps' },
  { module: { type: 'tyres', options: { content: 'statistics' } }, explanation: 'Recorded laps across all drivers and stints.' },
  { module: { type: 'incidents', options: { content: 'track_limits_summary' } }, explanation: 'Only drivers with recorded track-limit data are listed.' },
]) {
  test(`${module.type} static footer explanation follows its visibility choice without hiding the data`, async ({ page }) => {
    await page.evaluate(module => window.mountModular({ config: { modules: [module] } }), module);
    await expect(page.getByText(explanation, { exact: false })).toBeVisible();
    if (module.type === 'lap_chart') await expect(page.getByText('Gaps mean data is missing.', { exact: true })).toBeVisible();
    await page.evaluate(module => window.mountModular({ config: { modules: [{ ...module, options: { ...module.options, show_explanation: false } }] } }), module);
    await expect(page.getByText(explanation, { exact: false })).toHaveCount(0);
    if (module.type === 'lap_chart') {
      await expect(page.getByText('Gaps mean data is missing.', { exact: true })).toHaveCount(0);
      await expect(page.locator('f1-series-chart').getByRole('img')).toBeVisible();
    } else await expect(page.locator('f1-module-view table tbody tr').first()).toBeVisible();
  });
}

test('compound waiting state remains visible when static explanations are hidden', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ scene: 'missing', config: { modules: [{ type: 'tyres', options: { content: 'statistics', show_explanation: false } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    demo.hass.states[demo.preview.entries[0].entities.tyre_statistics] = { state: 'unknown', attributes: { status: 'waiting_for_compound_data', compounds: {} } };
    card.hass = { ...demo.hass };
  });
  await expect(page.getByText('Waiting for compound information', { exact: false })).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(0);
});
