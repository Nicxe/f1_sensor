const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(async () => {
    await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/register.js');
    window.mountMigration = (config, scene = 'race') => {
      window.originalConfig = structuredClone(config); window.migrationEvents = []; window.migrationRequests = []; window.migrationActions = [];
      const node = customElements.get(config.type.replace('custom:', '')).getConfigElement();
      window.mountModular({ scene });
      node.hass = { ...window.fixtureDemo.hass, connection: { subscribeEvents: async () => () => {} }, callWS: async request => { window.migrationRequests.push(request.type); return window.fixtureDemo.preview.entries; }, callService: (...args) => window.migrationActions.push(args) };
      node.setConfig(config);
      node.addEventListener('config-changed', event => window.migrationEvents.push(structuredClone(event.detail.config)));
      document.querySelector('#root').replaceChildren(node); window.migrationEditor = node;
    };
  });
});

test('all legacy factories including archive alias expose conversion without publishing a change', async ({ page }) => {
  const counts = await page.evaluate(async () => {
    const { LEGACY_MIGRATIONS } = await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/migration.js');
    return Object.keys(LEGACY_MIGRATIONS).map(type => ({ type, tag: customElements.get(type).getConfigElement().localName }));
  });
  expect(counts).toHaveLength(24); expect(counts.every(c => c.tag === 'f1-migration-editor')).toBe(true);
  await page.evaluate(() => window.mountMigration({ type: 'custom:f1-practice-timing-card', title: 'Original', color_overall_fastest: '#123456', show_sectors: true }));
  await expect(page.getByRole('button', { name: 'Review conversion', exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.migrationEvents)).toEqual([]);
  await page.getByRole('button', { name: 'Review conversion', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Apply conversion', exact: true })).toBeDisabled();
  await expect(page.getByText('DEMO · sample data')).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'F1 Sensor installation', exact: true })).toHaveValue('demo');
  await page.getByRole('button', { name: 'Cancel conversion', exact: true }).click();
  expect(await page.evaluate(() => window.migrationEvents)).toEqual([]);
  await expect(page.locator('f1-practice-timing-card-editor')).toBeVisible();
  expect(await page.evaluate(() => window.migrationActions)).toEqual([]);
  expect(await page.evaluate(() => [...new Set(window.migrationRequests)])).toEqual(['f1_sensor/entities']);
});

test('every actual legacy stub configuration converts and restores exactly', async ({ page }) => {
  const results = await page.evaluate(async () => {
    const [{ LEGACY_MIGRATIONS, proposeMigration, restoreLegacy }, { configWarnings }] = await Promise.all([
      import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/migration.js'),
      import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js'),
    ]);
    return Promise.all(Object.keys(LEGACY_MIGRATIONS).map(async type => {
      const source = structuredClone(await customElements.get(type).getStubConfig());
      source.type = `custom:${type}`;
      const { config, rows } = proposeMigration(source, { entries: [{ entry_id: 'demo', title: 'DEMO', entities: {}, global_entities: {} }] });
      return {
        type,
        warnings: configWarnings(config),
        restored: restoreLegacy(config),
        source,
        missing: Object.keys(source).filter(key => !rows.some(row => row.path === key)),
      };
    }));
  });
  expect(results).toHaveLength(24);
  for (const result of results) {
    expect(result.warnings, result.type).toEqual([]);
    expect(result.missing, result.type).toEqual([]);
    expect(result.restored, result.type).toEqual(result.source);
  }
});

