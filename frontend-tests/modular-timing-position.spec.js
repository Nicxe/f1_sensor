const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.setViewportSize({ width: 1200, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

const row = (page, driver) => page.locator(`f1-module-view tr[data-driver="${driver}"]`);
const section = (editor, title) => editor.locator('summary').filter({ hasText: new RegExp(`^${title}$`) }).locator('..');

test('the editor swaps plain and combined position fields in place for table and driver details', async ({ page }) => {
  const fields = ['driver', 'position', 'last_lap'];
  const detail_fields = ['tyre_age', 'position', 'best_lap'];
  await page.evaluate(({ fields, detail_fields }) => window.mountModular({ editor: true, nativePreview: false, config: {
    modules: [{ type: 'timing', fields, detail_fields, options: { profile: 'custom', detail_laps: 3 } }],
  } }), { fields, detail_fields });
  const editor = page.locator('f1-sensor-card-editor');
  const content = section(editor, 'Content and columns');
  await expect(content.getByRole('checkbox', { name: 'Position', exact: true })).toBeChecked();
  await content.getByRole('checkbox', { name: 'Position + change', exact: true }).check();
  await expect(content.getByRole('checkbox', { name: 'Position', exact: true })).not.toBeChecked();
  let saved = await page.evaluate(() => structuredClone(window.savedConfig));
  expect(saved.modules[0].fields).toEqual(['driver', 'position_with_change', 'last_lap']);
  expect(saved.modules[0].detail_fields).toEqual(detail_fields);
  expect(saved.modules[0].options.position_change).toBe('off');

  await editor.locator('summary').filter({ hasText: /^Driver details$/ }).click();
  const details = section(editor, 'Driver details');
  await details.getByRole('checkbox', { name: 'Position + change', exact: true }).check();
  saved = await page.evaluate(() => structuredClone(window.savedConfig));
  expect(saved.modules[0].detail_fields).toEqual(['tyre_age', 'position_with_change', 'best_lap']);
  expect(saved.modules[0].fields).toEqual(['driver', 'position_with_change', 'last_lap']);
  expect(saved.modules[0].options.detail_laps).toBe(3);
  await expect(details.getByRole('checkbox', { name: 'Position', exact: true }), JSON.stringify(saved.modules[0].detail_fields)).not.toBeChecked();

  await content.getByRole('checkbox', { name: 'Position', exact: true }).check();
  await expect(content.getByRole('checkbox', { name: 'Position + change', exact: true })).not.toBeChecked();
  saved = await page.evaluate(() => structuredClone(window.savedConfig));
  expect(saved.modules[0].fields).toEqual(fields);
  expect(saved.modules[0].detail_fields).toEqual(['tyre_age', 'position_with_change', 'best_lap']);
  await editor.locator('summary').filter({ hasText: /^Module options$/ }).click();
  await expect(section(editor, 'Module options').getByLabel('Position change', { exact: true })).toHaveCount(0);
});

for (const presentation of ['current', 'compact']) {
  for (const mode of ['dark', 'light']) {
    test(`plain and combined position columns remain distinct in ${presentation} ${mode}`, async ({ page }) => {
      await page.evaluate(({ presentation, mode }) => {
        window.mountModular({ config: { appearance: { presentation, mode }, modules: [{ type: 'timing',
          fields: ['position', 'driver', 'position_with_change', 'last_lap'], options: { profile: 'custom' } }] } });
        const demo = window.fixtureDemo, entry = demo.preview.entries[0];
        demo.hass.states[entry.entities.starting_grid].attributes = {
          status: 'confirmed', session_key: 'demo-session', meeting_key: 'demo-meeting', grid_context: 'race',
          grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }, { racing_number: '63', grid_position: 3 }],
        };
        window.fixtureCard.hass = { ...demo.hass };
      }, { presentation, mode });
      await expect(row(page, '16').locator('[data-field="position"]')).toHaveText('1');
      await expect(row(page, '4').locator('[data-field="position"]')).toHaveText('2');
      const gained = row(page, '16').locator('[data-field="position_with_change"]');
      const lost = row(page, '4').locator('[data-field="position_with_change"]');
      await expect(gained.locator('.position-change')).toContainText(/▲\s*4/);
      await expect(gained).toContainText(/places gained/i);
      await expect(lost.locator('.position-change')).toContainText(/▼\s*1/);
      await expect(lost).toContainText(/places lost/i);
      const equal = row(page, '63').locator('[data-field="position_with_change"]');
      await expect(equal.locator('.position-change')).toHaveClass(/equal/);
      await expect(equal.locator('.position-change [aria-hidden="true"]')).toHaveText('—');
      await expect(equal.locator('.position-change .sr')).toContainText(/0.*unchanged/i);
      await expect(equal.locator('.position-change')).toHaveAttribute('title', /0.*unchanged/i);
      for (const cell of [gained, lost, equal]) {
        const sizes = await cell.locator('.timing-position').evaluate(node => ({
          position: getComputedStyle(node.firstElementChild).fontSize,
          change: getComputedStyle(node.querySelector('.position-change [aria-hidden="true"]')).fontSize,
        }));
        expect(sizes.change, `position/change sizes: ${JSON.stringify(sizes)}`).toBe(sizes.position);
      }
      await page.evaluate(() => {
        const demo = window.fixtureDemo, entry = demo.preview.entries[0];
        demo.hass.states[entry.entities.starting_grid].attributes.status = 'provisional';
        window.fixtureCard.hass = { ...demo.hass };
      });
      await expect(gained.locator('.position-change')).toHaveClass(/unknown/);
      await expect(gained.locator('.position-change [aria-hidden="true"]')).toHaveText('—');
      await expect(gained.locator('.position-change .sr')).toContainText(/unavailable/i);
      await expect(gained.locator('.position-change')).toHaveAttribute('title', /unavailable/i);
      await expect(gained).not.toContainText('▲');
      await expect(row(page, '16').locator('[data-field="position"]')).toHaveText('1');
    });
  }
}

