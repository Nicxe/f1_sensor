const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.setViewportSize({ width: 1200, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

const row = (page, driver) => page.locator(`f1-module-view tr[data-driver="${driver}"]`);

async function setTimingOptions(page, options) {
  await page.evaluate(options => {
    const card = window.fixtureCard;
    const config = structuredClone(card.config);
    Object.assign(config.modules[0].options, options);
    card.setConfig(config);
  }, options);
}

test('editor saves the combined GAP / INT primary value without adding an on-card switch', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: {
    modules: [{ type: 'timing', fields: ['position', 'driver', 'interval', 'gap'], options: { show_gap_toggle: true } }],
  } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.locator('summary').filter({ hasText: /^Module options$/ }).click();
  await expect(editor.getByLabel('Primary value in combined GAP / INT', { exact: true })).toHaveCount(0);
  await editor.getByLabel('GAP and INT columns', { exact: true }).selectOption('combined');
  await editor.getByLabel('Primary value in combined GAP / INT', { exact: true }).selectOption('gap');
  await expect(editor.getByRole('checkbox', { name: 'Show live gap toggle', exact: true })).toHaveCount(0);
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].options.gap_display).toBe('combined');
  expect(saved.modules[0].options.gap_primary).toBe('gap');
  expect(saved.modules[0].options.show_gap_toggle).toBe(true);
  expect(saved.modules[0].fields).toEqual(['position', 'driver', 'interval', 'gap']);

  await page.evaluate(config => window.mountModular({ config }), saved);
  const combined = row(page, '63').locator('[data-field="timing_gap"]');
  await expect(combined.locator('[data-gap="gap"]')).toContainText('+2.490');
  await expect(combined.locator('[data-gap="interval"]')).toContainText('+1.245');
  expect(await combined.locator('[data-gap]').evaluateAll(nodes => nodes.map(node => node.dataset.gap))).toEqual(['gap', 'interval']);
  await expect(page.getByRole('group', { name: 'Gap mode', exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Primary value in combined GAP / INT', { exact: true })).toHaveCount(0);

  await setTimingOptions(page, { gap_primary: 'interval' });
  await expect(combined.locator('[data-gap]').first()).toHaveAttribute('data-gap', 'interval');
  expect(await combined.locator('[data-gap]').evaluateAll(nodes => nodes.map(node => node.dataset.gap))).toEqual(['interval', 'gap']);
  await expect(combined.locator('[data-gap="gap"]')).toContainText('+2.490');
});

test('minimal timing uses colored text while preserving deleted and previous-lap meanings in both themes', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { appearance: { logos: false }, modules: [{
      type: 'timing', fields: ['driver', 'last_lap', 'sector_1', 'sector_2'], options: { presentation: 'minimal', show_time_context: false },
    }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const drivers = demo.hass.states[entry.entities.driver_positions].attributes.drivers;
    drivers[0].sectors.current.sector_2.deleted = true;
    drivers[0].sectors.current.sector_2.personal_fastest = true;
    drivers[1].best_lap_time = 79;
    drivers[1].best_lap_lap = 11;
    window.fixtureCard.hass = { ...demo.hass };
  });
  const overall = row(page, '16').locator('[data-field="sector_1"] .signal');
  const deleted = row(page, '16').locator('[data-field="sector_2"] .signal');
  const previous = row(page, '4').locator('[data-field="last_lap"] .signal');
  await expect(overall).toContainText('◆');
  await expect(deleted).toHaveClass(/deleted/);
  await expect(deleted).toContainText('Deleted time');
  await expect(deleted.locator('.time')).toHaveCSS('text-decoration-line', 'line-through');
  await expect(previous).toHaveClass(/previous/);
  await expect(previous).toContainText('Previous lap');
  for (const [mode, color] of [['dark', 'rgb(197, 154, 255)'], ['light', 'rgb(115, 53, 166)']]) {
    await page.evaluate(mode => {
      const card = window.fixtureCard;
      card.setConfig({ ...card.config, appearance: { ...card.config.appearance, mode } });
    }, mode);
    await expect(overall).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await expect(overall).toHaveCSS('color', color);
    await expect(deleted).toHaveClass(/deleted/);
    await expect(previous).toHaveClass(/previous/);
  }
});

test('narrow summary keeps selected fields reachable even when ordinary driver details are disabled', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: {
    appearance: { logos: false, density: 'compact' },
    modules: [{ type: 'timing', fields: ['position', 'driver', 'interval', 'gap', 'last_lap', 'best_lap', 'sector_1', 'tyre'], options: {
      presentation: 'minimal', narrow_layout: true, gap_display: 'separate', gap_primary: 'interval', show_gap_toggle: true, show_driver_details: false,
    } }],
  } }));
  const driver = row(page, '16');
  await expect(driver.locator('td')).toHaveCount(4);
  expect(await driver.locator('td').evaluateAll(nodes => nodes.map(node => node.dataset.field))).toEqual(['position', 'driver', 'timing_gap', 'tyre']);
  await expect(driver.locator('[data-field="last_lap"]')).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Gap mode', exact: true })).toHaveCount(0);
  await driver.getByRole('button', { name: /LEC/ }).click();
  const details = page.locator('[part~="driver-detail"]');
  await expect(details).toBeVisible();
  await expect(details.locator('dt')).toContainText(['Last lap', 'Best lap', 'S1']);
  await expect(details).toContainText('1:20.873');
  await expect(details).toContainText('24.321');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].options.show_driver_details)).toBe(false);
  const accessibility = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(accessibility.violations.filter(item => ['critical', 'serious'].includes(item.impact))).toEqual([]);
});

