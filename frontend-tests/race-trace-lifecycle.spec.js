const { test, expect } = require('@playwright/test');
const { mountRaceTrace } = require('./race-trace-fixture.cjs');

const chart = page => page.locator('f1-series-chart');
const values = (page, index = 0) => chart(page).nth(index).evaluate(node => node.model.series.map(series => series.values.map(point => point.delta_ms)));

test('late older laps and zoom preserve the locked anchor, while explicit selection creates a new comparison', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(() => {
    for (const driver of window.raceTrace.snapshot().payload.attributes.drivers) { delete driver.laps[1]; delete driver.lap_metadata[1]; }
    window.raceTrace.mount();
  });
  await expect(chart(page)).toBeVisible();
  await expect(page.getByText('Zeroed after lap 2', { exact: true })).toBeVisible();
  expect(await values(page)).toEqual([[0, 0, 0], [0, 1000, 21000]]);
  await page.evaluate(() => {
    window.raceTrace.send('driver_positions', message => {
      for (const driver of message.payload.attributes.drivers) { driver.laps[1] = 90; driver.lap_metadata[1] = { association: 'confirmed', reason: null }; }
    });
    const card = window.raceTrace.cards[0], config = structuredClone(card.config);
    config.modules[0].options.start_lap = 3; config.modules[0].options.end_lap = 4; card.setConfig(config);
  });
  await expect(page.getByText('Zeroed after lap 2', { exact: true })).toBeVisible();
  expect(await values(page)).toEqual([[0, 0], [1000, 21000]]);
  await page.evaluate(() => {
    const card = window.raceTrace.cards[0], config = structuredClone(card.config);
    config.modules[0].options.reference_driver = '81'; config.modules[0].options.selected = ['4']; card.setConfig(config);
  });
  await expect(page.getByText('Zeroed after lap 1', { exact: true })).toBeVisible();
  expect(await values(page)).toEqual([[0, 0], [-500, -20500]]);
});

test('correction replaces the suffix, fills a gap and rejects an old accepted revision', async ({ page }) => {
  await mountRaceTrace(page);
  await expect(chart(page)).toBeVisible();
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
  await page.evaluate(() => window.raceTrace.send('driver_positions', message => { delete message.payload.attributes.drivers[1].laps[3]; }));
  await expect(chart(page).locator('table')).not.toContainText('+20.500');
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -500, null, null]]);
  await page.evaluate(() => window.raceTrace.send('driver_positions', message => {
    message.payload.attributes.drivers[1].laps[2] = 89.25; message.payload.attributes.drivers[1].laps[3] = 92;
  }));
  await expect(chart(page).locator('table')).toContainText('+20.250');
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -750, 250, 20250]]);
  await page.evaluate(() => {
    const old = structuredClone(window.raceTrace.snapshot()); old.revision = 1; old.payload.attributes.drivers[1].laps[4] = 999;
    for (const record of window.raceTrace.records) if (record.active && record.message?.data_keys?.includes('driver_positions')) record.callback(old);
  });
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -750, 250, 20250]]);
});

