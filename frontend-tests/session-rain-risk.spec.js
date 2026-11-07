const { test, expect } = require('@playwright/test');

const start = async (page, modules) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(modules => window.mountModular({ config: { modules } }), modules);
};
const riskModule = (type, options = {}) => ({ type, fields: ['session_rain_risk'], options });

test('Overview and Weather share the session assessment while the race forecast remains distinct', async ({ page }) => {
  await start(page, [{ type: 'overview', fields: ['session', 'session_rain_risk'] },
    { type: 'weather', fields: ['rain_probability', 'session_rain_risk'], options: { content: 'race_forecast' } }]);
  const modules = page.locator('f1-module-view');
  await expect(modules.nth(0).getByText('30 %', { exact: true })).toBeVisible();
  await expect(modules.nth(1)).toContainText('30 %');
  await expect(modules.nth(1).getByText('15 %', { exact: true })).toBeVisible();
  const details = modules.nth(0).locator('.rain-risk-details');
  await expect(details.locator('p').first()).not.toBeVisible();
  await details.locator('summary').click();
  await expect(details).toContainText('RISK OF RAIN FOR F1 RACE IS 30%');
  await expect(details.locator('time')).toContainText('UTC');
  await expect(details.locator('time')).toHaveAttribute('datetime', '2026-09-13T13:15:00Z');
});

test('missing assessments disappear, explicit zero displays and another session cannot reuse the value', async ({ page }) => {
  await start(page, [riskModule('overview'), riskModule('weather', { content: 'current_conditions' })]);
  const modules = page.locator('f1-module-view');
  await expect(modules).toHaveCount(2);
  const change = async value => page.evaluate(value => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    const id = entry.entities.session_rain_risk, old = card.hass.states[id];
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...old, state: value,
      attributes: { ...old.attributes, percentage: value === 'unknown' ? null : Number(value) } } } };
  }, value);
  await change('unknown');
  await expect(modules).toHaveCount(0);
  await change('0');
  await expect(modules).toHaveCount(2);
  for (const module of await modules.all()) await expect(module).toContainText('0 %');
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0], id = entry.entities.current_session;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], attributes: { ...card.hass.states[id].attributes, session_key: 'new-session' } } } };
  });
  await expect(modules).toHaveCount(0);
});

test('per-field spoiler protection leaves public Overview and forecast information visible', async ({ page }) => {
  await start(page, [{ type: 'overview', fields: ['meeting', 'session_rain_risk'] },
    { type: 'weather', fields: ['rain_probability', 'session_rain_risk'], options: { content: 'race_forecast' } }]);
  const modules = page.locator('f1-module-view');
  await expect(modules.nth(0).getByText('30 %', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { state: 'on', attributes: {} } } };
  });
  await expect(modules.nth(0)).toContainText('Demo Grand Prix');
  await expect(modules.nth(0).getByText('30 %', { exact: true })).toHaveCount(0);
  await expect(modules.nth(1).locator('.rain-risk-details')).toHaveCount(0);
  await expect(modules.nth(1).getByText('15 %', { exact: true })).toBeVisible();
});

test('Weather displays a valid assessment independently of missing weather measurements', async ({ page }) => {
  await start(page, [riskModule('weather', { content: 'race_forecast' }),
    { type: 'weather', fields: ['temperature', 'session_rain_risk'], options: { content: 'track_conditions' } }]);
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states,
      [entry.entities.weather]: { state: 'unavailable', attributes: {} },
      [entry.entities.track_weather]: { state: 'unavailable', attributes: {} } } };
  });
  const modules = page.locator('f1-module-view');
  await expect(modules).toHaveCount(2);
  for (const module of await modules.all()) await expect(module).toContainText('30 %');
  await expect(modules.nth(0).locator('.chip')).toHaveCount(0);
  await expect(modules.nth(0).locator('.context')).toHaveCount(0);
});

test('the editor saves the independent session field without requiring a Race Control module', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'weather', options: { content: 'race_forecast' } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByRole('checkbox', { name: 'Session rain risk', exact: true }).check();
  const config = await page.evaluate(() => window.savedConfig);
  expect(config.modules).toHaveLength(1);
  expect(config.modules[0].fields).toContain('session_rain_risk');
  expect(config.modules[0].options.content).toBe('race_forecast');
});
