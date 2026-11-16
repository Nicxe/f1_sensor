const { test, expect } = require('@playwright/test');
const { mountRaceTrace } = require('./race-trace-fixture.cjs');

const config = { modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], presentation: 'both', event_markers: ['pit', 'vsc', 'sc', 'red_flag'] } }] };
const chart = page => page.locator('f1-series-chart');
const events = (page, index = 0) => chart(page).nth(index).evaluate(node => node.model.markers.events.map(event => [event.id, event.lap]));
const analysisSubscriptions = page => page.evaluate(() => window.raceTrace.records.filter(record => record.active && record.message?.type === 'f1_sensor/analysis/subscribe').length);

test('opt-in markers reuse one analysis subscription across cards and release it on removal', async ({ page }) => {
  await mountRaceTrace(page, { cards: 2 });
  await expect(chart(page)).toHaveCount(2);
  expect(await analysisSubscriptions(page)).toBe(0);
  await page.evaluate(config => { for (const card of window.raceTrace.cards) card.setConfig(config); }, config);
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 3]]);
  expect(await analysisSubscriptions(page)).toBe(1);
  await page.evaluate(() => window.raceTrace.cards.shift().remove());
  await expect(chart(page)).toHaveCount(1);
  expect(await analysisSubscriptions(page)).toBe(1);
  await page.evaluate(() => window.raceTrace.remove());
  await expect.poll(() => analysisSubscriptions(page)).toBe(0);
  expect(await page.evaluate(() => window.raceTrace.diagnostics().connectionListeners)).toBe(0);
});

test('analysis ahead of timing waits, then exposes only the latest correction without changing deltas', async ({ page }) => {
  await mountRaceTrace(page, { config });
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 3]]);
  const deltas = await chart(page).evaluate(node => node.model.series.map(series => series.values));
  await page.evaluate(() => window.raceTrace.sendAnalysis(message => {
    const snapshot = message.race_trace_markers, event = snapshot.events[0];
    const cursor = { ...snapshot.as_of, sequence: 110, source_time_ms: snapshot.as_of.source_time_ms + 15000 };
    snapshot.as_of = cursor; snapshot.events.push({ ...event, revision: 2, lap_number: 4, observation_cursor: cursor });
  }));
  await expect.poll(() => events(page)).toEqual([]);
  expect(await chart(page).evaluate(node => node.model.markers.status)).toBe('pending');
  expect(await chart(page).evaluate(node => node.model.series.map(series => series.values))).toEqual(deltas);
  await page.evaluate(() => window.raceTrace.send('driver_positions', message => {
    message.payload.attributes.race_trace_observation.timing_as_of = structuredClone(window.raceTrace.analyses.values().next().value.race_trace_markers.as_of);
  }));
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 4]]);
});

test('a paused view clears marker context after delay 0→30→0 while the base chart remains available', async ({ page }) => {
  await mountRaceTrace(page, { config });
  await expect.poll(() => events(page)).toHaveLength(2);
  await page.evaluate(() => { window.raceTrace.cards[0].freeze(); });
  await page.evaluate(() => window.raceTrace.send('driver_positions', message => {
    const context = message.payload.attributes.race_trace_observation.context; context.delay_epoch = 2; context.token = 'after-delay-return';
  }));
  await expect.poll(() => events(page)).toEqual([]);
  await expect(chart(page).locator('table')).toContainText('+20.500');
  await page.evaluate(() => { window.raceTrace.cards[0].freeze(); });
  await expect.poll(() => events(page)).toEqual([]);
});

test('unsupported marker metadata leaves the chart readable, and No Spoiler clears all visible details', async ({ page }) => {
  await mountRaceTrace(page, { config });
  await expect.poll(() => events(page)).toHaveLength(2);
  await page.evaluate(() => window.raceTrace.send('driver_positions', message => { delete message.payload.attributes.race_trace_observation; }));
  await expect.poll(() => events(page)).toEqual([]);
  await expect(chart(page).locator('table')).toContainText('+20.500');
  await page.evaluate(() => window.raceTrace.send('session_context', message => { message.payload.attributes.no_spoiler = true; }));
  await expect(chart(page)).toHaveCount(0);
  await expect.poll(() => analysisSubscriptions(page)).toBe(0);
});

test('entry ownership and reconnect cannot borrow another entry or retain a previous marker snapshot', async ({ page }) => {
  await mountRaceTrace(page, { config, entries: 2, cards: 2 });
  await expect.poll(() => events(page, 1)).toHaveLength(2);
  await page.evaluate(() => {
    const harness = window.raceTrace, first = harness.entries[0].entry_id, second = harness.entries[1].entry_id;
    harness.sendAnalysis(message => { message.race_trace_markers = structuredClone(harness.analyses.get(first).race_trace_markers); }, second);
  });
  await expect.poll(() => events(page, 1)).toEqual([]);
  expect(await events(page)).toHaveLength(2);
  await page.evaluate(() => window.raceTrace.disconnect());
  await expect(chart(page)).toHaveCount(0);
  await page.evaluate(() => window.raceTrace.reconnect());
  await expect(chart(page)).toHaveCount(2);
  await expect.poll(() => events(page, 1)).toEqual([]);
  expect(await events(page)).toHaveLength(2);
});

