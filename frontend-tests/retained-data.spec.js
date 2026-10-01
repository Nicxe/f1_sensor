const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, modules = [{ id: 'timing', type: 'timing', fields: ['driver', 'last_lap'], unavailable: 'retain' }]) {
  await page.evaluate(modules => {
    window.mountModular({ config: { modules } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    const connection = new EventTarget(); connection.connected = true;
    connection.subscribeEvents = async () => () => {};
    window.retainedServices = [];
    card.previewData = null;
    card.hass = { ...demo.hass, connection, callWS: async () => demo.preview.entries,
      callService: async (...args) => window.retainedServices.push(args) };
    window.pushRetained = (key, state, attributes = {}) => {
      const id = demo.preview.entries[0].entities[key];
      card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], state, attributes } } };
    };
  }, modules);
  await expect(page.locator('f1-module-view').first()).toBeVisible();
}

test('retain preserves cleared attributes, keeps filters usable and yields to recovered empty data', async ({ page }) => {
  await mount(page);
  await expect(page.locator('button.driver')).toHaveCount(5);
  await page.evaluate(() => window.pushRetained('driver_positions', 'unavailable'));
  await expect(page.locator('button.driver')).toHaveCount(5);
  await expect(page.getByText('Saved data · source currently unavailable.', { exact: true })).toBeVisible();
  await page.evaluate(() => window.pushRetained('driver_list', 'unavailable'));
  await page.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('4');
  await expect(page.locator('button.driver')).toHaveCount(1);
  await expect(page.locator('button.driver')).toContainText('NOR');
  await expect(page.locator('.data-time')).toHaveCount(0);
  await page.evaluate(() => window.pushRetained('driver_positions', '0', { drivers: [] }));
  await expect(page.locator('button.driver')).toHaveCount(0);
  await expect(page.getByText('Saved data · source currently unavailable.', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.pushRetained('driver_positions', 'unavailable'));
  await expect(page.locator('button.driver')).toHaveCount(0);
  expect(await page.evaluate(() => window.retainedServices)).toEqual([]);
});

test('session changes and unknown spoiler state discard snapshots instead of reviving a previous session', async ({ page }) => {
  await mount(page);
  await expect(page.locator('button.driver')).toHaveCount(5);
  await page.evaluate(() => window.pushRetained('driver_positions', 'unavailable'));
  await expect(page.locator('button.driver')).toHaveCount(5);
  await page.evaluate(() => window.pushRetained('current_session', 'Qualifying', { active: true, meeting_key: 'new', start: '2026-09-14T13:00:00Z' }));
  await expect(page.locator('button.driver')).toHaveCount(0);
  await mount(page);
  await expect(page.locator('button.driver')).toHaveCount(5);
  await page.evaluate(() => {
    window.pushRetained('driver_positions', 'unavailable');
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { state: 'unknown' } } };
  });
  await expect(page.getByText(/Spoiler status cannot be verified/)).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { state: 'off' } } };
  });
  await expect(page.locator('button.driver')).toHaveCount(0);
});

test('retain, explain and hide keep independent behavior for the same source', async ({ page }) => {
  await mount(page, ['retain', 'explain', 'hide'].map(unavailable => ({ id: unavailable, type: 'weather', unavailable })));
  await expect(page.locator('#module-retain .weather-item').first()).toBeVisible();
  const before = await page.locator('#module-retain .weather-item').first().innerText();
  await page.evaluate(() => window.pushRetained('weather', 'unavailable'));
  await expect(page.locator('#module-retain .weather-item').first()).toHaveText(before, { useInnerText: true });
  await expect(page.locator('#module-explain .weather-item')).toHaveCount(0);
  await expect(page.locator('#module-hide')).toHaveCount(0);
  await expect(page.locator('#module-retain')).toContainText('Saved data');
});

test('changing Live Delay clears saved live timing and never writes a service from rendering', async ({ page }) => {
  await mount(page);
  await expect(page.locator('button.driver')).toHaveCount(5);
  await page.evaluate(() => window.pushRetained('driver_positions', 'unavailable'));
  await expect(page.locator('button.driver')).toHaveCount(5);
  await page.evaluate(() => window.pushRetained('live_delay_number', '90'));
  await expect(page.locator('button.driver')).toHaveCount(0);
  expect(await page.evaluate(() => window.retainedServices)).toEqual([]);
});
