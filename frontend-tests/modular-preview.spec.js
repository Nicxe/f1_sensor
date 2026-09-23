const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { title: 'Preview test', modules: [{ type: 'timing', options: { profile: 'auto' } }] } });
    const demo = window.fixtureDemo;
    window.previewRequests = []; window.previewStops = 0; window.previewActions = [];
    window.actualHass = { ...demo.hass, connection: {
      connected: true, subscribeEvents: async () => () => window.previewStops++,
    }, callWS: async message => { window.previewRequests.push(message.type); return demo.preview.entries; },
    callService: async (...args) => window.previewActions.push(args) };
    window.originalStates = JSON.stringify(window.actualHass.states);
    window.previewHost = document.createElement('hui-dialog-edit-card');
    document.querySelector('#root').replaceChildren(window.previewHost);
    window.rebuildNativePreview = config => {
      const card = document.createElement('f1-sensor-card');
      card.hass = window.actualHass; card.preview = true;
      card.setConfig(config ?? { title: 'Preview test', modules: [{ type: 'timing', options: { profile: 'auto' } }], entity: 'switch.test', tap_action: { action: 'toggle' } });
      card.addEventListener('config-changed', event => window.previewActions.push(event.detail));
      card.addEventListener('hass-action', event => window.previewActions.push(event.detail));
      window.previewHost.replaceChildren(card); window.nativeCard = card;
    };
    window.rebuildNativePreview();
  });
  await expect(page.getByLabel('Preview data', { exact: true })).toHaveValue('actual');
  await expect(page.locator('button.driver').first()).toBeVisible();
});

test('native preview switches sources without changing HA states, config or integration settings', async ({ page }) => {
  const before = await page.evaluate(() => JSON.stringify(window.nativeCard.config));
  await expect(page.getByText('DEMO · sample data')).toHaveCount(0);
  await page.getByLabel('Preview data', { exact: true }).selectOption('sample');
  await expect(page.getByText('DEMO · sample data')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.previewStops)).toBe(1);
  await page.getByLabel('Sample session', { exact: true }).selectOption('sprint_qualifying');
  await expect(page.getByRole('columnheader', { name: 'SQ1 best', exact: true })).toBeVisible();
  await page.locator('[data-f1-card-action]').click();
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.getByLabel('Preview data', { exact: true }).selectOption('actual');
  await expect(page.getByText('DEMO · sample data')).toHaveCount(0);
  await expect(page.getByLabel('Sample session', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'SQ1 best', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Freeze view', exact: true })).toBeVisible();
  await page.locator('[data-f1-card-action]').click();
  expect(await page.evaluate(() => JSON.stringify(window.nativeCard.config))).toBe(before);
  expect(await page.evaluate(() => JSON.stringify(window.actualHass.states) === window.originalStates)).toBe(true);
  expect(await page.evaluate(() => window.previewActions)).toEqual([]);
  expect(await page.evaluate(() => window.previewRequests)).toEqual(['f1_sensor/entities', 'f1_sensor/entities']);
});

test('sample choice survives HA card recreation and remains confined to its preview host', async ({ page }) => {
  await page.getByLabel('Preview data', { exact: true }).selectOption('sample');
  await page.getByLabel('Sample session', { exact: true }).selectOption('qualifying');
  await page.evaluate(() => window.rebuildNativePreview({ ...window.nativeCard.config, title: 'Changed title' }));
  await expect(page.getByLabel('Preview data', { exact: true })).toHaveValue('sample');
  await expect(page.getByLabel('Sample session', { exact: true })).toHaveValue('qualifying');
  await expect(page.getByRole('columnheader', { name: 'Q1 best', exact: true })).toBeVisible();
  await page.evaluate(() => {
    const host = document.createElement('hui-dialog-edit-card'), card = document.createElement('f1-sensor-card');
    card.hass = window.actualHass; card.preview = true; card.setConfig(window.nativeCard.config);
    host.append(card); document.querySelector('#root').append(host); window.otherPreview = host;
  });
  await expect(page.getByLabel('Preview data', { exact: true }).nth(1)).toHaveValue('actual');
  await page.evaluate(() => { window.otherPreview.remove(); window.nativeCard.preview = false; });
  await expect(page.getByLabel('Preview data', { exact: true })).toHaveCount(0);
  await expect(page.getByText('DEMO · sample data')).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Q1 best', exact: true })).toHaveCount(0);
  await expect(page.locator('button.driver').first()).toBeVisible();
});

test('sample data works without a discovered installation or a visible card header', async ({ page }) => {
  await page.evaluate(() => {
    window.actualHass = { states: {}, locale: { language: 'en' }, themes: { darkMode: false } };
    window.rebuildNativePreview({ f1_entry_id: 'unavailable-entry', appearance: { show_header: false }, modules: [{ type: 'timing', options: { profile: 'auto' } }] });
  });
  await expect(page.getByText('Waiting for F1 Sensor…')).toBeVisible();
  await page.getByLabel('Preview data', { exact: true }).selectOption('sample');
  await expect(page.locator('button.driver').first()).toBeVisible();
  await expect(page.getByText('DEMO · sample data')).toBeVisible();
  await page.getByLabel('Sample session', { exact: true }).selectOption('missing');
  await expect(page.locator('button.driver')).toHaveCount(0);
  await page.getByLabel('Preview data', { exact: true }).selectOption('actual');
  await expect(page.getByText('Waiting for F1 Sensor…')).toBeVisible();
  await expect(page.getByText('DEMO · sample data')).toHaveCount(0);
});

test('preview controls support Swedish, keyboard, narrow screens and accessible labels', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 950 });
  await page.evaluate(() => {
    window.nativeCard.hass = { ...window.actualHass, locale: { ...window.actualHass.locale, language: 'sv' } };
    window.nativeCard.setConfig({ ...window.nativeCard.config, layout: 'columns', columns: 3 });
  });
  const source = page.getByLabel('Data i förhandsvisningen', { exact: true });
  await source.focus();
  await source.selectOption('sample');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Exempelsession', { exact: true })).toBeFocused();
  await expect(page.getByText('DEMO · exempeldata')).toBeVisible();
  await expect(page.getByText('Home Assistant begränsar förhandsvisningens bredd.', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const audit = await new AxeBuilder({ page }).include('f1-sensor-card').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(audit.violations).toEqual([]);
});


test('dashboard edit mode keeps real data and has no sample controls', async ({ page }) => {
  await page.getByLabel('Preview data', { exact: true }).selectOption('sample');
  await page.evaluate(() => {
    const editMode = document.createElement('hui-card-edit-mode');
    editMode.append(window.nativeCard);
    document.querySelector('#root').replaceChildren(editMode);
  });
  await expect(page.getByLabel('Preview data', { exact: true })).toHaveCount(0);
  await expect(page.getByText('DEMO · sample data')).toHaveCount(0);
  await expect(page.locator('button.driver').first()).toBeVisible();
});