for (const transition of ['rewind', 'restart', 'session', 'delay', 'live_replay_live']) {
  test(`${transition} clears old points before the matching replacement snapshot arrives`, async ({ page }) => {
    await mountRaceTrace(page);
    await expect(chart(page).locator('table')).toContainText('+20.500');
    await page.evaluate(transition => {
      const harness = window.raceTrace;
      const change = message => {
        message.generation = 'generation-2';
        if (transition === 'session') message.context.session_id = 'race-2';
        if (transition === 'delay') message.context.delay_seconds = 90;
        if (transition === 'live_replay_live') message.source = 'replay';
        if (['rewind', 'restart'].includes(transition)) { message.source = 'replay'; message.context.replay_generation++; }
      };
      window.traceChange = change;
      harness.send('session_context', change);
    }, transition);
    await expect(chart(page)).toHaveCount(0);
    await page.evaluate(() => window.raceTrace.send('driver_positions', message => {
      window.traceChange(message);
      for (const driver of message.payload.attributes.drivers) {
        driver.completed_laps = 2; delete driver.laps[3]; delete driver.laps[4];
      }
    }));
    await expect(chart(page)).toBeVisible();
    expect(await values(page)).toEqual([[0, 0], [0, -500]]);
    await expect(chart(page).locator('table')).not.toContainText('+20.500');
    await page.evaluate(() => {
      const old = structuredClone(window.raceTrace.snapshot()); old.generation = 'generation-1'; old.revision = 1000;
      old.payload.attributes.drivers[1].laps[2] = 999;
      for (const record of window.raceTrace.records) if (record.active && record.message?.data_keys?.includes('driver_positions')) record.callback(old);
    });
    expect(await values(page)).toEqual([[0, 0], [0, -500]]);
    if (transition === 'live_replay_live') {
      await page.evaluate(() => {
        for (const key of ['session_context', 'driver_positions']) window.raceTrace.send(key, message => { message.generation = 'generation-3'; message.source = 'live'; });
      });
      await expect(chart(page)).toBeVisible();
      expect(await values(page)).toEqual([[0, 0], [0, -500]]);
    }
  });
}

test('shared driver focus preserves the reference, anchor and selected series', async ({ page }) => {
  await mountRaceTrace(page, { config: { context: { show_focus_control: true } } });
  await expect(chart(page)).toBeVisible();
  await page.getByRole('combobox', { name: 'Driver focus', exact: true }).selectOption('63');
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
  expect(await chart(page).evaluate(node => ({ reference: node.model.referenceDriver, anchor: node.model.anchorLap }))).toEqual({ reference: '4', anchor: 1 });
});

for (const hiddenBy of ['disabled', 'visibility']) for (const transition of ['protection', 'context']) {
  test(`${hiddenBy} Race Trace clears retained module and chart models before ${transition} changes`, async ({ page }) => {
    await mountRaceTrace(page);
    await expect(chart(page).locator('table')).toContainText('+20.500');
    await page.evaluate(hiddenBy => {
      const card = window.raceTrace.cards[0], config = structuredClone(card.config);
      window.retiredTraceNode = card.moduleNodes.get(config.modules[0].id);
      if (hiddenBy === 'disabled') config.modules[0].enabled = false;
      else config.modules[0].visibility = [{ condition: 'state', entity: 'input_boolean.trace_visible', state: 'on' }];
      config.modules.push({ type: 'timing', id: 'still-active' });
      card.setConfig(config);
    }, hiddenBy);
    await expect(chart(page)).toHaveCount(0);
    await page.evaluate(transition => {
      if (transition === 'protection') window.raceTrace.send('session_context', data => { data.payload.attributes.no_spoiler = true; });
      else for (const dataset of ['session_context', 'driver_positions']) window.raceTrace.send(dataset, data => {
        data.generation = 'replacement-generation'; data.context.session_id = 'race-2';
        if (dataset === 'driver_positions') for (const driver of data.payload.attributes.drivers) {
          driver.completed_laps = 1; driver.laps = { 1: 90 }; driver.lap_metadata = { 1: { association: 'confirmed', reason: null } };
        }
      });
    }, transition);
    expect(await page.evaluate(() => ({
      moduleSeries: window.retiredTraceNode.model?.series?.length ?? 0,
      chartSeries: window.retiredTraceNode.chartNode?.model?.series?.length ?? 0,
    }))).toEqual({ moduleSeries: 0, chartSeries: 0 });
    await page.evaluate(() => {
      const card = window.raceTrace.cards[0], config = structuredClone(card.config);
      config.modules[0].enabled = true; config.modules[0].visibility = []; card.setConfig(config);
    });
    if (transition === 'protection') {
      await expect(chart(page)).toHaveCount(0);
      await page.evaluate(() => window.raceTrace.send('session_context', data => { data.payload.attributes.no_spoiler = false; }));
    }
    await expect(chart(page)).toBeVisible();
    expect(await values(page)).toEqual(transition === 'protection' ? [[0, 0, 0, 0], [0, -500, 500, 20500]] : [[0], [0]]);
  });
}