test('only confirmed retired drivers are dimmed; pit-out and stopped rows keep their status', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'timing', fields: ['position', 'driver', 'status'], options: {
      presentation: 'minimal', driver_badges: true, dim_retired: true,
    } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const drivers = demo.hass.states[entry.entities.driver_positions].attributes.drivers;
    Object.assign(drivers[0], { retired: true, status: 'retired' });
    Object.assign(drivers[1], { stopped: true, status: 'stopped' });
    Object.assign(drivers[2], { pit_out: true, status: 'pit_out' });
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(row(page, '16')).toHaveAttribute('data-retired', 'true');
  await expect(row(page, '4')).toHaveAttribute('data-retired', 'false');
  await expect(row(page, '63')).toHaveAttribute('data-retired', 'false');
  await expect(row(page, '16').getByText('RET', { exact: true })).toBeVisible();
  await expect(row(page, '4').getByText('STOP', { exact: true })).toBeVisible();
  await expect(row(page, '63').getByText('PIT OUT', { exact: true })).toBeVisible();
  await setTimingOptions(page, { dim_retired: false });
  await expect(row(page, '16')).toHaveAttribute('data-retired', 'false');
});

test('qualifying focus shows the selected part and its matching gap without discarding saved columns', async ({ page }) => {
  const fields = ['position', 'driver', 'q1_time', 'q2_time', 'q3_time', 'qualifying_gap', 'sector_1'];
  await page.evaluate(fields => window.mountModular({ scene: 'qualifying', config: { modules: [{
    type: 'timing', fields, options: { presentation: 'minimal', qualifying_focus: 'current' },
  }] } }), fields);
  await expect(page.getByRole('columnheader', { name: 'Q2 best', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Q1 best', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Q3 best', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Q2 gap', exact: true })).toBeVisible();
  await expect(row(page, '4').locator('[data-field="qualifying_gap"]')).toContainText('+0.250');
  await setTimingOptions(page, { qualifying_focus: 'q1' });
  await expect(page.getByRole('columnheader', { name: 'Q1 best', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Q2 best', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Q1 gap', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Q2 gap', exact: true })).toHaveCount(0);
  await expect(row(page, '4').locator('[data-field="qualifying_gap"]')).toContainText('+0.200');
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].fields)).toEqual(fields);
  await setTimingOptions(page, { qualifying_focus: 'all' });
  for (const part of ['Q1', 'Q2', 'Q3']) await expect(page.getByRole('columnheader', { name: `${part} best`, exact: true })).toBeVisible();
});

test('driver badges distinguish pending seconds, unknown service and served penalties', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'timing', fields: ['position', 'driver'], options: { presentation: 'minimal', driver_badges: true } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.investigations].attributes = {
      session_key: 'demo-session', noted: [], under_investigation: [],
      penalties: [
        { driver: 'LEC', racing_number: '16', penalty: '5 SECOND TIME PENALTY', reason: 'Causing a collision', utc: '2026-09-13T13:20:00Z', lap: 12, service_status: 'pending' },
        { driver: 'NOR', racing_number: '4', penalty: '10 SECOND TIME PENALTY', reason: 'Leaving the track', utc: '2026-09-13T13:21:00Z', lap: 12, service_status: 'unknown' },
        { driver: 'RUS', racing_number: '63', penalty: '5 SECOND TIME PENALTY', reason: 'Speeding in the pit lane', utc: '2026-09-13T13:22:00Z', lap: 12, service_status: 'served' },
      ],
    };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(row(page, '16').getByText('+5s', { exact: true })).toBeVisible();
  await expect(row(page, '4').getByText('PEN', { exact: true })).toBeVisible();
  await expect(row(page, '4').getByText('+10s', { exact: true })).toHaveCount(0);
  await expect(row(page, '63').getByText('+5s', { exact: true })).toHaveCount(0);
  await expect(row(page, '63').getByText('PEN', { exact: true })).toHaveCount(0);
  await row(page, '4').getByRole('button', { name: /NOR/ }).click();
  const details = page.locator('[part~="driver-detail"]');
  await expect(details).toContainText('Penalty reported; service status is unconfirmed');
  await expect(details).toContainText('Leaving the track');
});

test('position arrows use only the matching confirmed grid and become unknown for a provisional grid', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'timing', fields: ['position', 'driver'], options: { presentation: 'minimal', position_change: 'grid' } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.starting_grid].attributes = {
      status: 'confirmed', session_key: 'demo-session', grid_context: 'race', meeting_key: 'demo-meeting',
      grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }],
    };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(row(page, '16').locator('[data-field="position_with_change"]')).toContainText(/▲\s*4/);
  await expect(row(page, '4').locator('[data-field="position_with_change"]')).toContainText(/▼\s*1/);
  await page.evaluate(() => {
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.starting_grid].attributes.status = 'provisional';
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(row(page, '16').locator('[data-field="position_with_change"]')).not.toContainText(/▲\s*4/);
  await expect(row(page, '4').locator('[data-field="position_with_change"]')).not.toContainText(/▼\s*1/);
});

