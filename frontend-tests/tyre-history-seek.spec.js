const { test, expect } = require('@playwright/test');

async function mount(page, direct = false) {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(direct => {
    window.mountModular({ scene: 'replay', config: { modules: [{ id: 'tyres', type: 'tyres', driver: '4', options: { content: 'history' } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const callbacks = new Map(), messages = new Map(), connection = new EventTarget();
    const keys = ['session_context', 'current_session', 'session_status', 'replay_status', 'current_tyres', 'tyre_statistics', 'driver_list'];
    if (direct) entry.data_api = { protocol_version: 1, enabled: keys };
    for (const key of keys) messages.set(key, { protocol_version: 1, entry_id: entry.entry_id, dataset: key, generation: 'initial', revision: 1,
      source: 'replay', status: 'ready', context: { qualifying_part: null }, payload: key === 'session_context'
        ? { state: 'ready', attributes: { no_spoiler: false } } : structuredClone(demo.hass.states[entry.entities[key]]) });
    connection.connected = true;
    connection.subscribeEvents = async () => () => {};
    connection.subscribeMessage = async (callback, request) => {
      if (request.type === 'f1_sensor/data/subscribe') for (const key of request.data_keys) {
        callbacks.set(key, callback); queueMicrotask(() => callback(structuredClone(messages.get(key))));
      }
      return () => {};
    };
    card.entries = [entry]; card.previewData = null;
    card.hass = { ...demo.hass, connection, callWS: async () => [entry] };
    window.tyreSeek = (position, rewind = true, generationOnly = false) => {
      const states = structuredClone(card.hass.states), attrs = states[entry.entities.current_tyres].attributes;
      if (!generationOnly) states[entry.entities.replay_player].attributes.media_position = position;
      attrs.lap_current = rewind ? 3 : 13;
      for (const driver of attrs.drivers) {
        if (rewind) {
          driver.stints = [{ ...driver.stints[0], first_lap: 1, last_lap: 3, stint_laps: 3, total_laps: 3, is_current: true }];
          driver.completed_laps = 3;
        } else {
          Object.assign(driver.stints.at(-1), { last_lap: 13, stint_laps: driver.stints.at(-1).stint_laps + 1, total_laps: driver.stints.at(-1).total_laps + 1 });
          driver.completed_laps = 13;
        }
      }
      card.hass = { ...card.hass, states };
      if (direct) for (const [key, message] of messages) {
        message.generation = rewind ? 'rewound' : 'initial'; message.revision++;
        if (key !== 'session_context') message.payload = structuredClone(states[entry.entities[key]]);
        callbacks.get(key)?.(structuredClone(message));
      }
    };
  }, direct);
  await expect(page.locator('f1-tyre-history-view .segment')).toHaveCount(2);
}

test.beforeEach(({ page }) => page.on('pageerror', error => { throw error; }));

test('a backward replay seek closes the driver detail and replaces future stints', async ({ page }) => {
  await mount(page);
  const driver = page.locator('f1-tyre-history-view [data-tyre-driver="4"]');
  await driver.getByRole('button').click();
  await expect(driver.locator('.stints tbody tr')).toHaveCount(2);
  await page.evaluate(() => window.tyreSeek(200));
  await expect(driver.locator('.segment')).toHaveCount(1);
  await expect(driver.getByRole('button')).toHaveAttribute('aria-expanded', 'false');
  await driver.getByRole('button').click();
  await expect(driver.locator('.stints tbody tr')).toHaveCount(1);
});

for (const direct of [false, true]) {
  test(`a frozen tyre history discards future stints across ${direct ? 'a direct generation replacement' : 'an entity replay rewind'}`, async ({ page }) => {
    await mount(page, direct);
    await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
    await page.evaluate(direct => window.tyreSeek(200, true, direct), direct);
    await expect(page.locator('f1-tyre-history-view')).toHaveCount(0);
    const frozenRows = await page.evaluate(() => [...window.fixtureCard.frozenModels.values()].flatMap(model => model.rows ?? []));
    expect(frozenRows).toEqual([]);
    await page.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect(page.locator('f1-tyre-history-view .segment')).toHaveCount(1);
  });
}

test('ordinary forward playback preserves a local tyre reading snapshot until resuming', async ({ page }) => {
  await mount(page);
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => window.tyreSeek(1850, false));
  await expect(page.locator('f1-tyre-history-view .lap-progress')).toHaveText('Lap 12 / 53');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(page.locator('f1-tyre-history-view .lap-progress')).toHaveText('Lap 13 / 53');
});
