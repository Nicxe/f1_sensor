const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function live(page, context = {}) {
  await page.evaluate(context => {
    window.mountModular({ config: { context: { viewing_controls: true, ...context }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.viewingCalls = []; window.failViewing = false; window.holdViewing = false;
    const connection = { connected: true, subscribeEvents: async () => () => {} };
    card.previewData = null;
    const callService = async (domain, service, data) => {
      window.viewingCalls.push({ domain, service, data });
      if (window.failViewing) throw new Error('Permission denied');
      if (window.holdViewing) await new Promise(resolve => { window.resolveViewing = resolve; });
      const old = card.hass.states[data.entity_id];
      card.hass = { ...card.hass, states: { ...card.hass.states, [data.entity_id]: { ...old, state: domain === 'number' ? String(data.value) : service === 'turn_on' ? 'on' : 'off', last_changed: new Date().toISOString() } } };
    };
    card.hass = { ...demo.hass, connection, callWS: async () => demo.preview.entries, callService };
  }, context);
  const panel = page.locator('f1-viewing-controls');
  await panel.locator('summary').first().click();
  return panel;
}

test('viewing controls opt in through editor, save and remain inert in both preview modes', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Layout and shared focus', { exact: true }).click();
  await editor.getByLabel('Show Live Delay and global spoiler controls', { exact: true }).check();
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.context.viewing_controls).toBe(true);
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => { window.mountModular({ config }); window.viewingCalls = []; window.fixtureCard.hass.callService = (...args) => window.viewingCalls.push(args); }, saved);
  const panel = page.locator('f1-viewing-controls');
  await panel.locator('summary').first().click();
  await expect(panel.getByRole('button', { name: 'Enable global protection', exact: true })).toBeDisabled();
  await page.evaluate(() => { const card = window.fixtureCard; card.viewingAction({ stopPropagation() {}, detail: { action: 'protect', connection: card.hass.connection, context: card.shadowRoot.querySelector('f1-viewing-controls').model.spoilers.context } }); });
  expect(await page.evaluate(() => window.viewingCalls)).toEqual([]);
  await live(page);
  await page.evaluate(() => { window.fixtureCard.preview = true; });
  await expect(panel.getByLabel('Delay in seconds', { exact: true })).toBeDisabled();
  await expect(panel.getByRole('button', { name: 'Enable global protection', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.viewingCalls)).toEqual([]);
});

test('delay applies only on submission, accepts zero and rejects stale drafts and calibration changes', async ({ page }) => {
  const panel = await live(page), input = panel.getByLabel('Delay in seconds', { exact: true });
  await input.fill('0');
  expect(await page.evaluate(() => window.viewingCalls)).toEqual([]);
  await input.press('Enter');
  await expect(panel.getByText('Saved value: 0 s', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.viewingCalls)).toEqual([{ domain: 'number', service: 'set_value', data: { entity_id: 'number.f1_demo_live_delay_number', value: 0 } }]);
  await input.fill('50');
  await page.evaluate(() => { const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].entities.live_delay_number; card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], state: '30' } } }; });
  await expect(panel.getByText('Settings changed elsewhere. Use the current value before editing again.', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Apply live delay', exact: true })).toBeDisabled();
  await panel.getByRole('button', { name: 'Use current value', exact: true }).click();
  await expect(input).toHaveValue('30');
  await expect(input).toBeFocused();
  await page.evaluate(() => { const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].entities.delay_calibration_switch; card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], state: 'on' } } }; });
  await expect(input).toBeDisabled();
  await expect(panel.getByText(/Calibration is active/)).toBeVisible();
  expect(await page.evaluate(() => window.viewingCalls.length)).toBe(1);
});

test('global reveal requires review, cancel keeps protection and local masking survives global changes', async ({ page }) => {
  const panel = await live(page, { spoilers: 'hide' });
  await panel.getByRole('button', { name: 'Enable global protection', exact: true }).click();
  await expect(panel.getByText('Global protection on', { exact: true })).toBeVisible();
  await panel.getByRole('button', { name: 'Review turning protection off', exact: true }).click();
  await expect(panel.getByText(/Turning protection off requests current results/)).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Turn off protection for all F1 installations', exact: true })).toBeFocused();
  expect(await page.evaluate(() => window.viewingCalls.length)).toBe(1);
  await panel.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Review turning protection off', exact: true })).toBeFocused();
  expect(await page.evaluate(() => window.viewingCalls.length)).toBe(1);
  await panel.getByRole('button', { name: 'Review turning protection off', exact: true }).click();
  await panel.getByRole('button', { name: 'Turn off protection for all F1 installations', exact: true }).click();
  await expect(panel.getByText('Global protection off', { exact: true })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Enable global protection', exact: true })).toBeFocused();
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(panel.getByText(/This card also hides spoilers locally/)).toBeVisible();
  expect(await page.evaluate(() => window.viewingCalls.map(call => call.service))).toEqual(['turn_on', 'turn_off']);
});

test('service failures retain authoritative values; freeze, disconnect and stale review cannot write', async ({ page }) => {
  const panel = await live(page);
  await page.evaluate(() => { window.failViewing = true; });
  await panel.getByRole('button', { name: 'Enable global protection', exact: true }).click();
  await expect(panel.getByText(/The change could not be completed/)).toBeVisible();
  await expect(panel.getByText('Global protection off', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Enable global protection', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await page.evaluate(() => { window.failViewing = false; window.fixtureCard.hass.connection.connected = false; window.fixtureCard.revision++; });
  await expect(panel.getByRole('button', { name: 'Enable global protection', exact: true })).toBeDisabled();
  await page.evaluate(() => { const card = window.fixtureCard; card.hass.connection.connected = true; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'on', attributes: {} } } }; });
  await panel.getByRole('button', { name: 'Review turning protection off', exact: true }).click();
  await page.evaluate(() => { const card = window.fixtureCard; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'unavailable', attributes: {} } } }; });
  await expect(panel.getByRole('button', { name: 'Turn off protection for all F1 installations', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.viewingCalls.length)).toBe(1);
});

test('pending commands are not repeated or retried after detach, and narrow controls remain accessible', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  const panel = await live(page);
  for (const mode of ['dark', 'light']) {
    await page.evaluate(mode => window.fixtureCard.setConfig({ ...window.fixtureCard.config, appearance: { ...window.fixtureCard.config.appearance, mode } }), mode);
    expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.emulateMedia({ forcedColors: 'active' });
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
  await page.evaluate(() => { window.holdViewing = true; });
  await panel.getByRole('button', { name: 'Enable global protection', exact: true }).click();
  await expect(panel.getByRole('button', { name: 'Enable global protection', exact: true })).toBeDisabled();
  await expect(panel.getByText('Applying viewing setting…', { exact: true })).toBeVisible();
  await page.evaluate(() => { window.fixtureCard.remove(); window.resolveViewing(); });
  expect(await page.evaluate(() => window.viewingCalls.length)).toBe(1);
});
