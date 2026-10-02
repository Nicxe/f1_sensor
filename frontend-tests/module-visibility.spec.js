const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('an entity condition hides only its module and reacts to Home Assistant state changes', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [
    { id: 'overview', type: 'overview', visibility: [{ condition: 'state', entity: 'input_boolean.show_overview', state: 'on' }] },
    { id: 'calendar', type: 'calendar' },
  ] } }));
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Schedule', exact: true })).toBeVisible();

  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, states: { ...card.hass.states, 'input_boolean.show_overview': { state: 'on', attributes: {} } } };
  });
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toBeVisible();

  await page.evaluate(() => {
    const card = window.fixtureCard, state = card.hass.states['input_boolean.show_overview'];
    card.hass = { ...card.hass, states: { ...card.hass.states, 'input_boolean.show_overview': { ...state, state: 'off' } } };
  });
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toHaveCount(0);
});

test('screen visibility removes hidden tabs and follows viewport changes', async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { layout: 'tabs', modules: [
    { id: 'desktop', type: 'overview', title: 'Desktop overview', visibility: [{ condition: 'screen', media_query: '(min-width: 768px)' }] },
    { id: 'all', type: 'calendar', title: 'Schedule' },
  ] } }));
  await expect(page.getByRole('button', { name: 'Desktop overview', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Schedule', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(page.getByRole('button', { name: 'Desktop overview', exact: true })).toBeVisible();
});

test('the visual editor creates a module state condition without raw JSON', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'overview' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Visibility conditions', { exact: true }).click();
  await expect(editor.getByText('Always visible', { exact: true })).toBeVisible();
  await editor.getByLabel('Add condition', { exact: true }).selectOption('state');
  const condition = editor.getByRole('region', { name: 'Condition 1', exact: true });
  await condition.getByLabel('Entity', { exact: true }).fill('input_boolean.show_f1');
  await condition.getByLabel('Entity', { exact: true }).press('Tab');
  await condition.getByLabel('State values, separated by commas', { exact: true }).fill('on, auto');
  await condition.getByLabel('State values, separated by commas', { exact: true }).press('Tab');
  expect(await page.evaluate(() => window.savedConfig.modules[0].visibility)).toEqual([
    { condition: 'state', entity: 'input_boolean.show_f1', state: ['on', 'auto'] },
  ]);
  await expect(editor.getByText('Hidden now', { exact: true })).toBeVisible();
  const accessibility = await new AxeBuilder({ page }).include('f1-sensor-card-editor').analyze();
  expect(accessibility.violations.filter(({ impact }) => ['serious', 'critical'].includes(impact))).toEqual([]);
});
