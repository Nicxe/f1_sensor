const { test, expect } = require('@playwright/test');

const circuits = [
  ['baku', 'Baku City Circuit', '40.3725', '49.8533'],
  ['shanghai', 'Shanghai International Circuit', '31.3389', '121.22'],
  ['albert_park', 'Albert Park Grand Prix Circuit', '-37.8497', '144.968'],
  ['losail', 'Lusail International Circuit', '25.49', '51.4542'],
  ['yas_marina', 'Yas Marina Circuit', '24.4672', '54.6031'],
];
const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mockWeather(page) {
  const requests = [];
  await page.route(/^https:\/\/(api\.librewxr\.net|tile\.openstreetmap\.org)\//, async route => {
    requests.push(route.request().url());
    if (route.request().url().endsWith('/public/weather-maps.json')) {
      const now = Math.floor(Date.now() / 600000) * 600;
      await route.fulfill({ json: { host: 'https://api.librewxr.net', generated: now, radar: {
        past: [now - 600, now].map(time => ({ time, path: `/v2/radar/${time}` })),
        nowcast: [{ time: now + 600, path: `/v2/radar/${now + 600}` }],
      } } });
    } else await route.fulfill({ contentType: 'image/png', body: pixel });
  });
  return requests;
}

async function mountRadar(page, mode = 'live', options = {}) {
  await page.evaluate(({ circuits, mode, options }) => {
    const context = mode === 'pinned' ? { selection: {
      mode: 'pinned', source: 'live', season: 2026, meeting_key: 'demo-meeting', session_key: 'demo-session',
    } } : {};
    window.mountModular({ config: { context, modules: [{ type: 'radar', options }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    entry.entities.current_season = 'sensor.radar_calendar';
    demo.hass.states[entry.entities.current_season] = { state: String(circuits.length), attributes: {
      races: circuits.map(([circuitId, circuitName, lat, long]) => ({ Circuit: { circuitId, circuitName, Location: { lat, long } } })),
    } };
    demo.hass.states[entry.entities.next_race].attributes.circuit_id = 'baku';
    demo.hass.states[entry.entities.live_delay_number].state = mode === 'delay' ? '30' : '0';
    demo.hass.states[entry.entities.replay_status].state = mode === 'replay' ? 'paused' : 'idle';
    if (mode === 'spoilers') demo.hass.states[entry.global_entities.no_spoiler_mode].state = 'on';
    if (mode === 'unknown-spoilers') delete demo.hass.states[entry.global_entities.no_spoiler_mode];
    card.entries = demo.preview.entries;
    if (mode !== 'demo') card.previewData = null;
    if (mode === 'preview') card.preview = true;
    card.hass = { ...demo.hass, connection: {
      connected: true, subscribeEvents: async () => () => {}, subscribeMessage: async () => () => {},
    }, callWS: async () => demo.preview.entries };
  }, { circuits, mode, options });
  await page.evaluate(async () => { await window.fixtureCard.updateComplete; });
}

test('radar editor saves zoom, circuit selector and explanation visibility across reopening', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: { modules: [{ type: 'radar' }] } }));
  await page.getByText('Module options', { exact: true }).click();
  const zoom = page.getByRole('combobox', { name: 'Default map zoom', exact: true });
  const selector = page.getByRole('checkbox', { name: 'Show circuit selector', exact: true });
  const explanations = page.getByRole('checkbox', { name: 'Show explanations', exact: true });
  await expect(zoom).toHaveValue('13');
  await expect(zoom.locator('option')).toHaveText(['5', '6', '7', '8', '9', '10', '11', '12', '13', '14']);
  await expect(selector).toBeChecked();
  await expect(explanations).toBeChecked();
  await zoom.selectOption('14');
  await selector.uncheck();
  await explanations.uncheck();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options)).toMatchObject({ zoom: 14, show_circuit_selector: false, show_explanation: false });
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: window.savedConfig }));
  await page.getByText('Module options', { exact: true }).click();
  await expect(zoom).toHaveValue('14');
  await expect(selector).not.toBeChecked();
  await expect(explanations).not.toBeChecked();
  await expect(page.getByText('Default circuit ID', { exact: false })).toHaveCount(0);
});

