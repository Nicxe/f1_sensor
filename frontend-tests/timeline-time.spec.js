const { test, expect } = require('@playwright/test');
const { mountRaceTrace } = require('./race-trace-fixture.cjs');

const cases = [
  { name: 'summer', utc: '2025-07-06T14:05:48Z', clock: '16:05:48', twelve: /04:05:48\s*PM/ },
  { name: 'winter', utc: '2026-11-06T19:30:19Z', clock: '20:30:19', twelve: /08:30:19\s*PM/ },
];

async function mountEvents(page, { utc, legacy = false, radio = false, ambiguous = false }) {
  await mountRaceTrace(page, { cards: 0 });
  await page.evaluate(({ utc, legacy, radio, ambiguous }) => {
    const h = window.raceTrace, id = h.entries[0].entry_id;
    h.hass.locale = { language: 'en-US', time_format: '24', time_zone: 'server' };
    h.hass.config.time_zone = 'Europe/Stockholm';
    const obs = structuredClone(h.snapshot().payload.attributes.race_trace_observation);
    obs.timing_as_of = { sequence: 90, source_time_ms: Date.parse(utc) + 1000, time_domain: 'utc' };
    obs.event_time_basis = 'utc_field';
    const event = {
      event_id: 'rc', revision: 1, sequence: 3, session_id: 'race-1', provider: 'f1_live',
      title: 'CAR 18 LAP 14 DELETED', category: 'lap_control', kind: 'lap_deleted',
      occurred_at: legacy ? utc.slice(0, -1) : utc,
      driver_numbers: [18], lap_number: 14, focus_observation: ambiguous ? null : obs,
    };
    const events = [event];
    if (radio) events.push({
      event_id: 'radio', revision: 1, sequence: 2, session_id: 'race-1', provider: 'f1_live',
      title: 'ALB team radio', category: 'radio', kind: 'team_radio_available',
      occurred_at: '2026-11-06T19:29:53.762Z', driver_numbers: [23],
    });
    Object.assign(h.analyses.get(id), {
      session_id: 'race-1', session_name: 'Practice 2', drivers: [{ driver_number: 18, tla: 'STR' }],
      timeline: { events },
    });
    const originalCall = h.hass.callWS;
    h.hass.callWS = async message => message.type === 'f1_sensor/race_control_log/get'
      ? { items: [{ event_id: 'rc', utc, message: event.title, category: 'Other' }] }
      : originalCall(message);
    h.mount({ modules: [
      { id: 'timeline', title: 'Timeline', type: 'timeline', fields: ['event_time', 'analysis_title'], options: { event_focus: true, presentation: 'table' } },
      { id: 'control', title: 'Race Control', type: 'race_control', fields: ['event_time', 'message'] },
    ] });
  }, { utc, legacy, radio, ambiguous });
}

async function profile(page, time_format, time_zone = 'server') {
  await page.evaluate(({ time_format, time_zone }) => {
    const h = window.raceTrace;
    h.cards[0].hass = { ...h.hass, locale: { ...h.hass.locale, time_format, time_zone } };
  }, { time_format, time_zone });
}

for (const timezoneId of ['UTC', 'Europe/Stockholm', 'America/New_York']) {
  test.describe(`timeline clocks with browser ${timezoneId}`, () => {
    test.use({ timezoneId });
    for (const legacy of [false, true]) {
      test(`${legacy ? 'verified older UTC' : 'canonical backend UTC'} agrees with Race Control and selected detail`, async ({ page }) => {
        for (const sample of cases) {
          await mountEvents(page, { utc: sample.utc, legacy });
          const timeline = page.locator('f1-module-view').filter({ has: page.getByRole('table', { name: 'Timeline' }) });
          const rowClock = timeline.locator('tbody time');
          const controlClock = page.locator('.event-meta time');
          await expect(rowClock).toHaveText(sample.clock);
          await expect(controlClock).toHaveText(sample.clock);
          await expect(rowClock).toHaveAttribute('datetime', sample.utc);
          await timeline.getByRole('button', { name: 'Inspect event', exact: true }).click();
          const detail = page.getByRole('region', { name: 'Selected event', exact: true });
          await expect(detail.locator('time')).toHaveText(sample.clock);
          await expect(detail.locator('time')).toHaveAttribute('datetime', sample.utc);
          await expect(detail).not.toContainText(sample.utc.slice(0, 10));

          await profile(page, '12');
          for (const clock of [rowClock, controlClock, detail.locator('time')]) await expect(clock).toHaveText(sample.twelve);
          await profile(page, '24', 'local');
          const localClock = new Intl.DateTimeFormat('en-GB', { timeZone: timezoneId, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(new Date(sample.utc));
          for (const clock of [rowClock, controlClock, detail.locator('time')]) await expect(clock).toHaveText(localClock);
          expect(await page.evaluate(() => window.raceTrace.calls.filter(Array.isArray))).toEqual([]);
        }
      });
    }

    test('mixed FP2 Race Control and radio retain chronology in both orders', async ({ page }) => {
      await mountEvents(page, { utc: '2026-11-06T19:30:19Z', legacy: true, radio: true });
      const rows = page.locator('table').getByRole('row').filter({ has: page.locator('time') });
      await expect(rows).toHaveCount(2);
      await expect(rows.nth(0)).toContainText('CAR 18 LAP 14 DELETED');
      await expect(rows.nth(0).locator('time')).toHaveText('20:30:19');
      await expect(rows.nth(1)).toContainText('ALB team radio');
      await expect(rows.nth(1).locator('time')).toHaveText('20:29:53');
      await page.evaluate(() => {
        const card = window.raceTrace.cards[0];
        card.setConfig({ ...card.config, modules: card.config.modules.map(module => module.type === 'timeline'
          ? { ...module, options: { ...module.options, order: 'oldest' } } : module) });
      });
      await expect(rows.nth(0)).toContainText('ALB team radio');
      await expect(rows.nth(1)).toContainText('CAR 18 LAP 14 DELETED');
    });
  });
}

test('older unproven timestamps remain unknown instead of using the browser timezone', async ({ page }) => {
  await mountEvents(page, { utc: '2026-11-06T19:30:19Z', legacy: true, ambiguous: true });
  const rowClock = page.locator('table tbody time');
  await expect(rowClock).toHaveText('—');
  await expect(rowClock).toHaveAttribute('datetime', '');
  await expect(page.getByRole('button', { name: 'Inspect event', exact: true })).toBeDisabled();
  await expect(page.locator('.event-meta time')).toHaveText('20:30:19');
});
