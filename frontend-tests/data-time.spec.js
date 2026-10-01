const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T13:32:00Z') });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function live(page, modules, language = 'en', scene = 'race') {
  await page.evaluate(({ modules, language, scene }) => {
    window.mountModular({ config: { modules }, language, scene });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.timeRequests = []; window.timeServices = [];
    const connection = new EventTarget();
    connection.connected = true;
    connection.subscribeEvents = async () => () => {};
    card.previewData = null;
    card.hass = { ...demo.hass, connection,
      callWS: async message => { window.timeRequests.push(message.type); return demo.preview.entries; },
      callService: async (...args) => { window.timeServices.push(args); },
    };
  }, { modules, language, scene });
  await expect(page.locator('f1-module-view').first()).toBeVisible();
}

test('cards keep useful schedule content without update metadata or automatic source credits', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [
    { type: 'timing' }, { type: 'calendar' }, { type: 'weather' },
    { type: 'results' }, { type: 'archive' }, { type: 'map' }, { type: 'timeline' },
  ] } }));
  await expect(page.locator('f1-module-view')).toHaveCount(7);
  await expect(page.locator('.data-time')).toHaveCount(0);
  await expect(page.locator('f1-sensor-card')).not.toContainText(/Updated in Home Assistant|Received in this browser|Snapshot generated|Data provided by|Jolpica|Open-Meteo/);
  await expect(page.locator('.schedule time').first()).toBeVisible();
  await page.getByText('About the weather data', { exact: true }).click();
  await expect(page.locator('f1-sensor-card')).not.toContainText(/Open-Meteo|update time is shown/);
});

test('automatic weather keeps one source through disconnect and switches after the session ends', async ({ page }) => {
  await live(page, [
    { id: 'auto', type: 'weather', fields: ['temperature', 'humidity'], unavailable: 'retain', options: { content: 'automatic_conditions' } },
    { id: 'forecast', type: 'weather', fields: ['temperature'], options: { content: 'race_forecast' } },
  ]);
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    const states = { ...card.hass.states };
    states[entry.entities.session_status] = { state: 'live', attributes: {} };
    states[entry.entities.track_weather] = { state: 'live', attributes: { air_temperature: 30 } };
    states[entry.entities.weather] = { state: 'cloudy', attributes: { current_temperature: 12, current_humidity: 70, race_temperature: 24 } };
    card.hass = { ...card.hass, states };
  });
  const auto = page.locator('#module-auto'), forecast = page.locator('#module-forecast');
  await expect(auto).toContainText('30');
  await expect(auto).not.toContainText('70');
  await expect(forecast).toContainText('24');
  await page.evaluate(() => {
    window.fixtureCard.hass.connection.connected = false;
    window.fixtureCard.hass.connection.dispatchEvent(new Event('disconnected'));
  });
  await expect(auto).toContainText('Saved data');
  await expect(auto).toContainText('30');
  await expect(auto).not.toContainText('70');
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass.connection.connected = true;
    card.hass.connection.dispatchEvent(new Event('ready'));
    card.hass = { ...card.hass, states: { ...card.hass.states, [entry.entities.session_status]: { state: 'idle', attributes: {} } } };
  });
  await expect(auto).toContainText('12');
  await expect(auto).toContainText('70');
  await expect(auto).not.toContainText('Saved data');
  await expect(forecast).toContainText('24');
  expect(await page.evaluate(() => window.timeServices)).toEqual([]);
});

