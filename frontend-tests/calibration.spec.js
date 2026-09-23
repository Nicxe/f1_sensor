const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, local = 'inherit') {
  await page.evaluate(local => {
    window.mountModular({ config: { context: { viewing_controls: true, spoilers: local }, modules: [] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const connection = { connected: true, subscribeEvents: async () => () => {} };
    window.calibrationCalls = []; window.calibrationFail = false; window.calibrationRun = 0;
    window.calibrationPush = (mode, attrs = {}) => {
      const id = entry.entities.delay_calibration_switch, value = card.hass.states[id];
      card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...value, state: mode === 'idle' ? 'off' : 'on', attributes: { ...value.attributes, mode, idle_reason: null, waiting_since: null, started_at: null, timeout_at: null, recorded_lap: null, elapsed: 0, ...attrs } } } };
    };
    const callService = async (domain, service, data) => {
      window.calibrationCalls.push({ domain, service, data });
      if (window.calibrationFail) throw new Error('Permission denied');
      if (domain === 'select') {
        const old = card.hass.states[data.entity_id];
        card.hass = { ...card.hass, states: { ...card.hass.states, [data.entity_id]: { ...old, state: data.option } } };
        window.calibrationPush('idle', { reference: data.option === 'Session live' ? 'session_live' : 'lap_sync' });
      } else if (domain === 'switch' && service === 'turn_on') {
        window.calibrationRun++;
        window.calibrationPush('waiting', { waiting_since: `2026-09-14T01:00:${String(window.calibrationRun).padStart(2, '0')}Z` });
      } else if (domain === 'switch' && service === 'turn_off') window.calibrationPush('idle', { idle_reason: 'cancelled' });
      else if (domain === 'button') {
        const seconds = Math.min(300, Math.round(card.hass.states[entry.entities.delay_calibration_switch].attributes.elapsed));
        const id = entry.entities.live_delay_number, old = card.hass.states[id];
        card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...old, state: String(seconds), attributes: { ...old.attributes, calibration_last_result: { seconds, completed_at: '2026-09-14T01:00:40Z', source: 'button' } } } } };
        window.calibrationPush('idle', { idle_reason: 'completed', last_result: { seconds, completed_at: '2026-09-14T01:00:40Z', source: 'button' } });
      }
    };
    card.previewData = null;
    card.hass = { ...demo.hass, connection, callService, callWS: async () => demo.preview.entries };
  }, local);
  const panel = page.locator('f1-viewing-controls');
  await panel.locator('summary').first().click();
  await panel.locator('.calibration summary').click();
  return panel;
}

test('guided lap sync selects a reference, waits for one lap and saves only on an explicit match', async ({ page }) => {
  const panel = await mount(page), guide = panel.locator('.calibration');
  expect(await page.evaluate(() => window.calibrationCalls)).toEqual([]);
  await guide.getByRole('combobox', { name: 'Calibration reference', exact: true }).selectOption('Lap sync (race/sprint)');
  await expect(guide.getByRole('combobox', { name: 'Calibration reference', exact: true })).toHaveValue('Lap sync (race/sprint)');
  await guide.getByRole('button', { name: 'Start calibration', exact: true }).click();
  await expect(guide.getByText('Waiting for the next completed lap', { exact: true })).toBeVisible();
  await expect(guide.getByRole('button', { name: 'Match TV and save delay', exact: true })).toBeDisabled();
  await expect(panel.getByLabel('Delay in seconds', { exact: true })).toBeDisabled();
  await page.evaluate(() => window.calibrationPush('running', { started_at: '2026-09-14T01:00:00Z', elapsed: 41.6, recorded_lap: 52 }));
  await expect(guide.getByText('Lap 52 completed', { exact: true })).toBeVisible();
  await expect(guide.getByText(/Match when the TV lap counter changes to 53/)).toBeVisible();
  await expect(guide.getByText('41.6 s', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.calibrationCalls.map(call => call.service))).toEqual(['select_option', 'turn_on']);
  await guide.getByRole('button', { name: 'Match TV and save delay', exact: true }).press('Enter');
  await expect(guide.getByText('Calibration saved', { exact: true })).toBeVisible();
  await expect(panel.getByText('Saved value: 42 s', { exact: true })).toBeVisible();
  await expect(guide.getByRole('button', { name: 'Start calibration', exact: true })).toBeFocused();
  expect(await page.evaluate(() => window.calibrationCalls.at(-1))).toEqual({ domain: 'button', service: 'press', data: { entity_id: 'button.f1_demo_delay_calibration_match' } });
  expect(await page.evaluate(() => window.savedConfig)).toBeUndefined();
});