test('rewinding replaces the marker generation before any earlier lap data is shown', async ({ page }) => {
  await mountRaceTrace(page, { config });
  await expect.poll(() => events(page)).toHaveLength(2);
  await page.evaluate(() => {
    const harness = window.raceTrace;
    window.oldMarkerAnalysis = structuredClone(harness.analyses.values().next().value);
    for (const dataset of ['session_context', 'driver_positions']) harness.send(dataset, message => {
      message.generation = 'rewound'; message.source = 'replay'; message.context.replay_generation++;
      if (dataset !== 'driver_positions') return;
      const observation = message.payload.attributes.race_trace_observation;
      Object.assign(observation.context, { token: 'rewound-token', source: 'replay', source_epoch: 'rewound-source' });
      observation.timing_as_of = { sequence: 30, source_time_ms: 30000, time_domain: 'replay_offset' };
      for (const driver of message.payload.attributes.drivers) { driver.completed_laps = 2; delete driver.laps[3]; delete driver.laps[4]; }
    });
  });
  await expect.poll(() => events(page)).toEqual([]);
  await expect(chart(page).locator('table')).not.toContainText('+20.500');
  await page.evaluate(() => window.raceTrace.sendAnalysis(message => {
    const observation = window.raceTrace.snapshot().payload.attributes.race_trace_observation;
    const snapshot = message.race_trace_markers;
    snapshot.context = structuredClone(observation.context);
    snapshot.as_of = { ...observation.timing_as_of, sequence: 20, source_time_ms: 20000 };
    snapshot.events = [{ ...snapshot.events[0], context_token: observation.context.token, lap_number: 2,
      observation_cursor: { ...snapshot.as_of, sequence: 15, source_time_ms: 15000 } }];
  }));
  await expect.poll(() => events(page)).toEqual([['pit-81', 2]]);
  await page.evaluate(() => {
    for (const record of window.raceTrace.records) if (record.active && record.message?.type === 'f1_sensor/analysis/subscribe') record.callback(window.oldMarkerAnalysis);
  });
  await expect.poll(() => events(page)).toEqual([]);
  await expect(chart(page).locator('table')).toContainText('-0.500');
});


test('a late older analysis in the same context cannot revive a corrected marker', async ({ page }) => {
  await mountRaceTrace(page, { config });
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 3]]);
  await page.evaluate(() => {
    const harness = window.raceTrace;
    window.beforeMarkerCorrection = structuredClone(harness.analyses.values().next().value);
    harness.sendAnalysis(message => {
      const snapshot = message.race_trace_markers;
      const cursor = { ...snapshot.as_of, sequence: 99, source_time_ms: snapshot.as_of.source_time_ms + 4000 };
      snapshot.as_of = cursor;
      snapshot.events[0] = { ...snapshot.events[0], revision: 2, lap_number: 4, observation_cursor: cursor };
    });
    window.afterMarkerCorrection = structuredClone(harness.analyses.values().next().value);
    window.deliverMarkerSnapshot = snapshot => {
      for (const record of harness.records) if (record.active && record.message?.type === 'f1_sensor/analysis/subscribe') record.callback(structuredClone(snapshot));
    };
  });
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 4]]);
  // An unrelated token must not erase the accepted ordering boundary.
  await page.evaluate(() => {
    const wrongContext = structuredClone(window.afterMarkerCorrection);
    wrongContext.race_trace_markers.context.token = 'unrelated-context';
    window.deliverMarkerSnapshot(wrongContext);
  });
  await expect.poll(() => events(page)).toEqual([]);
  await page.evaluate(() => window.deliverMarkerSnapshot(window.beforeMarkerCorrection));
  await expect.poll(() => events(page)).toEqual([]);
  expect(await chart(page).evaluate(node => node.model.markers.status)).toBe('pending');
  await expect(chart(page).locator('table')).not.toContainText('Pit stop');
  await expect(chart(page).locator('table')).toContainText('+20.500');
  await page.evaluate(() => window.deliverMarkerSnapshot(window.afterMarkerCorrection));
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 4]]);
  await expect(chart(page).locator('tbody tr').last().locator('.event-cell')).toContainText('Pit stop · Oscar Piastri · lap 4');
  // Equal sequence is idempotent, and closing the card clears the watermark.
  await page.evaluate(() => window.deliverMarkerSnapshot(window.afterMarkerCorrection));
  await expect.poll(() => events(page)).toEqual([['vsc-start', 2], ['pit-81', 4]]);
  await page.evaluate(() => { window.removedMarkerCard = window.raceTrace.cards[0]; window.raceTrace.remove(); });
  expect(await page.evaluate(() => window.removedMarkerCard.raceTraceMarkerWatermark)).toBeNull();
});