test('disconnect respects explain, retain and hide, then restores the same configured content', async ({ page }) => {
  await live(page, [
    { id: 'retained', type: 'timing', title: 'Retained timing', fields: ['driver', 'last_lap'], unavailable: 'retain' },
    { id: 'explained', type: 'weather', unavailable: 'explain' },
    { id: 'hidden', type: 'calendar', unavailable: 'hide' },
  ]);
  const timing = page.locator('#module-retained'), weather = page.locator('#module-explained');
  await expect(timing.locator('button.driver').first()).toContainText('LEC');
  await page.evaluate(() => {
    window.beforeTimeConfig = JSON.stringify(window.fixtureCard.config);
    window.beforeTimingNode = window.fixtureCard.shadowRoot.querySelector('#module-retained');
    window.fixtureCard.hass.connection.connected = false;
    window.fixtureCard.hass.connection.dispatchEvent(new Event('disconnected'));
  });
  await expect(page.locator('.connection-status')).toContainText('any visible values are saved snapshots');
  await expect(timing.locator('button.driver').first()).toContainText('LEC');
  await expect(weather.getByText(/Home Assistant is disconnected/)).toBeVisible();
  await expect(weather.locator('.weather-item')).toHaveCount(0);
  await expect(page.locator('#module-hidden')).toHaveCount(0);
  await page.clock.fastForward(120_000);
  await expect(timing.locator('button.driver').first()).toContainText('LEC');
  expect(await page.evaluate(() => window.timeRequests)).toEqual(['f1_sensor/entities']);
  await page.evaluate(() => {
    window.fixtureCard.hass.connection.connected = true;
    window.fixtureCard.hass.connection.dispatchEvent(new Event('ready'));
  });
  await expect(page.locator('.connection-status')).toHaveCount(0);
  await expect(page.locator('#module-hidden')).toBeVisible();
  await expect(weather.locator('.weather-item').first()).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify(window.fixtureCard.config) === window.beforeTimeConfig)).toBe(true);
  expect(await page.evaluate(() => window.fixtureCard.shadowRoot.querySelector('#module-retained') === window.beforeTimingNode)).toBe(true);
  expect(await page.evaluate(() => window.timeServices)).toEqual([]);
});

test('automatic weather freezes its source and protection removes frozen observations without hiding forecast', async ({ page }) => {
  await live(page, [
    { id: 'auto', type: 'weather', fields: ['temperature'], options: { content: 'automatic_conditions' } },
    { id: 'forecast', type: 'weather', fields: ['temperature'], options: { content: 'race_forecast' } },
  ]);
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states,
      [entry.entities.session_status]: { state: 'live', attributes: {} },
      [entry.entities.track_weather]: { state: 'live', attributes: { air_temperature: 31 } },
      [entry.entities.weather]: { state: 'cloudy', attributes: { current_temperature: 12, race_temperature: 24 } },
    } };
  });
  const auto = page.locator('#module-auto'), forecast = page.locator('#module-forecast');
  await expect(auto).toContainText('31');
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states, [entry.entities.session_status]: { state: 'idle', attributes: {} } } };
  });
  await expect(auto).toContainText('31');
  await expect(auto).not.toContainText('12');
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states,
      [entry.entities.session_status]: { state: 'live', attributes: {} },
      [entry.global_entities.no_spoiler_mode]: { state: 'unknown', attributes: {} },
    } };
  });
  await expect(auto.locator('.weather-item')).toHaveCount(0);
  await expect(auto).not.toContainText('31');
  await expect(forecast).toContainText('24');
  expect(await page.evaluate(() => window.timeServices)).toEqual([]);
});

for (const content of ['track_conditions', 'automatic_conditions']) test(`a new session cannot relabel unchanged weather in ${content}`, async ({ page }) => {
  await live(page, [
    { id: 'track', type: 'weather', fields: ['temperature'], options: { content } },
    { id: 'forecast', type: 'weather', fields: ['temperature'], options: { content: 'race_forecast' } },
  ]);
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states,
      [entry.entities.track_weather]: { state: 'live', attributes: { air_temperature: 31 } },
      [entry.entities.weather]: { state: 'cloudy', attributes: { race_temperature: 24 } },
    } };
  });
  const track = page.locator('#module-track');
  await expect(track).toContainText('31');
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states, [entry.entities.current_session]: {
      state: 'Qualifying', attributes: { active: true, start: '2026-09-14T13:00:00Z', meeting_key: 'new-meeting', meeting_name: 'New Grand Prix' },
    } } };
  });
  await expect(track.locator('.weather-item')).toHaveCount(0);
  await expect(track).toContainText('Waiting for a new track weather update');
  await expect(page.locator('#module-forecast')).toContainText('24');
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, states: structuredClone(card.hass.states) };
  });
  await expect(track.locator('.weather-item')).toHaveCount(0);
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states, [entry.entities.track_weather]: { state: 'live', attributes: { air_temperature: 32 } } } };
  });
  await expect(track).toContainText('32');
  await expect(track).not.toContainText('Waiting for a new track weather update');
});