test('reordering a connected Race Trace keeps its current model without waiting for a new publication', async ({ page }) => {
  await mountRaceTrace(page, { config: { modules: [
    { id: 'trace', type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], presentation: 'both' } },
    { id: 'timing', type: 'timing' },
  ] } });
  await expect(chart(page).locator('table')).toContainText('+20.500');
  await page.evaluate(() => {
    const card = window.raceTrace.cards[0], config = structuredClone(card.config);
    config.modules.reverse(); card.setConfig(config);
  });
  await expect(chart(page).locator('table')).toContainText('+20.500');
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
});

test('disabling Race Trace releases its anchor while timing keeps the shared source open', async ({ page }) => {
  await mountRaceTrace(page);
  await expect(chart(page)).toBeVisible();
  await page.evaluate(() => {
    const card = window.raceTrace.cards[0], config = structuredClone(card.config);
    config.modules[0].enabled = false;
    config.modules.push({ type: 'timing', id: 'still-active' });
    card.setConfig(config);
  });
  await expect(chart(page)).toHaveCount(0);
  expect(await page.evaluate(() => window.raceTrace.cards[0].raceTraceAnchors.size)).toBe(0);
  expect(await page.evaluate(() => window.raceTrace.records.filter(record => record.active && record.message?.data_keys?.includes('driver_positions')).length)).toBe(1);
  await page.evaluate(() => {
    const card = window.raceTrace.cards[0], config = structuredClone(card.config);
    config.modules[0].enabled = true; card.setConfig(config);
  });
  await expect(chart(page)).toBeVisible();
  expect(await values(page)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
});

test('rewind also retires a frozen chart and resuming accepts only the replacement generation', async ({ page }) => {
  await mountRaceTrace(page, { config: { context: { show_freeze_control: true } } });
  await expect(chart(page).locator('table')).toContainText('+20.500');
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => {
    for (const key of ['session_context', 'driver_positions']) window.raceTrace.send(key, message => {
      message.generation = 'rewound'; message.context.replay_generation++;
      if (key === 'driver_positions') for (const driver of message.payload.attributes.drivers) {
        driver.completed_laps = 2; delete driver.laps[3]; delete driver.laps[4];
      }
    });
  });
  await expect(chart(page)).toHaveCount(0);
  expect(await page.evaluate(() => [...window.raceTrace.cards[0].moduleNodes.values()].flatMap(node => node.chartNode?.model?.series ?? []).length)).toBe(0);
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(chart(page)).toBeVisible();
  expect(await values(page)).toEqual([[0, 0], [0, -500]]);
});

test('unknown type waits, qualifying is not applicable, and an old backend still supports old measures', async ({ page }) => {
  await mountRaceTrace(page);
  await expect(chart(page)).toBeVisible();
  for (const type of [null, 'Qualifying']) {
    await page.evaluate(type => window.raceTrace.send('driver_positions', message => { message.payload.attributes.lap_history_session_type = type; }), type);
    await expect(chart(page)).toHaveCount(0);
  }
  await page.evaluate(() => window.raceTrace.send('driver_positions', message => { message.payload.attributes.lap_history_session_type = 'Race'; }));
  await expect(chart(page)).toBeVisible();
  await page.evaluate(() => { delete window.raceTrace.entries[0].data_api.lap_history_version; window.raceTrace.cards[0].revision++; });
  await expect(chart(page)).toHaveCount(0);
  await page.evaluate(() => {
    const card = window.raceTrace.cards[0], config = structuredClone(card.config); config.modules[0].options.metric = 'lap_time'; card.setConfig(config);
  });
  await expect(chart(page)).toBeVisible();
  expect(await chart(page).evaluate(node => node.model.series[0].values.map(point => point.value))).toEqual([91, 89.5, 92, 110]);
});

