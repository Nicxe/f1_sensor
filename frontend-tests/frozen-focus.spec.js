const { test, expect } = require('@playwright/test');

test('a frozen group card retains its driver and roster until resuming the latest shared focus', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    const config = { context: { scope: 'group', group: 'race' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] };
    window.mountModular({ config });
    const demo = window.fixtureDemo;
    const hass = { ...demo.hass, connection: { connected: true, subscribeEvents: async () => () => {} }, callWS: async () => demo.preview.entries, callService: () => { throw new Error('Focus must never write to HA'); } };
    const first = window.fixtureCard;
    first.entries = demo.preview.entries; first.previewData = null; first.hass = hass;
    const second = document.createElement('f1-sensor-card');
    second.setConfig(config); second.entries = demo.preview.entries; second.hass = hass;
    document.querySelector('#root').append(second);
  });
  const first = page.locator('f1-sensor-card').nth(0), second = page.locator('f1-sensor-card').nth(1);
  await first.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('16');
  await expect(second.getByRole('combobox', { name: 'Driver focus', exact: true })).toHaveValue('16');
  await first.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await second.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('4');
  await expect(first.getByRole('combobox', { name: 'Driver focus', exact: true })).toHaveValue('16');
  await expect(first.locator('tr[data-driver]')).toHaveCount(1);
  await expect(first.locator('tr[data-driver="16"]')).toBeVisible();
  await expect(first.locator('.frozen')).toContainText('Group focus has changed');
  await expect(second.locator('tr[data-driver="4"]')).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, id = card.entry.entities.driver_list;
    const old = card.hass.states[id];
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...old, attributes: { ...old.attributes, drivers: old.attributes.drivers.filter(driver => String(driver.racing_number) !== '16') } } } };
  });
  await expect(first.getByRole('combobox', { name: 'Driver focus', exact: true })).toHaveValue('16');
  await expect(first.getByRole('combobox', { name: 'Driver focus', exact: true }).locator('option:checked')).toHaveText('LEC');
  await first.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(first.getByRole('combobox', { name: 'Driver focus', exact: true })).toHaveValue('4');
  await expect(first.locator('tr[data-driver="4"]')).toBeVisible();
  await expect(first.locator('.frozen')).toHaveCount(0);
  await first.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await first.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('63');
  await expect(first.locator('.frozen')).toHaveCount(0);
  await expect(second.getByRole('combobox', { name: 'Driver focus', exact: true })).toHaveValue('63');
  await first.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => { const card = window.fixtureCard; card.remove(); document.querySelector('#root').prepend(card); });
  await expect(first.getByRole('button', { name: 'Freeze view', exact: true })).toBeVisible();
  await expect(first.locator('.frozen')).toHaveCount(0);
  await expect(first.locator('tr[data-driver="63"]')).toBeVisible();
});