test('frozen content stays readable while disconnect and new spoiler protection stay visible', async ({ page }) => {
  await live(page, [{ type: 'timing', fields: ['driver', 'last_lap'], unavailable: 'retain' }]);
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await expect(page.locator('button.driver').first()).toContainText('LEC');
  await page.evaluate(() => {
    window.fixtureCard.hass.connection.connected = false;
    window.fixtureCard.hass.connection.dispatchEvent(new Event('disconnected'));
  });
  await page.clock.fastForward(120_000);
  await expect(page.locator('.connection-status')).toBeVisible();
  await expect(page.locator('button.driver').first()).toContainText('LEC');
  await expect(page.getByText(/Reading snapshot/)).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { state: 'on', attributes: {} } } };
  });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(page.locator('.data-time')).toHaveCount(0);
  await expect(page.locator('button.driver')).toHaveCount(0);
  await expect(page.locator('.connection-status')).toBeVisible();
});

test('narrow Swedish status is readable with keyboard and forced colors without repeated time announcements', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await live(page, [{ type: 'timing', fields: ['driver', 'last_lap'], unavailable: 'retain' }], 'sv');
  await expect(page.locator('.data-time')).toHaveCount(0);
  await page.getByRole('button', { name: 'Frys vyn', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Fortsätt', exact: true })).toBeFocused();
  await page.evaluate(() => {
    window.fixtureCard.hass.connection.connected = false;
    window.fixtureCard.hass.connection.dispatchEvent(new Event('disconnected'));
  });
  await expect(page.locator('.connection-status')).toContainText('Frånkopplad från Home Assistant');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const normal = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(normal.violations).toEqual([]);
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  const forced = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(forced.violations).toEqual([]);
});

for (const change of ['session', 'delay', 'replay']) test(`frozen weather keeps its original context and discloses a ${change} change until resumed`, async ({ page }) => {
  await live(page, [{ id: 'track', type: 'weather', fields: ['temperature'], options: { content: 'track_conditions' } }], 'en', change === 'replay' ? 'replay' : 'race');
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    card.hass = { ...card.hass, states: { ...card.hass.states, [entry.entities.track_weather]: { state: 'live', attributes: { air_temperature: 31 } } } };
  });
  const track = page.locator('#module-track');
  await expect(track).toContainText('31');
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(change => {
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    const states = { ...card.hass.states, [entry.entities.track_weather]: { state: 'live', attributes: { air_temperature: 32 } } };
    if (change === 'session') states[entry.entities.current_session] = { state: 'Qualifying', attributes: { active: true, start: '2026-09-14T13:00:00Z', meeting_key: 'new-meeting', meeting_name: 'New Grand Prix' } };
    else if (change === 'delay') states[entry.entities.live_delay_number] = { state: '90', attributes: { min: 0, max: 300, step: 1 } };
    else {
      const player = states[entry.entities.replay_player];
      states[entry.entities.replay_player] = { ...player, attributes: { ...player.attributes, media_position: 100 } };
    }
    card.hass = { ...card.hass, states };
  }, change);
  await expect(page.locator('.frozen')).toContainText('Session or playback settings have changed');
  await expect(track).toContainText('31');
  await expect(track).toContainText('Demo Grand Prix');
  await expect(track).not.toContainText('New Grand Prix');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(page.locator('.frozen')).toHaveCount(0);
  await expect(track).toContainText('32');
  if (change === 'session') await expect(track).toContainText('New Grand Prix');
  expect(await page.evaluate(() => window.timeServices)).toEqual([]);
});