for (const protection of [true, null]) {
  test(`protection ${protection} removes graph/table/details and frozen values, then recovers`, async ({ page }) => {
    await mountRaceTrace(page, { config: { context: { show_freeze_control: true } } });
    await expect(chart(page).locator('table')).toContainText('+20.500');
    await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
    await page.evaluate(protection => window.raceTrace.send('session_context', message => { message.payload.attributes.no_spoiler = protection; }), protection);
    await expect(chart(page)).toHaveCount(0);
    await expect(page.getByText(/\+20\.500/)).toHaveCount(0);
    expect(await page.evaluate(() => {
      const card = window.raceTrace.cards[0];
      return { saved: card.savedSources.snapshots.size, series: [...(card.frozenModels?.values() ?? [])].flatMap(model => model.series ?? []).length,
        detached: [...card.moduleNodes.values()].flatMap(node => node.chartNode?.model?.series ?? []).length };
    })).toEqual({ saved: 0, series: 0, detached: 0 });
    await page.evaluate(() => window.raceTrace.send('session_context', message => { message.payload.attributes.no_spoiler = false; }));
    if (await page.getByRole('button', { name: 'Resume', exact: true }).count()) await page.getByRole('button', { name: 'Resume', exact: true }).click();
    await expect(chart(page).locator('table')).toContainText('+20.500');
  });
}

for (const entryCount of [1, 2]) {
test(`${entryCount} entries and independent card references stay isolated through reconnect and cleanup`, async ({ page }) => {
  await mountRaceTrace(page, { entries: entryCount, cards: 2 });
  await expect(chart(page)).toHaveCount(2);
  await page.evaluate(() => {
    const card = window.raceTrace.cards[1], config = structuredClone(card.config);
    config.modules[0].options.reference_driver = '81'; config.modules[0].options.selected = ['4']; card.setConfig(config);
  });
  await expect(chart(page).nth(1).locator('table')).toContainText('-20.500');
  expect(await values(page, 0)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
  expect(await values(page, 1)).toEqual([[0, 0, 0, 0], [0, 500, -500, -20500]]);
  if (entryCount === 2) {
    await page.evaluate(() => window.raceTrace.send('driver_positions', data => {
      data.payload.attributes.drivers[1].laps['4'] = 120;
    }, window.raceTrace.entries[1].entry_id));
    await expect(chart(page).nth(1).locator('table')).toContainText('-30.500');
    expect(await values(page, 0)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
    expect(await values(page, 1)).toEqual([[0, 0, 0, 0], [0, 500, -500, -30500]]);
  }
  await page.evaluate(() => window.raceTrace.disconnect());
  await expect(chart(page)).toHaveCount(0);
  await page.evaluate(() => window.raceTrace.reconnect());
  await expect(chart(page)).toHaveCount(2);
  expect(await values(page, 0)).toEqual([[0, 0, 0, 0], [0, -500, 500, 20500]]);
  expect(await values(page, 1)).toEqual([[0, 0, 0, 0], [0, 500, -500, entryCount === 2 ? -30500 : -20500]]);
  await page.evaluate(() => window.raceTrace.remove());
  expect(await page.evaluate(() => window.raceTrace.diagnostics())).toMatchObject({ resources: 0, consumers: 0, activeSubscriptions: 0, connectionListeners: 0 });
  await page.evaluate(() => { window.raceTrace.mount(); window.raceTrace.mount(); });
  await expect(chart(page)).toHaveCount(2);
  const shared = await page.evaluate(() => window.raceTrace.diagnostics());
  expect(shared.resources).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.raceTrace.records.filter(record => record.active && record.message?.data_keys?.includes('driver_positions')).length)).toBe(1);
  await page.evaluate(() => window.raceTrace.remove());
  expect(await page.evaluate(() => window.raceTrace.diagnostics())).toMatchObject({ resources: 0, consumers: 0, activeSubscriptions: 0, connectionListeners: 0 });
  expect(await page.evaluate(() => window.raceTrace.calls.filter(call => Array.isArray(call) || call.type?.includes('seek')))).toEqual([]);
});

}