test('conversion review, UI edits, serialized reload and restore retain the exact original', async ({ page }) => {
  await page.evaluate(() => window.mountMigration({ type: 'custom:f1-practice-timing-card', title: 'Original', color_overall_fastest: '#123456', show_sectors: true, extra: { marker: [1, false] }, tap_action: { action: 'navigate', navigation_path: '/original' } }));
  await page.getByRole('button', { name: 'Review conversion', exact: true }).click();
  await expect(page.getByText('extra', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: 'I have reviewed the differences and settings that need to be chosen again.' }).check();
  await page.getByRole('button', { name: 'Apply conversion', exact: true }).click();
  await expect(page.locator('f1-sensor-card-editor')).toBeVisible();
  expect(await page.evaluate(() => window.migrationEvents.at(-1))).toMatchObject({ type: 'custom:f1-sensor-card', appearance: { palette: { overall: '#123456' } } });
  await page.locator('f1-sensor-card-editor').getByRole('textbox', { name: 'Card title', exact: true }).fill('New title');
  await page.locator('f1-sensor-card-editor').getByRole('textbox', { name: 'Card title', exact: true }).press('Tab');
  await page.evaluate(() => {
    const saved = JSON.parse(JSON.stringify(window.migrationEvents.at(-1)));
    const node = document.createElement('f1-sensor-card-editor'); node.hass = window.migrationEditor.hass; node.setConfig(saved);
    node.addEventListener('config-changed', event => window.migrationEvents.push(structuredClone(event.detail.config)));
    document.querySelector('#root').replaceChildren(node);
  });
  await page.getByText('Original card and recovery', { exact: true }).click();
  await page.getByRole('button', { name: 'Export original', exact: true }).click();
  expect(JSON.parse(await page.getByRole('textbox', { name: 'Original configuration', exact: true }).inputValue())).toEqual(await page.evaluate(() => window.originalConfig));
  await page.getByRole('button', { name: 'Restore original…', exact: true }).click();
  const count = await page.evaluate(() => window.migrationEvents.length);
  await page.getByRole('button', { name: 'Cancel restoration', exact: true }).click();
  expect(await page.evaluate(() => window.migrationEvents.length)).toBe(count);
  await page.getByRole('button', { name: 'Restore original…', exact: true }).click();
  await page.getByRole('button', { name: 'Restore original card', exact: true }).click();
  expect(await page.evaluate(() => window.migrationEvents.at(-1))).toEqual(await page.evaluate(() => window.originalConfig));
  expect(await page.evaluate(() => window.migrationActions)).toEqual([]);
});

test('weather conversion reviews two modules and restores both source and visibility preferences', async ({ page }) => {
  await page.evaluate(() => window.mountMigration({ type: 'custom:f1-weather-card', prefer_live_weather: false, show_weather: false }));
  await page.getByRole('button', { name: 'Review conversion', exact: true }).click();
  await page.locator('summary').filter({ hasText: 'Changed behavior' }).click();
  await expect(page.getByText(/Current weather and race-start forecast become two independently editable modules/)).toBeVisible();
  await page.getByRole('checkbox', { name: 'I have reviewed the differences and settings that need to be chosen again.' }).check();
  await page.getByRole('button', { name: 'Apply conversion', exact: true }).click();
  const weather = await page.evaluate(() => window.migrationEvents.at(-1).modules.filter(m => m.type === 'weather'));
  expect(weather).toHaveLength(2);
  expect(weather.map(m => m.options.content)).toEqual(['current_conditions', 'race_forecast']);
  expect(weather.every(m => !m.enabled)).toBe(true);
  await page.evaluate(() => {
    const node = document.createElement('f1-sensor-card-editor');
    node.hass = window.migrationEditor.hass;
    node.setConfig(JSON.parse(JSON.stringify(window.migrationEvents.at(-1))));
    node.addEventListener('config-changed', event => window.migrationEvents.push(structuredClone(event.detail.config)));
    document.querySelector('#root').replaceChildren(node);
  });
  await page.getByText('Original card and recovery', { exact: true }).click();
  await page.getByRole('button', { name: 'Restore original…', exact: true }).click();
  await page.getByRole('button', { name: 'Restore original card', exact: true }).click();
  expect(await page.evaluate(() => window.migrationEvents.at(-1))).toEqual(await page.evaluate(() => window.originalConfig));
  expect(await page.evaluate(() => window.migrationActions)).toEqual([]);
});

