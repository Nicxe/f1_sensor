const { test, expect } = require('@playwright/test');

test('two replay cards share a pending command and permit an explicit retry after failure', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'replay' }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.replay_status].state = 'selected';
    demo.hass.states[entry.entities.replay_status].attributes.selected_session = 'Demo Grand Prix · Race';
    window.replayCalls = [];
    const hass = { ...demo.hass, connection: { connected: true, subscribeEvents: async () => () => {} }, callWS: async () => demo.preview.entries, callService: (...args) => {
      window.replayCalls.push(args);
      return new Promise((resolve, reject) => { window.finishReplay = resolve; window.failReplay = reject; });
    } };
    const first = window.fixtureCard;
    first.entries = demo.preview.entries; first.previewData = null; first.hass = hass;
    const second = document.createElement('f1-sensor-card');
    second.setConfig({ modules: [{ type: 'replay' }] });
    second.entries = demo.preview.entries; second.hass = hass;
    document.querySelector('#root').append(second);
  });
  const cards = page.locator('f1-sensor-card');
  await cards.nth(0).getByText('Choose replay', { exact: true }).click();
  await cards.nth(1).getByText('Choose replay', { exact: true }).click();
  const first = cards.nth(0).getByRole('button', { name: 'Load selected replay', exact: true });
  const second = cards.nth(1).getByRole('button', { name: 'Load selected replay', exact: true });
  await first.click(); await cards.nth(1).getByRole('button', { name: 'Refresh session list', exact: true }).click();
  expect(await page.evaluate(() => window.replayCalls.length)).toBe(1);
  await expect(cards.nth(1).getByRole('status')).toContainText('Command not sent: another card was sending a replay command');
  await page.evaluate(() => window.failReplay(new Error('simulated service failure')));
  await expect(cards.nth(0).getByRole('alert')).toContainText('The replay command failed');
  await second.click();
  expect(await page.evaluate(() => window.replayCalls.length)).toBe(2);
  await expect(second).toBeDisabled();
  await page.evaluate(() => window.finishReplay());
  await expect(second).toBeEnabled();
  await expect(cards.nth(1).getByRole('status')).toHaveCount(0);
});
