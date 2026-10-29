const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, mode = 'first', options = {}) {
  await page.evaluate(({ mode, options }) => {
    window.mountModular({ scene: 'qualifying', config: { modules: [{ id: 'timing', type: 'timing', fields: ['position', 'driver', 'sector_1'], options: { push_laps: mode, ...options } }] } });
    window.setPushFixture = (status = 'available', change = {}) => {
      const card = window.fixtureCard, entity = window.fixtureDemo.preview.entries[0].entities.driver_positions;
      const source = card.hass.states[entity];
      card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { ...source, attributes: { ...source.attributes,
        push_laps_status: status,
        drivers: source.attributes.drivers.map(driver => ({ ...driver, push_lap: {
          state: driver.racing_number === '63' ? 'push' : driver.racing_number === '4' ? 'probable_push' : 'cooldown',
          active: ['63', '4'].includes(driver.racing_number), progress: driver.racing_number === '63' ? .85 : .4,
          lap: 13, ...(change[driver.racing_number] ?? {}),
        } })),
      } } } };
    };
    window.setPushFixture();
  }, { mode, options });
}

test('push rows rise above the cap in track order and keep opened driver details during updates', async ({ page }) => {
  await mount(page, 'first', { rows: 2 });
  const module = page.locator('f1-module-view');
  await expect(module.locator('tr[data-driver]')).toHaveCount(2);
  expect(await module.locator('tr[data-driver]').evaluateAll(rows => rows.map(row => row.dataset.driver))).toEqual(['63', '4']);
  await expect(module.locator('tr[data-driver="63"] td').first()).toHaveText('3');
  await expect(module.locator('tr[data-driver="63"] .push-label')).toHaveText('Push');
  await expect(module.locator('tr[data-driver="4"] .push-label')).toHaveText('Possible push');
  await expect(module.getByText('Nearest the finish line first', { exact: true })).toBeVisible();
  const driver = module.locator('tr[data-driver="63"] button.driver');
  await driver.click();
  await driver.focus();
  await page.evaluate(() => window.setPushFixture('available', { '4': { progress: .95 } }));
  expect(await module.locator('tr[data-driver]').evaluateAll(rows => rows.map(row => row.dataset.driver))).toEqual(['4', '63']);
  await expect(driver).toBeFocused();
  await expect(driver).toHaveAttribute('aria-expanded', 'true');
  await expect(module.locator('#driver-detail-63')).toBeVisible();
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(a11y.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
});

test('only mode distinguishes empty, waiting and unavailable data and briefly shows completed times', async ({ page }) => {
  await mount(page, 'only');
  const module = page.locator('f1-module-view');
  for (const [status, text] of [['waiting', 'Waiting for enough timing data to identify push laps'], ['unavailable', 'Push-lap timing is unavailable'], ['unsupported', 'Push laps are available during practice and qualifying']]) {
    await page.evaluate(status => window.setPushFixture(status), status);
    await expect(module.getByText(text, { exact: true })).toBeVisible();
    await expect(module.locator('tr[data-driver]')).toHaveCount(0);
  }
  await page.evaluate(() => window.setPushFixture('available', { '4': { active: false }, '63': { state: 'completed', active: false, completed_at: '2026-10-24T12:00:00Z', last_lap_time: 95.73 } }));
  await expect(module.locator('tr[data-driver]')).toHaveCount(1);
  await expect(module.locator('.push-label')).toHaveText('Lap complete · 1:35.730');
  await expect(module.getByText('Completed attempts', { exact: true })).toBeVisible();
  await page.evaluate(() => window.setPushFixture('available', { '4': { active: false }, '63': { active: false } }));
  await expect(module.getByText('No push laps identified', { exact: true })).toBeVisible();
});

test('editor saves push modes per Timing module and labels remain available on narrow displays', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: { modules: [{ id: 'timing', type: 'timing' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const options = editor.getByRole('region', { name: 'Selected module', exact: true }).locator('details').filter({ has: page.locator('summary').filter({ hasText: /^Module options$/ }) });
  await options.locator('summary').click();
  const picker = editor.getByLabel('Push laps', { exact: true });
  await expect(picker).toHaveValue('off');
  await picker.selectOption('only');
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.push_laps)).toBe('only');
  await editor.getByRole('button', { name: 'Duplicate module', exact: true }).click();
  expect(await page.evaluate(() => window.savedConfig.modules.map(module => module.options.push_laps))).toEqual(['only', 'only']);
  await page.setViewportSize({ width: 360, height: 900 });
  await mount(page, 'only');
  await expect(page.locator('.push-label').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('a backwards replay seek clears future cached times from the highlighted current attempt', async ({ page }) => {
  await mount(page, 'only');
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, modules: card.config.modules.map(module => ({ ...module, fields: ['driver', 'sector_1', 'sector_2', 'sector_3'] })) });
    const key = card.buildModels().get('timing').context.key;
    card.sectors.select(key, { racing_number: '63', sector_current_lap: 4, sectors: { current: {
      sector_1: { time: 41.486, lap: 4, source: 'current' },
      sector_2: { time: 48.138, lap: 4, source: 'current' },
      sector_3: { time: 48.47, lap: 4, source: 'current' },
    } } });
    window.setEarlierPush = (progress, time = null) => {
      const entity = window.fixtureDemo.preview.entries[0].entities.driver_positions;
      const source = card.hass.states[entity];
      card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { ...source, attributes: { ...source.attributes,
        drivers: source.attributes.drivers.map(driver => driver.racing_number === '63' ? { ...driver,
          sector_current_lap: time === null ? null : 3,
          sectors: { state: time === null ? 'awaiting_s1' : 's1_done', current: {
            sector_1: { time, lap: time === null ? null : 3, source: time === null ? null : 'current' },
            sector_2: { time: null, lap: null, source: null },
            sector_3: { time: null, lap: null, source: null },
          } },
          push_lap: { ...driver.push_lap, state: 'probable_push', active: true, lap: 2, progress },
        } : { ...driver, push_lap: { state: 'cooldown', active: false, progress: null } }),
      } } } };
    };
    window.setEarlierPush(.125);
  });
  const row = page.locator('tr[data-driver="63"]');
  await expect(row.locator('.push-label')).toHaveText('Possible push');
  await expect(row.locator('.time')).toHaveText(['—', '—', '—']);
  await expect(row).not.toContainText('41.486');
  await expect(row).not.toContainText('48.138');
  await page.evaluate(() => window.setEarlierPush(.4, 25.54));
  await expect(row.locator('.time')).toHaveText(['25.540', '—', '—']);
  await expect(row).toContainText('Lap 3');
  await expect(row).not.toContainText('Lap 4');
});