test('Weekend Hub conversion opens the configured tab and explains the shared update interval', async ({ page }) => {
  await page.evaluate(() => window.mountMigration({ type: 'custom:f1-weekend-hub-card', default_view: 'strategy', throttle_ms: 500 }));
  await page.getByRole('button', { name: 'Review conversion', exact: true }).click();
  await expect(page.locator('f1-sensor-card').getByRole('button', { name: 'Stint pace and quality', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('summary').filter({ hasText: 'Changed behavior' }).click();
  await expect(page.getByText(/effective 500 ms update interval is retained/)).toBeVisible();
  await page.getByRole('checkbox', { name: 'I have reviewed the differences and settings that need to be chosen again.' }).check();
  await page.getByRole('button', { name: 'Apply conversion', exact: true }).click();
  expect(await page.evaluate(() => ({ layout: window.migrationEvents.at(-1).layout, first: window.migrationEvents.at(-1).modules[0].type }))).toEqual({ layout: 'tabs', first: 'strategy' });
  expect(await page.evaluate(() => window.migrationActions)).toEqual([]);
});

test('Pit Stops conversion transfers status and availability controls into the live preview', async ({ page }) => {
  await page.evaluate(() => window.mountMigration({
    type: 'custom:f1-pitstop-overview-card', auth_status_entity: 'sensor.f1_f1tv_token_status',
    show_availability_notice: false, show_status: true,
  }));
  await page.getByRole('button', { name: 'Review conversion', exact: true }).click();
  const preview = page.locator('f1-sensor-card');
  await expect(preview.getByRole('columnheader', { name: 'Status', exact: true })).toBeVisible();
  await expect(preview.getByText('On track', { exact: true }).first()).toBeVisible();
  await page.locator('summary').filter({ hasText: 'Transferred settings' }).click();
  for (const key of ['show_availability_notice', 'show_status']) await expect(page.getByText(key, { exact: true })).toBeVisible();
  await page.locator('summary').filter({ hasText: 'Changed behavior' }).click();
  await expect(page.getByText('auth_status_entity', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: 'I have reviewed the differences and settings that need to be chosen again.' }).check();
  await page.getByRole('button', { name: 'Apply conversion', exact: true }).click();
  expect(await page.evaluate(() => {
    const pit = window.migrationEvents.at(-1).modules.find(module => module.type === 'pit_stops');
    return { status: pit.fields.includes('status'), availability: pit.options.show_availability_notice };
  })).toEqual({ status: true, availability: false });
  expect(await page.evaluate(() => window.migrationActions)).toEqual([]);
});

test('Qualifying conversion transfers current-part gaps into the live preview', async ({ page }) => {
  await page.evaluate(() => window.mountMigration({ type: 'custom:f1-qualifying-timing-card', show_delta: true }, 'qualifying'));
  await page.getByRole('button', { name: 'Review conversion', exact: true }).click();
  const preview = page.locator('f1-sensor-card');
  await expect(preview.getByRole('columnheader', { name: 'Current part gap', exact: true })).toBeVisible();
  await expect(preview.getByRole('row', { name: /NOR · Lando Norris/ }).getByRole('cell').nth(5)).toHaveText('0.25');
  await page.locator('summary').filter({ hasText: 'Transferred settings' }).click();
  await expect(page.getByText('show_delta', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: 'I have reviewed the differences and settings that need to be chosen again.' }).check();
  await page.getByRole('button', { name: 'Apply conversion', exact: true }).click();
  expect(await page.evaluate(() => window.migrationEvents.at(-1).modules[0].fields.includes('qualifying_gap'))).toBe(true);
  expect(await page.evaluate(() => window.migrationActions)).toEqual([]);
});

test('conversion review supports keyboard, narrow widths, Swedish and forced colors', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.evaluate(() => {
    window.mountMigration({ type: 'custom:f1-weekend-hub-card', title: 'Helgen', unknown: true });
    window.migrationEditor.hass = { ...window.migrationEditor.hass, locale: { ...window.migrationEditor.hass.locale, language: 'sv' } };
  });
  await page.getByRole('button', { name: 'Granska konvertering', exact: true }).focus(); await page.keyboard.press('Enter');
  await expect(page.getByText('Ändrat beteende', { exact: false })).toBeVisible();
  const check = page.getByRole('checkbox'); await check.focus(); await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Tillämpa konvertering', exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const violations = await new AxeBuilder({ page }).include('f1-migration-editor').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(violations.violations).toEqual([]);
});
