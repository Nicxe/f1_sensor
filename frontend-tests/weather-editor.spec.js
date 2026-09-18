const { test, expect } = require('@playwright/test');

test('weather template and custom fields survive UI edits and serialized reload', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1100 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [] } }));
  let editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Start from a template', { exact: true }).click();
  await editor.getByRole('button', { name: /^Weather comparison/ }).click();
  await expect(editor.getByRole('button', { name: '1. Automatic current weather', exact: true })).toBeVisible();
  await expect(editor.getByRole('button', { name: '2. Race-start forecast', exact: true })).toBeVisible();
  await editor.getByLabel('Module title', { exact: true }).fill('My weather');
  await editor.getByLabel('Module title', { exact: true }).press('Tab');
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByLabel('Weather source', { exact: true })).toHaveValue('automatic_conditions');
  await editor.getByLabel('Weather layout', { exact: true }).selectOption('compact_list');
  await editor.getByRole('checkbox', { name: 'Track temperature', exact: true }).check();
  await editor.getByRole('checkbox', { name: 'Humidity', exact: true }).uncheck();
  const saved = await page.evaluate(() => JSON.parse(JSON.stringify(window.savedConfig)));
  expect(saved.modules.map(m => m.options.content)).toEqual(['automatic_conditions', 'race_forecast']);
  expect(saved.modules[0].fields).toContain('track_temperature');
  expect(saved.modules[0].fields).not.toContain('humidity');
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ editor: true, config }), saved);
  editor = page.locator('f1-sensor-card-editor');
  await expect(editor.getByRole('button', { name: '1. My weather', exact: true })).toBeVisible();
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByLabel('Weather source', { exact: true })).toHaveValue('automatic_conditions');
  await expect(editor.getByLabel('Weather layout', { exact: true })).toHaveValue('compact_list');
  await expect(editor.getByRole('checkbox', { name: 'Track temperature', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'Humidity', exact: true })).not.toBeChecked();
});

test('Swedish module names distinguish automatic weather from the race forecast', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => window.mountModular({ editor: true, preset: 'weather', language: 'sv' }));
  const editor = page.locator('f1-sensor-card-editor');
  await expect(editor.getByRole('button', { name: '1. Automatiskt aktuellt väder', exact: true })).toBeVisible();
  await expect(editor.getByRole('button', { name: '2. Prognos inför racestart', exact: true })).toBeVisible();
  await editor.getByRole('button', { name: 'Flytta upp Prognos inför racestart', exact: true }).click();
  await expect(editor.getByRole('button', { name: '1. Prognos inför racestart', exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.savedConfig.modules.map(m => m.options.content))).toEqual(['race_forecast', 'automatic_conditions']);
});

test('weather display follows HA unit changes for both current observations and race forecast', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ preset: 'weather' });
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, config: { ...card.hass.config, unit_system: { temperature: '°F', wind_speed: 'mph' } }, states: { ...card.hass.states,
      [entry.entities.session_status]: { state: 'live', attributes: {} },
      [entry.entities.track_weather]: { state: 'live', attributes: { air_temperature: 20, wind_speed: 10 } },
      [entry.entities.weather]: { state: 'cloudy', attributes: { race_temperature: 0, race_wind_speed: 0 } },
    } };
  });
  const modules = page.locator('f1-module-view');
  await expect(modules).toHaveCount(2);
  await expect(modules.nth(0)).toContainText('68 °F');
  await expect(modules.nth(0)).toContainText('22.4 mph');
  await expect(modules.nth(1)).toContainText('32 °F');
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, config: { ...card.hass.config, unit_system: { temperature: '°C', wind_speed: 'km/h' } } };
  });
  await expect(modules.nth(0)).toContainText('20 °C');
  await expect(modules.nth(0)).toContainText('36 km/h');
  await expect(modules.nth(1)).toContainText('0 °C');
});
