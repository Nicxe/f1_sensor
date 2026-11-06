const { test, expect } = require('@playwright/test');
const { mountRaceTrace } = require('./race-trace-fixture.cjs');

test('an observed event can be inspected without seeking and is cleared by protection', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(() => {
    const h = window.raceTrace, id = h.entries[0].entry_id, analysis = h.analyses.get(id);
    const obs = structuredClone(h.snapshot().payload.attributes.race_trace_observation);
    obs.timing_as_of.sequence = 90; obs.timing_as_of.source_time_ms -= 10000;
    Object.assign(analysis, { session_id: 'race-1', session_name: 'Race', drivers: [{ driver_number: 18, tla: 'STR' }], timeline: { events: [{
      event_id: 'event-1', revision: 1, session_id: 'race-1', title: 'CAR 18 LAP 14 DELETED', category: 'lap_control', occurred_at: new Date(obs.timing_as_of.source_time_ms - 1000).toISOString(), driver_numbers: [18], lap_number: 14, focus_observation: obs,
    }] } });
    h.mount({ modules: [{ type: 'timeline', options: { event_focus: true }, fields: ['analysis_title', 'incident_drivers', 'incident_lap'] }] });
  });
  await page.getByRole('button', { name: 'Inspect event' }).click();
  await expect(page.getByText('Selected event', { exact: true })).toBeVisible();
  await expect(page.getByText('CAR 18 LAP 14 DELETED').last()).toBeVisible();
  await expect(page.getByText('STR · 14 · 2027', { exact: false })).toBeVisible();
  await expect(page.getByText('Revision 1', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => window.raceTrace.calls.filter(call => Array.isArray(call)).length)).toBe(0);
  await page.evaluate(() => window.raceTrace.send('session_context', message => { message.payload.attributes.no_spoiler = true; }));
  await expect(page.getByText('Selected event', { exact: true })).toHaveCount(0);
  await expect(page.getByText('CAR 18 LAP 14 DELETED')).toHaveCount(0);
});

test('group focus is shared only by opted-in cards and retired after a context change', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(() => {
    const h = window.raceTrace, id = h.entries[0].entry_id, analysis = h.analyses.get(id);
    const obs = structuredClone(h.snapshot().payload.attributes.race_trace_observation);
    obs.timing_as_of.sequence = 90; obs.timing_as_of.source_time_ms -= 10000;
    Object.assign(analysis, { session_id: 'race-1', session_name: 'Race', drivers: [], timeline: { events: [{
      event_id: 'event-1', revision: 1, session_id: 'race-1', title: 'CAR 18 LAP 14 DELETED', category: 'lap_control', occurred_at: new Date(obs.timing_as_of.source_time_ms - 1000).toISOString(), driver_numbers: [18], lap_number: 14, focus_observation: obs,
    }] } });
    const context = { scope: 'group', group: 'f1', share: ['event_focus'] };
    h.mount({ title: 'one', context, modules: [{ type: 'timeline', options: { event_focus: true } }] });
    h.mount({ title: 'two', context, modules: [{ type: 'timeline', options: { event_focus: true } }] });
    h.mount({ title: 'isolated', context: { ...context, group: 'other' }, modules: [{ type: 'timeline', options: { event_focus: true } }] });
  });
  const cards = page.locator('f1-sensor-card');
  await cards.nth(0).getByRole('button', { name: 'Inspect event' }).click();
  await expect(cards.nth(0).getByText('Selected event', { exact: true })).toBeVisible();
  await expect(cards.nth(1).getByText('Selected event', { exact: true })).toBeVisible();
  await expect(cards.nth(2).getByText('Selected event', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.raceTrace.send('session_context', message => { message.context.delay_seconds = 30; }));
  await expect(cards.nth(0).getByText('Selected event', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.raceTrace.send('session_context', message => { message.context.delay_seconds = 0; }));
  await expect(cards.nth(0).getByText('Selected event', { exact: true })).toHaveCount(0);
});

test('a verified event inspects its lap in Race Trace without changing reference or seeking', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(() => {
    const h = window.raceTrace, analysis = h.analyses.get(h.entries[0].entry_id);
    const obs = structuredClone(h.snapshot().payload.attributes.race_trace_observation);
    obs.timing_as_of.sequence = 90; obs.timing_as_of.source_time_ms -= 10000;
    Object.assign(analysis, { session_id: 'race-1', drivers: [], timeline: { events: [{
      event_id: 'event-1', revision: 1, session_id: 'race-1', title: 'CAR 18 LAP 3 DELETED', category: 'lap_control',
      occurred_at: new Date(obs.timing_as_of.source_time_ms - 1000).toISOString(), driver_numbers: [18], lap_number: 3, focus_observation: obs,
    }] } });
    h.mount({ modules: [
      { type: 'timeline', options: { event_focus: true } },
      { type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], presentation: 'both' } },
    ] });
  });
  await page.getByRole('button', { name: 'Inspect event' }).click();
  await expect(page.getByText('Lap 3 · cumulative difference', { exact: true })).toBeVisible();
  await expect(page.locator('f1-series-chart')).toContainText('Lando Norris');
  expect(await page.evaluate(() => window.raceTrace.calls.filter(call => Array.isArray(call)).length)).toBe(0);
});

