const { test, expect } = require('@playwright/test');
const budgets = require('../quality/performance-budgets.json');

test('modular cards render a larger field, share streams and release resources @performance', async ({ page }, testInfo) => {
  test.skip((process.env.F1_BROWSER || 'chromium') !== 'chromium', 'Long Task API and heap diagnostics are Chromium measurements.');
  await page.goto('/frontend-tests/modular.html'); await page.waitForFunction(() => window.modularReady);
  const measurements = await page.evaluate(async () => {
    const base = '/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/';
    const [{ makeDemo }, { connectionDiagnostics }] = await Promise.all([import(base + 'demo.js'), import(base + 'connection.js')]);
    const demo = makeDemo('race'), entry = demo.preview.entries[0], fieldSize = 32;
    const state = key => demo.hass.states[entry.entities[key]], originals = state('driver_positions').attributes.drivers;
    const drivers = Array.from({ length: fieldSize }, (_, i) => ({ ...structuredClone(originals[i % originals.length]), racing_number: String(i + 1), tla: `D${i + 1}`, full_name: `Test Driver ${i + 1}`, current_position: i + 1, completed_laps: 100, sector_current_lap: 101,
      sectors: { current: { sector_1: { time: 24 + i / 100, lap: 101 } }, personal_best: {} }, laps: Object.fromEntries(Array.from({ length: 100 }, (_, lap) => [lap + 1, 81 + i / 10 + lap % 3 / 10])) }));
    state('driver_positions').attributes.drivers = drivers;
    state('driver_list').attributes.drivers = drivers.map(({ racing_number, tla, full_name, team, team_color }) => ({ racing_number, tla, full_name, team, team_color }));
    state('current_tyres').attributes.drivers = drivers.map(driver => ({ racing_number: driver.racing_number, compound_short: 'M', stint_laps: 12 }));
    const handlers = new Map(), counts = { requests: 0, subscriptions: 0, removed: 0, services: 0 };
    const connection = new EventTarget(); connection.connected = true;
    connection.subscribeEvents = async (callback, type) => { counts.subscriptions++; if (!handlers.has(type)) handlers.set(type, new Set()); handlers.get(type).add(callback); return () => { counts.removed++; handlers.get(type).delete(callback); }; };
    let hass = { ...demo.hass, connection, callService() { counts.services++; }, async callWS(query) { counts.requests++; return query.type === 'f1_sensor/entities' ? [entry] : { items: demo.preview.events }; } };
    const root = document.querySelector('#root'), frame = () => new Promise(resolve => requestAnimationFrame(() => resolve()));
    const settle = async cards => { await Promise.all(cards.map(card => card.updateComplete)); await frame(); await Promise.all(cards.flatMap(card => [...card.moduleNodes.values()].map(node => node.updateComplete))); await frame(); };
    const longTasks = []; const observer = new PerformanceObserver(list => longTasks.push(...list.getEntries().map(item => ({ start: item.startTime, duration: item.duration })))); observer.observe({ type: 'longtask', buffered: false });
    const scenarios = [
      { name: 'simple', count: 1, modules: [{ type: 'overview' }, { type: 'weather' }] },
      { name: 'detailed', count: 1, modules: [{ type: 'timing', options: { rows: fieldSize } }, { type: 'lap_chart' }, { type: 'race_control' }] },
      { name: 'ten-shared', count: 10, modules: [{ type: 'timing', options: { rows: fieldSize } }, { type: 'race_control' }] },
      { name: 'ten-retained', count: 10, modules: [{ type: 'timing', unavailable: 'retain', options: { rows: fieldSize } }, { type: 'race_control' }] },
    ], results = [];
    for (const scenario of scenarios) {
      const requestStart = counts.requests, subscriptionStart = counts.subscriptions, start = performance.now();
      const cards = Array.from({ length: scenario.count }, () => { const card = document.createElement('f1-sensor-card'); card.hass = hass; card.setConfig({ appearance: { logos: false, flags: false }, modules: scenario.modules }); root.append(card); return card; });
      await settle(cards); await settle(cards);
      const renderMs = performance.now() - start, heapBeforeUpdates = performance.memory?.usedJSHeapSize ?? null;
      const updates = [];
      for (let update = 0; update < 20; update++) {
        const previous = state('driver_positions'), updateStart = performance.now();
        hass = { ...hass, states: { ...hass.states, [entry.entities.driver_positions]: { ...previous, last_updated: new Date(Date.parse(previous.last_updated) + update * 500).toISOString(), attributes: { ...previous.attributes, drivers: drivers.map((driver, index) => ({ ...driver, gap_to_leader: index ? `+${(index + update / 100).toFixed(3)}` : 'LEADER', sectors: { ...driver.sectors, current: { sector_1: { time: 24 + index / 100 + update / 1000, lap: 101 } } } })) } } } };
        cards.forEach(card => { card.hass = hass; }); await settle(cards); updates.push(performance.now() - updateStart);
      }
      await frame();
      const end = performance.now(), diagnostics = connectionDiagnostics(connection), rowsPerCard = cards.map(card => [...card.moduleNodes.values()].filter(node => node.module.type === 'timing').map(node => node.model.rows.length));
      const heapAfterUpdates = performance.memory?.usedJSHeapSize ?? null;
      const requests = counts.requests - requestStart, subscriptions = counts.subscriptions - subscriptionStart;
      const savedModules = cards.map(card => card.savedSources.snapshots.size);
      cards.forEach(card => card.remove()); await frame();
      const remainingSnapshots = cards.map(card => card.savedSources.snapshots.size);
      results.push({ name: scenario.name, savedModules, remainingSnapshots, fieldSize, cards: scenario.count, renderMs, p95UpdateMs: updates.toSorted((a, b) => a - b)[Math.ceil(updates.length * .95) - 1], longestTask: Math.max(0, ...longTasks.filter(item => item.start + item.duration >= start && item.start <= end).map(item => item.duration)), requests, subscriptions, diagnostics, rowsPerCard, afterRemoval: connectionDiagnostics(connection), activeHandlers: [...handlers.values()].reduce((sum, set) => sum + set.size, 0), heapBeforeUpdates, heapAfterUpdates });
    }
    observer.disconnect(); return { scenarios: results, services: counts.services };
  });
  await testInfo.attach('modular-performance.json', { body: JSON.stringify(measurements, null, 2), contentType: 'application/json' });
  console.log(JSON.stringify(measurements));
  expect(measurements.services).toBe(0);
  for (const scenario of measurements.scenarios) {
    expect(scenario.renderMs, scenario.name).toBeLessThan(budgets.browser.gallery_render_ms);
    expect(scenario.longestTask, scenario.name).toBeLessThan(budgets.browser.long_task_ms);
    expect(scenario.remainingSnapshots.every(count => count === 0)).toBe(true);
    if (scenario.name === 'ten-retained') expect(scenario.savedModules).toEqual(Array(10).fill(1));
    expect(scenario.afterRemoval).toEqual({ resources: 0, consumers: 0, groups: 0 }); expect(scenario.activeHandlers).toBe(0);
    if (scenario.name !== 'simple') { expect(scenario.requests).toBe(2); expect(scenario.subscriptions).toBe(3); expect(scenario.rowsPerCard.every(rows => rows[0] === scenario.fieldSize)).toBe(true); }
  }
});