test('dimmed retired rows preserve the current timing badges foreground and background contrast', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'timing', fields: ['driver', 'sector_1', 'sector_2'], options: { presentation: 'current', dim_retired: false } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    Object.assign(demo.hass.states[entry.entities.driver_positions].attributes.drivers[0], { retired: true, status: 'retired' });
    window.fixtureCard.hass = { ...demo.hass };
  });
  const driver = row(page, '16'), badges = driver.locator('.signal');
  await expect(badges).toHaveCount(2);
  for (const mode of ['dark', 'light']) {
    await page.evaluate(mode => {
      const card = window.fixtureCard;
      const config = structuredClone(card.config);
      config.appearance.mode = mode;
      config.modules[0].options.dim_retired = false;
      card.setConfig(config);
    }, mode);
    await expect(driver).toHaveAttribute('data-retired', 'false');
    const normal = await badges.evaluateAll(nodes => nodes.map(node => {
      const style = getComputedStyle(node);
      return { color: style.color, background: style.backgroundColor };
    }));
    await setTimingOptions(page, { dim_retired: true });
    await expect(driver).toHaveAttribute('data-retired', 'true');
    const dimmed = await badges.evaluateAll(nodes => nodes.map(node => {
      const style = getComputedStyle(node);
      return { color: style.color, background: style.backgroundColor };
    }));
    expect(dimmed, `${mode} timing badges keep their readable ink when the row is retired`).toEqual(normal);
  }
});