test('an older correction cannot return after clearing and reselecting an event', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(() => {
    const h = window.raceTrace, analysis = h.analyses.get(h.entries[0].entry_id);
    const obs = structuredClone(h.snapshot().payload.attributes.race_trace_observation);
    obs.timing_as_of.sequence = 90; obs.timing_as_of.source_time_ms -= 10000;
    Object.assign(analysis, { session_id: 'race-1', drivers: [], timeline: { events: [{
      event_id: 'event-1', revision: 2, session_id: 'race-1', title: 'CORRECTED EVENT', category: 'lap_control',
      occurred_at: new Date(obs.timing_as_of.source_time_ms - 1000).toISOString(), driver_numbers: [18], lap_number: 3, focus_observation: obs,
    }] } });
    h.mount({ modules: [{ type: 'timeline', options: { event_focus: true } }] });
  });
  await page.getByRole('button', { name: 'Inspect event' }).click();
  await expect(page.getByText('Revision 2', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Clear selected event' }).click();
  await page.evaluate(() => window.raceTrace.sendAnalysis(snapshot => {
    snapshot.timeline.events[0].revision = 1;
    snapshot.timeline.events[0].title = 'OLDER EVENT';
  }));
  await expect(page.getByText('OLDER EVENT')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect event' })).toBeDisabled();
  await page.evaluate(() => window.raceTrace.sendAnalysis(snapshot => {
    snapshot.timeline.events[0].revision = 2;
    snapshot.timeline.events[0].title = 'CONFLICTING EVENT';
  }));
  await expect(page.getByText('CONFLICTING EVENT')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Inspect event' })).toBeDisabled();
  await expect(page.getByText('Selected event', { exact: true })).toHaveCount(0);
});

test('a verified track marker can select its matching timeline event and reference lap', async ({ page }) => {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(() => {
    const h = window.raceTrace, analysis = h.analyses.get(h.entries[0].entry_id);
    const marker = analysis.race_trace_markers.events.find(event => event.event_id === 'vsc-start');
    const obs = structuredClone(h.snapshot().payload.attributes.race_trace_observation);
    obs.timing_as_of = structuredClone(marker.observation_cursor); obs.event_time_basis = 'single_frame';
    Object.assign(analysis, { session_id: 'race-1', drivers: [], timeline: { events: [{
      event_id: marker.event_id, revision: 1, session_id: 'race-1', title: 'VIRTUAL SAFETY CAR',
      category: 'track_status', kind: 'track_status_changed', occurred_at: null, driver_numbers: [], lap_number: null,
      focus_observation: obs,
    }] } });
    h.mount({ modules: [
      { type: 'timeline', options: { event_focus: true } },
      { type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], event_markers: ['vsc'], presentation: 'both' } },
    ] });
  });
  await page.locator('f1-series-chart').getByRole('button', { name: /Virtual Safety Car/ }).first().click();
  await expect(page.getByText('Selected event', { exact: true })).toBeVisible();
  await expect(page.getByText('Lap 2 · cumulative difference', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.raceTrace.calls.filter(call => Array.isArray(call)).length)).toBe(0);
});
