const { test, expect } = require('@playwright/test');

test('a standalone map receives direct timing and hides eliminated cars once they are in the pits', async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.clock.install({ time: new Date('2026-10-31T22:00:00Z') });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(async () => {
    const catalog = await (await fetch('/frontend-tests/fixtures/map-catalog-2026.json')).json();
    window.mountModular({ scene: 'qualifying', config: { modules: [{ type: 'map' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    const entry = structuredClone(demo.preview.entries[0]);
    entry.data_api = { enabled: ['driver_positions'] };
    delete entry.entities.driver_positions;
    card.entries = [entry]; card.previewData = null;
    window.mapVisibilityRequests = []; window.mapVisibilityStops = [];
    window.mapVisibilitySnapshot = {
      ...demo.preview.map, track: catalog.circuits.find(circuit => circuit.circuit_key === '65').snapshot.track,
      session: { session_key: 'mexico-qualifying', session_name: 'Qualifying' },
      drivers: [
        { racing_number: '14', tla: 'ALO', x: -1180, y: -110, status: 'OnTrack', stale: false },
        { racing_number: '16', tla: 'LEC', x: 4000, y: -3000, status: 'OnTrack', stale: false },
      ],
    };
    let revision = 0;
    window.pushMapVisibilityTiming = driver => window.mapVisibilityTimingCallback({
      entry_id: entry.entry_id, dataset: 'driver_positions', protocol_version: 1,
      generation: 'mexico-qualifying', revision: ++revision, source: 'live', status: 'ready',
      payload: { state: 2, attributes: { drivers: [driver, { racing_number: '16', status: 'on_track' }] } },
    });
    card.hass = {
      ...demo.hass,
      connection: {
        subscribeEvents: async () => () => {},
        subscribeMessage: async (callback, message) => {
          window.mapVisibilityRequests.push(message);
          if (message.type === 'f1_sensor/data/subscribe') {
            window.mapVisibilityTimingCallback = callback;
            window.pushMapVisibilityTiming({ racing_number: '14', tla: 'ALO', stopped: true, retired: false, status: 'stopped' });
          } else if (message.type === 'f1_sensor/track_map/subscribe') {
            window.mapVisibilityPositionCallback = callback;
            callback({ protocol_version: 2, type: 'snapshot', entry_id: entry.entry_id,
              sequence: 1, geometry_revision: 1, snapshot: window.mapVisibilitySnapshot });
          }
          return () => window.mapVisibilityStops.push(message.type);
        },
      },
      callWS: async () => [entry],
    };
  });

  const map = page.locator('f1-track-map-view');
  await expect.poll(() => page.evaluate(() => window.mapVisibilityRequests
    .filter(message => message.type === 'f1_sensor/data/subscribe').flatMap(message => message.data_keys))).toContain('driver_positions');
  await expect(map.locator('.marker text')).toHaveText(['LEC']);

  await page.evaluate(() => window.pushMapVisibilityTiming({
    racing_number: '14', tla: 'ALO', in_pit: true, stopped: false, retired: false,
    q1_knocked_out: true, status: 'pit_in',
  }));
  await expect(map.locator('.marker text')).toHaveText(['LEC']);

  await page.evaluate(() => window.pushMapVisibilityTiming({
    racing_number: '14', tla: 'ALO', in_pit: true, stopped: false, retired: false,
    q1_knocked_out: false, q2_knocked_out: false, status: 'pit_in',
  }));
  await expect(map.locator('.marker text')).toHaveText(['ALO', 'LEC']);

  await page.evaluate(() => window.pushMapVisibilityTiming({
    racing_number: '14', tla: 'ALO', in_pit: false, q2_knocked_out: true, status: 'on_track',
  }));
  await expect(map.locator('.marker text')).toHaveText(['ALO', 'LEC']);
  await page.evaluate(() => window.pushMapVisibilityTiming({
    racing_number: '14', tla: 'ALO', in_pit: true, q2_knocked_out: true, status: 'pit_in',
  }));
  await expect(map.locator('.marker text')).toHaveText(['LEC']);

  await page.evaluate(() => window.fixtureCard.remove());
  await expect.poll(() => page.evaluate(() => window.mapVisibilityStops
    .filter(type => type === 'f1_sensor/data/subscribe'))).toHaveLength(1);
  await expect.poll(() => page.evaluate(() => window.mapVisibilityStops
    .filter(type => type === 'f1_sensor/track_map/subscribe'))).toHaveLength(1);
});

for (const entityState of ['unknown', 'unavailable']) {
  test(`a standalone map respects driver attributes when the fallback sensor state is ${entityState}`, async ({ page }) => {
    page.on('pageerror', error => { throw error; });
    await page.clock.install({ time: new Date('2026-10-31T22:00:00Z') });
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.evaluate(state => {
      window.mountModular({ scene: 'qualifying', config: { modules: [{ type: 'map' }] } });
      const card = window.fixtureCard, demo = window.fixtureDemo;
      const entry = structuredClone(demo.preview.entries[0]);
      delete entry.data_api;
      entry.entities.driver_positions = 'sensor.map_visibility_timing';
      card.entries = [entry]; card.previewData = null;
      const states = { ...demo.hass.states, [entry.entities.driver_positions]: {
        state, attributes: { drivers: [{ racing_number: '14', tla: 'ALO', stopped: true }] },
      } };
      window.updateFallbackTiming = driver => {
        card.hass = { ...card.hass, states: { ...card.hass.states, [entry.entities.driver_positions]: {
          state, attributes: { drivers: [driver] },
        } } };
      };
      card.hass = {
        ...demo.hass, states,
        connection: {
          subscribeEvents: async () => () => {},
          subscribeMessage: async (callback, message) => {
            if (message.type === 'f1_sensor/track_map/subscribe') callback({
              protocol_version: 2, type: 'snapshot', entry_id: entry.entry_id,
              sequence: 1, geometry_revision: 1, snapshot: { ...demo.preview.map, drivers: [
                { racing_number: '14', tla: 'ALO', x: 0, y: 60, status: 'OnTrack', stale: false },
                { racing_number: '16', tla: 'LEC', x: 70, y: 0, status: 'OnTrack', stale: false },
              ] },
            });
            return () => {};
          },
        },
        callWS: async () => [entry],
      };
    }, entityState);
    const map = page.locator('f1-track-map-view');
    const inactiveLabels = entityState === 'unknown' ? ['LEC'] : ['ALO', 'LEC'];
    await expect(map.locator('.marker text')).toHaveText(inactiveLabels);

    await page.evaluate(() => window.updateFallbackTiming({
      racing_number: '14', tla: 'ALO', in_pit: true, stopped: false, retired: false,
      q1_knocked_out: true, status: 'pit_in',
    }));
    await expect(map.locator('.marker text')).toHaveText(inactiveLabels);

    await page.evaluate(() => window.updateFallbackTiming({
      racing_number: '14', tla: 'ALO', in_pit: true, stopped: false, retired: false,
      q1_knocked_out: false, q2_knocked_out: false, status: 'pit_in',
    }));
    await expect(map.locator('.marker text')).toHaveText(['ALO', 'LEC']);
  });
}
