const { test, expect } = require('@playwright/test');

// Compact desktop rows are distinct from the existing coarse-pointer hit area.
test.use({ hasTouch: false });

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.setViewportSize({ width: 1200, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

const timing = (page, id = 'compact') => page.locator(`f1-module-view[data-module-id="${id}"]`);
const row = (page, id = 'compact') => timing(page, id).locator('tr[data-driver="16"]');
const plainFields = ['position', 'driver', 'sector_1', 'sector_2', 'sector_3', 'tyre'];
const combinedFields = ['position', 'driver', 'sector_1_with_minisectors', 'sector_2', 'sector_3_with_minisectors', 'tyre'];
const options = { profile: 'custom', presentation: 'minimal', show_time_context: false, show_time_status_icon: true, tyre_age_inline: true };

async function mount(page, mode, fields = plainFields, modules) {
  await page.evaluate(({ mode, fields, modules, options }) => window.mountModular({ config: {
    appearance: { mode, style: 'minimal', font: 'system', density: 'compact', logos: false },
    modules: modules ?? [{ id: 'compact', type: 'timing', fields, options }],
  } }), { mode, fields, modules, options });
  await expect(row(page)).toBeVisible();
}

async function replaceFields(page, fields) {
  await page.evaluate(fields => {
    const card = window.fixtureCard, config = structuredClone(card.config);
    config.modules[0].fields = fields;
    card.setConfig(config);
  }, fields);
}

for (const mode of ['dark', 'light']) {
  test(`inline tyre symbols keep one vertical column for one-digit, two-digit and unknown ages in ${mode} mode`, async ({ page }) => {
    await mount(page, mode, ['position', 'driver', 'tyre']);
    await page.evaluate(() => {
      const demo = window.fixtureDemo, entry = demo.preview.entries[0];
      const people = demo.hass.states[entry.entities.driver_list].attributes.drivers;
      const drivers = demo.hass.states[entry.entities.driver_positions].attributes.drivers;
      const tyres = demo.hass.states[entry.entities.current_tyres].attributes.drivers;
      for (const [number, code] of [['10', 'D10'], ['11', 'D11'], ['12', 'D12']]) {
        people.push({ ...people[0], racing_number: number, tla: code, full_name: `Demo driver ${number}` });
        drivers.push({ ...structuredClone(drivers[0]), racing_number: number, tla: code, current_position: drivers.length + 1 });
        tyres.push({ ...structuredClone(tyres[0]), racing_number: number });
      }
      [7, 15, 9, 17, 13, 10, null, 100].forEach((age, index) => {
        tyres[index].stint_laps = age;
      });
      window.fixtureCard.hass = { ...demo.hass };
    });
    const cells = timing(page).locator('tr[data-driver] [data-field="tyre"]');
    await expect(cells).toHaveCount(8);
    await expect(cells.nth(6)).toContainText('—');
    await expect(cells.nth(6).locator('.compound')).toContainText('S');
    const symbols = await cells.locator('.compound').evaluateAll(nodes => nodes.map(node => ({ x: node.getBoundingClientRect().x, width: node.getBoundingClientRect().width })));
    const spread = Math.max(...symbols.map(value => value.x)) - Math.min(...symbols.map(value => value.x));
    expect(spread, `tyre symbol X positions ${symbols.map(value => value.x).join(', ')}`).toBeLessThanOrEqual(.5);
    expect(new Set(symbols.map(value => value.width)).size).toBe(1);
  });

  test(`minimal combined sectors keep tiny status blocks below aligned times without tall rows in ${mode} mode`, async ({ page }) => {
    await mount(page, mode);
    const baseline = await row(page).evaluate(node => node.getBoundingClientRect().height);
    await replaceFields(page, combinedFields);
    const sectorHeader = timing(page).getByRole('columnheader', { name: 'S1 with minisectors', exact: true });
    await expect(sectorHeader.locator('[aria-hidden="true"]')).toHaveText('S1');
    const combined = row(page).locator('[data-field="sector_1_with_minisectors"]');
    await expect(combined.locator('.minisector-block')).toHaveCount(6);
    const geometry = await row(page).evaluate(node => {
      const rect = element => {
        const { x, y, width, height, bottom } = element.getBoundingClientRect();
        return { x, y, width, height, bottom };
      };
      const cell = node.querySelector('[data-field="sector_1_with_minisectors"]');
      return {
        rowHeight: node.getBoundingClientRect().height,
        times: [...node.querySelectorAll('td .time')].map(rect),
        strip: rect(cell.querySelector('.minisector-strip')),
        time: rect(cell.querySelector('.time')),
        blocks: [...cell.querySelectorAll('.minisector-block')].map(rect),
      };
    });
    expect.soft(Math.max(...geometry.blocks.map(block => block.width)), 'minimal minisector marks should be at most 8px wide').toBeLessThanOrEqual(8);
    expect.soft(Math.max(...geometry.blocks.map(block => block.height)), 'minimal minisector marks should be at most 8px high').toBeLessThanOrEqual(8);
    expect.soft(geometry.strip.y, 'minisectors should sit beneath their time').toBeGreaterThanOrEqual(geometry.time.bottom);
    const topSpread = Math.max(...geometry.times.map(time => time.y)) - Math.min(...geometry.times.map(time => time.y));
    expect.soft(topSpread, `time tops ${geometry.times.map(time => time.y).join(', ')}`).toBeLessThanOrEqual(1);
    expect.soft(geometry.rowHeight, `combined row should fit the compact ${baseline}px baseline plus at most 4px`).toBeLessThanOrEqual(baseline + 4);
  });
}

test('minimal minisectors preserve regular status order and accessible labels while the regular presentation keeps its large marks', async ({ page }) => {
  await mount(page, 'dark', plainFields, [
    { id: 'compact', type: 'timing', fields: combinedFields, options },
    { id: 'regular', type: 'timing', fields: combinedFields, options: { ...options, presentation: 'current' } },
  ]);
  await page.evaluate(() => {
    const demo = window.fixtureDemo;
    demo.preview.minisectors.drivers['16'].sectors['0'].segments = { 0: 2051, 1: 2049, 2: 2048, 3: 0, 4: 2064, 5: 9999 };
    window.fixtureCard.hass = { ...demo.hass };
  });
  const compact = row(page).locator('[data-field="sector_1_with_minisectors"] .minisector-block');
  const regular = row(page, 'regular').locator('[data-field="sector_1_with_minisectors"] .minisector-block');
  await expect(compact).toHaveCount(6);
  await expect(regular).toHaveCount(6);
  await expect(compact.nth(5)).toHaveAttribute('data-status', 'unknown');
  const statuses = locator => locator.evaluateAll(nodes => nodes.map(node => ({ status: node.dataset.status, label: node.getAttribute('aria-label'), role: node.getAttribute('role') })));
  const compactStatuses = await statuses(compact);
  expect(compactStatuses).toEqual(await statuses(regular));
  expect(compactStatuses.map(value => value.status)).toEqual(['overall', 'personal', 'recorded', 'unset', 'special', 'unknown']);
  expect(compactStatuses.every(value => value.label && value.role === 'listitem')).toBe(true);
  expect(compactStatuses[5].label).toContain('9999');
  const sizes = await regular.evaluateAll(nodes => nodes.map(node => ({ width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height, radius: getComputedStyle(node).borderRadius })));
  expect(sizes).toEqual(Array(6).fill({ width: 11, height: 20, radius: '4px' }));
});

test('editor switches between plain and combined sector fields and plain mode leaves no minisector strip or extra height', async ({ page }) => {
  await mount(page, 'light');
  const baseline = await row(page).evaluate(node => node.getBoundingClientRect().height);
  const initial = await page.evaluate(() => structuredClone(window.fixtureCard.config));
  await page.evaluate(config => window.mountModular({ editor: true, nativePreview: false, config }), initial);
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByRole('checkbox', { name: 'S1', exact: true }).uncheck();
  await editor.getByRole('checkbox', { name: 'S1 with minisectors', exact: true }).check();
  const combined = await page.evaluate(() => structuredClone(window.savedConfig));
  expect(combined.modules[0].fields).toContain('sector_1_with_minisectors');
  expect(combined.modules[0].fields).not.toContain('sector_1');
  expect(combined.modules[0].options).toEqual(initial.modules[0].options);
  await page.evaluate(config => window.mountModular({ config }), combined);
  await expect(row(page).locator('[data-field="sector_1_with_minisectors"] .minisector-block')).toHaveCount(6);

  await page.evaluate(config => window.mountModular({ editor: true, nativePreview: false, config }), combined);
  await editor.getByRole('checkbox', { name: 'S1 with minisectors', exact: true }).uncheck();
  await editor.getByRole('checkbox', { name: 'S1', exact: true }).check();
  const plain = await page.evaluate(() => structuredClone(window.savedConfig));
  expect(plain.modules[0].fields).toContain('sector_1');
  expect(plain.modules[0].fields).not.toContain('sector_1_with_minisectors');
  await page.evaluate(config => window.mountModular({ config }), plain);
  await expect(row(page).locator('[data-field="sector_1"] .time')).toHaveText('24.321');
  await expect(timing(page).locator('tbody .minisector-strip')).toHaveCount(0);
  expect(await row(page).evaluate(node => node.getBoundingClientRect().height)).toBeCloseTo(baseline, 1);
});