test('hidden circuit selector follows the installation next race at the saved zoom', async ({ page }) => {
  const requests = await mockWeather(page);
  await mountRadar(page, 'live', { zoom: 14, show_circuit_selector: false, circuit: 'shanghai' });
  const radar = page.locator('f1-radar-view');
  await expect(radar.locator('.place')).toHaveText('Baku City Circuit');
  await expect(radar.getByRole('combobox', { name: 'Circuit', exact: true })).toHaveCount(0);
  expect(requests.some(url => url.startsWith('https://tile.openstreetmap.org/14/'))).toBe(true);
  await expect(radar.getByRole('button', { name: 'Zoom in', exact: true })).toBeDisabled();
  await page.evaluate(() => {
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.next_race].attributes.circuit_id = 'losail';
    card.hass = { ...card.hass };
  });
  await expect(radar.locator('.place')).toHaveText('Lusail International Circuit');
  await expect(radar.locator('.track-line')).toHaveAttribute('d', /^M.*L/);
  await expect(radar.getByRole('combobox', { name: 'Circuit', exact: true })).toHaveCount(0);
});

test('the modular editor adds radar and the live module can select each requested calendar circuit', async ({ page }) => {
  const requests = await mockWeather(page);
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: { modules: [] } }));
  await page.getByRole('combobox', { name: 'Add module', exact: true }).selectOption('radar');
  expect(await page.evaluate(() => window.savedConfig.modules.map(module => module.type))).toEqual(['radar']);
  await mountRadar(page);
  const radar = page.locator('f1-radar-view');
  await expect(radar.locator('.precipitation').first()).toBeVisible();
  await expect(radar.locator('#circuit option')).toHaveCount(circuits.length);
  expect(requests.some(url => /\/256\/12\//.test(url))).toBe(true);
  expect(requests.some(url => url.startsWith('https://tile.openstreetmap.org/13/'))).toBe(true);
  for (const [id, name] of circuits) {
    await radar.locator('#circuit').selectOption(id);
    await expect(radar.getByRole('group', { name: /^Precipitation map:/ })).toHaveAttribute('aria-label', new RegExp(name));
    await expect(radar.locator('.place')).toHaveText(name);
    await expect(radar.locator('.circuit-outline .track-line')).toHaveAttribute('d', /^M.*L/);
    await expect(radar.locator('.precipitation').first()).toBeVisible();
  }
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await expect(radar).toHaveCount(0);
  const afterFreeze = requests.length;
  await page.evaluate(async () => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass };
    await card.updateComplete;
  });
  expect(requests.length).toBe(afterFreeze);
});

for (const mode of ['demo', 'preview', 'spoilers', 'unknown-spoilers', 'replay', 'delay', 'pinned']) {
  test(`radar makes no external requests in ${mode} context`, async ({ page }) => {
    const requests = await mockWeather(page);
    await mountRadar(page, mode);
    const card = page.locator('f1-sensor-card');
    await expect(card.locator('f1-module-view')).toHaveCount(1);
    if (['demo', 'preview', 'replay', 'delay', 'pinned'].includes(mode)) {
      await expect(card.locator('f1-radar-view .notice')).toBeVisible();
      await expect(card.locator('f1-radar-view .precipitation')).toHaveCount(0);
    } else {
      await expect(card.locator('f1-module-view .empty')).toBeVisible();
      await expect(card.locator('f1-radar-view')).toHaveCount(0);
    }
    expect(requests).toEqual([]);
  });
}

test('current-weather opt-in during delay resets on context changes and never bypasses spoiler protection', async ({ page }) => {
  const requests = await mockWeather(page);
  await mountRadar(page, 'delay', { show_explanation: false });
  const radar = page.locator('f1-radar-view');
  const reveal = radar.getByRole('button', { name: 'Show current weather', exact: true });
  await expect(reveal).toBeVisible();
  expect(requests).toEqual([]);
  await reveal.click();
  await expect(radar.locator('.precipitation').first()).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass.states[card.entry.entities.live_delay_number].state = '60';
    card.hass = { ...card.hass };
  });
  await expect(reveal).toBeVisible();
  await expect(radar.locator('.precipitation')).toHaveCount(0);
  await reveal.click();
  await expect(radar.locator('.precipitation').first()).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass.states[card.entry.global_entities.no_spoiler_mode].state = 'on';
    card.hass = { ...card.hass };
  });
  await expect(radar).toHaveCount(0);
  await expect(page.locator('f1-module-view .empty')).toBeVisible();
  const afterProtection = requests.length;
  await page.evaluate(async () => {
    const card = window.fixtureCard;
    card.hass.states[card.entry.entities.live_delay_number].state = '0';
    card.hass = { ...card.hass };
    await card.updateComplete;
  });
  expect(requests.length).toBe(afterProtection);
});