test('narrow timing keeps the selected combined column and does not inject a position when none is selected', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => {
    window.mountModular({ config: { appearance: { presentation: 'compact' }, modules: [{ type: 'timing',
      fields: ['driver', 'position_with_change', 'last_lap', 'gap'], detail_fields: [],
      options: { profile: 'custom', narrow_layout: true } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.starting_grid].attributes = {
      status: 'confirmed', session_key: 'demo-session', meeting_key: 'demo-meeting', grid_context: 'race',
      grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }],
    };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(row(page, '16').locator('[data-field="position_with_change"] .position-change')).toContainText(/▲\s*4/);
  await expect(row(page, '16').locator('[data-field="position"]')).toHaveCount(0);
  await row(page, '16').getByRole('button', { name: /LEC/ }).click();
  await expect(page.locator('[part~="driver-detail"]')).toContainText('Last lap');
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].fields)).toEqual(['driver', 'position_with_change', 'last_lap', 'gap']);
  await page.evaluate(() => {
    const card = window.fixtureCard, value = structuredClone(card.config);
    value.modules[0].fields = ['driver', 'last_lap', 'gap'];
    card.setConfig(value);
  });
  await expect(row(page, '16').locator('[data-field="position"], [data-field="position_with_change"]')).toHaveCount(0);
  await expect(row(page, '16').locator('.position-change')).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].fields)).toEqual(['driver', 'last_lap', 'gap']);
});

test('combined position works as a driver-detail field while the table position remains plain', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'timing', fields: ['position', 'driver', 'last_lap'],
      detail_fields: ['position_with_change'], options: { profile: 'custom', detail_laps: 0 } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.starting_grid].attributes = {
      status: 'confirmed', session_key: 'demo-session', meeting_key: 'demo-meeting', grid_context: 'race',
      grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }],
    };
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(row(page, '16').locator('[data-field="position"]')).toHaveText('1');
  await row(page, '16').getByRole('button', { name: /LEC/ }).click();
  const details = page.locator('[part~="driver-detail"]');
  await expect(details.getByText('Position + change', { exact: true })).toBeVisible();
  await expect(details.locator('.position-change')).toContainText(/▲\s*4/);
  await expect(row(page, '16').locator('[data-field="position"]')).toHaveText('1');
});

test('automatic session profiles keep the combined position choice without changing qualifying columns', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ scene: 'qualifying', config: { modules: [{ type: 'timing',
    fields: ['position_with_change', 'driver'], options: { profile: 'auto' } }] } }));
  await expect(page.getByRole('columnheader', { name: 'Q1 best', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Q2 best', exact: true })).toBeVisible();
  await expect(row(page, '16').locator('[data-field="position"]')).toHaveCount(0);
  await expect(row(page, '16').locator('[data-field="position_with_change"] .position-change')).toHaveClass(/unknown/);
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].options.profile)).toBe('auto');
});

test('a saved position-change choice renders the replay GridPos reference and clears it after a seek generation', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ scene: 'replay', config: { modules: [{ type: 'timing', fields: ['position', 'driver'],
      options: { profile: 'custom', position_change: 'grid' } }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0], card = window.fixtureCard;
    const current = structuredClone(demo.hass.states[entry.entities.current_session]);
    current.state = 'Race';
    const positions = structuredClone(demo.hass.states[entry.entities.driver_positions]);
    Object.assign(positions.attributes.drivers.find(driver => String(driver.racing_number) === '16'), { current_position: 2, grid_position: 20 });
    positions.attributes.drivers.find(driver => String(driver.racing_number) === '4').current_position = 1;
    positions.attributes.starting_grid_reference = { source: 'TimingAppData.GridPos', session_key: current.attributes.session_key,
      grid: [{ racing_number: '16', grid_position: 5 }, { racing_number: '4', grid_position: 1 }] };
    const context = { session_id: 'replay-recording:demo-session', replay_generation: 2, delay_seconds: 0, qualifying_part: null };
    const resources = {
      session_context: { state: 'active', attributes: { no_spoiler: false } },
      current_session: current, driver_positions: positions,
    };
    entry.data_api = { enabled: Object.keys(resources) };
    for (const [key, payload] of Object.entries(resources)) card.cardDataResources.set(key, { key, entryId: entry.entry_id,
      state: { status: 'ready', data: { source: 'replay', generation: 'replay-generation-2', context: { ...context }, status: 'ready', payload } } });
    demo.hass.states[entry.entities.starting_grid].attributes = { status: 'confirmed', session_key: 'independent-live-race',
      grid_context: 'race', grid: [{ racing_number: '16', grid_position: 10 }] };
    card.hass = { ...demo.hass };
  });
  const combined = row(page, '16').locator('[data-field="position_with_change"]');
  await expect(combined.locator('.position-change')).toContainText(/▲\s*3/);
  await expect(row(page, '16').locator('[data-field="position"]')).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].options.position_change)).toBe('off');
  await page.evaluate(() => {
    const card = window.fixtureCard;
    for (const resource of card.cardDataResources.values()) {
      resource.state.data.generation = 'replay-generation-3';
      resource.state.data.context.replay_generation = 3;
    }
    delete card.cardDataResources.get('driver_positions').state.data.payload.attributes.starting_grid_reference;
    card.hass = { ...card.hass };
  });
  await expect(combined.locator('.position-change')).toHaveClass(/unknown/);
  await expect(combined).not.toContainText('▲');
});