test('cancel, timeout and session end keep the saved delay and never reuse an old run to match', async ({ page }) => {
  const panel = await mount(page), guide = panel.locator('.calibration');
  await guide.getByRole('button', { name: 'Start calibration', exact: true }).press('Enter');
  await expect(guide.getByRole('button', { name: 'Cancel calibration', exact: true })).toBeFocused();
  await guide.getByRole('button', { name: 'Cancel calibration', exact: true }).press('Enter');
  await expect(guide.getByText('Calibration cancelled; delay unchanged', { exact: true })).toBeVisible();
  await guide.getByRole('button', { name: 'Start calibration', exact: true }).click();
  await page.evaluate(() => {
    window.calibrationPush('running', { started_at: '2026-09-14T01:00:00Z', elapsed: 10 });
  });
  await expect(guide.getByRole('button', { name: 'Match TV and save delay', exact: true })).toBeEnabled();
  await page.evaluate(() => { window.oldCalibrationContext = window.fixtureCard.shadowRoot.querySelector('f1-viewing-controls').model.calibration.context; window.calibrationPush('idle', { idle_reason: 'timeout' }); });
  await expect(guide.getByText('Calibration timed out; delay unchanged', { exact: true })).toBeVisible();
  await guide.getByRole('button', { name: 'Start calibration', exact: true }).click();
  await page.evaluate(() => {
    window.calibrationPush('running', { started_at: '2026-09-14T01:01:00Z', elapsed: 1 });
    const card = window.fixtureCard;
    card.viewingAction({ stopPropagation() {}, detail: { action: 'calibration_match', context: window.oldCalibrationContext, connection: card.hass.connection } });
  });
  expect(await page.evaluate(() => window.calibrationCalls.some(call => call.service === 'press'))).toBe(false);
  await page.evaluate(() => window.calibrationPush('idle', { idle_reason: 'session_ended' }));
  await expect(guide.getByText('Session ended; calibration stopped without saving', { exact: true })).toBeVisible();
  await expect(panel.getByText('Saved value: 45 s', { exact: true })).toBeVisible();
});

test('failed reference selection rolls back immediately; replay, preview and spoiler masking guard the controls', async ({ page }) => {
  const panel = await mount(page), guide = panel.locator('.calibration');
  await page.evaluate(() => { window.calibrationFail = true; });
  await guide.getByRole('combobox', { name: 'Calibration reference', exact: true }).selectOption('Lap sync (race/sprint)');
  await expect(panel.getByText(/The change could not be completed/)).toBeVisible();
  await expect(guide.getByRole('combobox', { name: 'Calibration reference', exact: true })).toHaveValue('Session live');
  await page.evaluate(() => {
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].entities.replay_status;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], state: 'selected' } } };
  });
  await expect(guide.getByRole('button', { name: 'Start calibration', exact: true })).toBeDisabled();
  await expect(guide.getByText(/Stop and clear the selected replay/)).toBeVisible();
  await mount(page, 'hide');
  await page.evaluate(() => {
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].entities.live_delay_reference;
    card.hass.states[id].state = 'Lap sync (race/sprint)';
    window.calibrationPush('running', { reference: 'lap_sync', started_at: '2026-09-14T01:00:00Z', elapsed: 21.5, recorded_lap: 52 });
  });
  await expect(guide.getByText(/Reference details are hidden/)).toBeVisible();
  await expect(guide.getByText('Lap 52 completed', { exact: true })).toHaveCount(0);
  await expect(guide.getByText('21.5 s', { exact: true })).toHaveCount(0);
  await expect(guide.getByRole('button', { name: 'Match TV and save delay', exact: true })).toBeDisabled();
  await expect(guide.getByRole('button', { name: 'Cancel calibration', exact: true })).toBeEnabled();
  await page.evaluate(() => { window.fixtureCard.preview = true; });
  await expect(guide.getByRole('button', { name: 'Cancel calibration', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.calibrationCalls)).toEqual([]);
});

test('calibration remains usable on mobile, keeps ticks out of live announcements and preserves focus while measuring', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  const panel = await mount(page), guide = panel.locator('.calibration');
  await guide.getByRole('button', { name: 'Start calibration', exact: true }).press('Enter');
  await expect(guide.getByRole('button', { name: 'Cancel calibration', exact: true })).toBeFocused();
  for (const elapsed of [0, 10.2, 10.3, 10.4]) {
    await page.evaluate(elapsed => window.calibrationPush('running', { started_at: '2026-09-14T01:00:00Z', elapsed }), elapsed);
    await expect(guide.locator('.calibration-reading')).toContainText(`${elapsed} s`);
    await expect(guide.getByRole('button', { name: 'Cancel calibration', exact: true })).toBeFocused();
    await expect(guide.locator('p[aria-live]')).toHaveText('Measuring TV delay');
  }
  for (const mode of ['light', 'dark']) {
    await page.evaluate(mode => { const card = window.fixtureCard; card.setConfig({ ...card.config, appearance: { ...card.config.appearance, mode } }); }, mode);
    expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.emulateMedia({ forcedColors: 'active' });
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
  await page.evaluate(() => {
    const card = window.fixtureCard; card.hass = { ...card.hass, locale: { ...card.hass.locale, language: 'sv' } };
  });
  await expect(guide.getByRole('button', { name: 'Matcha TV och spara fördröjning', exact: true })).toBeVisible();
  await expect(guide.getByText('10,4 s', { exact: true })).toBeVisible();
  await guide.getByRole('button', { name: 'Avbryt kalibrering', exact: true }).press('Enter');
  await expect(guide.getByText('Kalibreringen avbruten; fördröjningen oförändrad', { exact: true })).toBeVisible();
});
