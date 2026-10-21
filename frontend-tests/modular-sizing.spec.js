const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mountSections(page, { preset = 'session', config, savedRows = 2, width = 980, rowHeight = 56, rowGap = 8, waiting = false } = {}) {
  await page.evaluate(({ preset, config, savedRows, width, rowHeight, rowGap, waiting }) => {
    const value = window.mountModular({ preset, config });
    const card = window.fixtureCard;
    card.layout = 'grid';
    if (waiting) card.previewData = { ...card.previewData, entries: [] };
    card.setConfig({ ...value, grid_options: { columns: 12, ...(savedRows === null ? {} : { rows: savedRows }) } });
    const root = document.querySelector('#root');
    const section = document.createElement('section');
    section.id = 'sizing-section';
    section.style.cssText = `width:${width}px;max-width:100%;`;
    section.style.setProperty('--row-height', typeof rowHeight === 'number' ? `${rowHeight}px` : rowHeight);
    section.style.setProperty('--row-gap', typeof rowGap === 'number' ? `${rowGap}px` : rowGap);
    const grid = document.createElement('div');
    grid.id = 'sizing-grid';
    grid.style.cssText = 'display:grid;grid-template-columns:repeat(12,minmax(0,1fr));grid-auto-rows:auto;gap:var(--row-gap) 8px;';
    const slot = document.createElement('div');
    slot.id = 'sizing-slot';
    slot.style.minWidth = '0';
    const next = document.createElement('div');
    next.id = 'sizing-next-card';
    next.textContent = 'Next card';
    next.style.cssText = 'grid-column:span 12;height:56px;';
    const add = document.createElement('button');
    add.id = 'sizing-add-card';
    add.textContent = 'Add card';
    add.style.cssText = 'grid-column:span 12;height:56px;';
    const nextSection = document.createElement('section');
    nextSection.id = 'sizing-next-section';
    nextSection.textContent = 'New section';
    nextSection.style.cssText = 'height:56px;margin-top:24px;';
    slot.append(card);
    grid.append(slot, next, add);
    section.append(grid);
    root.replaceChildren(section, nextSection);

    window.sizingEvents = { updated: 0, resize: 0 };
    // Home Assistant merges saved grid_options over the element defaults,
    // clamps numeric rows to min_rows, and gives that card a fixed grid height.
    // Auto rows instead retain the content's intrinsic height.
    window.applySizingGrid = () => {
      const options = { ...card.getGridOptions(), ...card.config.grid_options };
      const rows = typeof options.rows === 'number' ? Math.max(options.rows, options.min_rows ?? 1) : null;
      slot.style.gridColumn = `span ${Math.min(12, options.columns)}`;
      slot.style.gridRow = rows === null ? '' : `span ${rows}`;
      slot.style.height = rows === null ? '' : `calc(${rows} * (var(--row-height) + var(--row-gap)) - var(--row-gap))`;
    };
    card.addEventListener('card-updated', () => { window.sizingEvents.updated++; window.applySizingGrid(); });
    card.addEventListener('iron-resize', () => { window.sizingEvents.resize++; });
    window.applySizingGrid();
    window.sizingGeometry = () => {
      const bounds = card.shadowRoot.querySelector('ha-card').getBoundingClientRect();
      const slotBounds = slot.getBoundingClientRect();
      return {
        cardHeight: bounds.height,
        slotHeight: slotBounds.height,
        nextClearance: next.getBoundingClientRect().top - bounds.bottom,
        addClearance: add.getBoundingClientRect().top - bounds.bottom,
        sectionClearance: nextSection.getBoundingClientRect().top - bounds.bottom,
        options: card.getGridOptions(),
      };
    };
  }, { preset, config, savedRows, width, rowHeight, rowGap, waiting });
  await expect(page.locator('f1-sensor-card ha-card')).toBeVisible();
}

async function expectContained(page, maxGap = Infinity) {
  let size;
  await expect.poll(async () => {
    // getCardSize awaits Lit rendering. Measure the DOM in that same browser
    // observation. Containment and the themed row gap must pass together;
    // return that accepted snapshot instead of taking another measurement.
    size = await page.evaluate(async () => ({
      reportedSize: await window.fixtureCard.getCardSize(),
      ...window.sizingGeometry(),
    }));
    const gap = size.slotHeight - size.cardHeight;
    return {
      contained: Math.min(gap, size.nextClearance, size.addClearance, size.sectionClearance) >= -1,
      withinRow: gap < maxGap,
    };
  }).toEqual({ contained: true, withinRow: true });
  return size;
}

async function settleFrames(page, count = 12) {
  await page.evaluate(async count => {
    await document.fonts.ready;
    for (let frame = 0; frame < count; frame++) await new Promise(requestAnimationFrame);
  }, count);
}

test('column layout keeps later section cards below the content after reflow and visibility changes', async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 1000 });
  await mountSections(page, { width: 1100, config: { layout: 'columns', columns: 3, modules: [
    { id: 'timing', type: 'timing', column_span: 2 },
    { id: 'weather', type: 'weather' },
    { id: 'control', type: 'race_control', column_span: 'full' },
  ] } });
  const wide = await expectContained(page);
  await page.locator('#sizing-section').evaluate(section => { section.style.width = '360px'; });
  await expect.poll(async () => (await page.evaluate(() => window.sizingGeometry())).cardHeight).toBeGreaterThan(wide.cardHeight);
  const narrow = await expectContained(page);
  expect(narrow.slotHeight).toBeGreaterThan(wide.slotHeight);
  await page.evaluate(() => window.fixtureCard.setConfig({ ...window.fixtureCard.config, modules: window.fixtureCard.config.modules.map(module => ({ ...module, enabled: module.id !== 'timing' })) }));
  await expect.poll(async () => (await page.evaluate(() => window.sizingGeometry())).slotHeight).toBeLessThan(narrow.slotHeight);
  await expectContained(page);
  await settleFrames(page);
  const events = await page.evaluate(() => ({ ...window.sizingEvents }));
  await settleFrames(page);
  expect(await page.evaluate(() => window.sizingEvents)).toEqual(events);
});

test('saved two-row sections contain every modular preset and the next editing controls', async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 1000 });
  for (const preset of ['weekend', 'weather', 'session', 'driver', 'results', 'custom']) {
    await mountSections(page, { preset });
    if (preset === 'results') await expect(page.locator('f1-series-chart svg.plot')).toBeVisible();
    await settleFrames(page, 3);
    const size = await expectContained(page, 128);
    expect(size.options.rows).toBeUndefined();
    expect(size.slotHeight - size.cardHeight).toBeLessThan(128);
  }
});

test('opening and closing chart data moves later cards and sections with the actual card height', async ({ page }) => {
  await mountSections(page, { config: { modules: [{ type: 'progression' }] } });
  await expect(page.locator('f1-series-chart svg.plot')).toBeVisible();
  const closed = await expectContained(page);
  await page.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(page.locator('f1-series-chart tbody tr')).toHaveCount(4);
  const opened = await expectContained(page);
  expect(opened.cardHeight).toBeGreaterThan(closed.cardHeight + 100);
  expect(opened.slotHeight).toBeGreaterThan(closed.slotHeight);
  expect(opened.reportedSize).toBe(Math.ceil(opened.cardHeight / 50));
  await page.getByRole('button', { name: 'Hide data table', exact: true }).click();
  await expect.poll(async () => (await page.evaluate(() => window.sizingGeometry())).slotHeight).toBeLessThan(opened.slotHeight);
  const collapsed = await expectContained(page);
  expect(collapsed.cardHeight).toBeCloseTo(closed.cardHeight, 0);
});

test('container wrapping resizes the occupied section without requiring a viewport resize', async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 1000 });
  await mountSections(page, { config: { title: 'A detailed Formula One championship and race weekend overview', modules: [{ type: 'overview' }, { type: 'calendar' }, { type: 'documents' }] } });
  const wide = await expectContained(page);
  await page.locator('#sizing-section').evaluate(section => { section.style.width = '340px'; });
  await expect.poll(async () => (await page.evaluate(() => window.sizingGeometry())).cardHeight).toBeGreaterThan(wide.cardHeight + 50);
  const narrow = await expectContained(page);
  expect(narrow.slotHeight).toBeGreaterThan(wide.slotHeight);
  await page.locator('#sizing-section').evaluate(section => { section.style.width = '980px'; });
  await expect.poll(async () => (await page.evaluate(() => window.sizingGeometry())).slotHeight).toBeLessThan(narrow.slotHeight);
  await expectContained(page);
});

test('automatic height and explicit larger rows preserve content and report the rendered masonry size', async ({ page }) => {
  await mountSections(page, { preset: 'results', savedRows: null });
  await expect(page.locator('f1-series-chart svg.plot')).toBeVisible();
  const automatic = await expectContained(page);
  expect(automatic.options.rows).toBeUndefined();
  expect(automatic.slotHeight).toBeCloseTo(automatic.cardHeight, 0);
  expect(automatic.reportedSize).toBe(Math.ceil(automatic.cardHeight / 50));

  await mountSections(page, { preset: 'session', savedRows: 2, rowHeight: 'calc(5rem + 16px)', rowGap: '.75rem' });
  const themed = await expectContained(page, 108);
  expect(themed.slotHeight - themed.cardHeight).toBeLessThan(108);
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, grid_options: { columns: 12, rows: 30 } });
    window.applySizingGrid();
  });
  const larger = await expectContained(page);
  expect(larger.slotHeight).toBe(30 * 108 - 12);
  expect(larger.reportedSize).toBe(Math.ceil(larger.cardHeight / 50));
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, grid_options: { columns: 12, rows: 2 } });
    window.applySizingGrid();
    const section = document.querySelector('#sizing-section');
    section.style.setProperty('--row-height', 'calc(2rem + 12px)');
    section.style.setProperty('--row-gap', '.5rem');
  });
  const smallerTheme = await expectContained(page, 52);
  expect(smallerTheme.cardHeight).toBeCloseTo(themed.cardHeight, 0);
  expect(smallerTheme.slotHeight - smallerTheme.cardHeight).toBeLessThan(52);
  await page.evaluate(async () => {
    const section = document.querySelector('#sizing-section');
    section.style.fontSize = '12px';
    section.style.setProperty('--row-height', '3em');
    section.style.setProperty('--row-gap', '8px');
    window.fixtureCard.requestUpdate();
    await window.fixtureCard.updateComplete;
  });
  const relativeTheme = await expectContained(page, 44);
  expect(relativeTheme.slotHeight - relativeTheme.cardHeight).toBeLessThan(44);
  expect(relativeTheme.cardHeight).toBeCloseTo(themed.cardHeight, 0);
});

test('masonry geometry and reported size use the same render after a delayed chart resize', async ({ page }) => {
  await page.evaluate(() => {
    const NativeResizeObserver = window.ResizeObserver;
    window.heldChartResizes = [];
    window.holdChartResizes = true;
    window.ResizeObserver = class extends NativeResizeObserver {
      constructor(callback) {
        super((entries, observer) => {
          if (window.holdChartResizes && entries.some(entry => entry.target.localName === 'f1-series-chart')) {
            window.heldChartResizes.push(() => callback(entries, observer));
          } else callback(entries, observer);
        });
      }
    };
  });
  await mountSections(page, { preset: 'results', savedRows: null });
  await expect(page.locator('f1-series-chart svg.plot')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.heldChartResizes.length)).toBeGreaterThan(0);
  const initialHeight = await page.evaluate(() => window.sizingGeometry().cardHeight);
  await page.evaluate(() => {
    const card = window.fixtureCard;
    const getCardSize = card.getCardSize.bind(card);
    // Release the real observer callbacks at the async sizing boundary. A
    // geometry snapshot taken before that boundary is deliberately obsolete.
    card.getCardSize = async () => {
      if (window.holdChartResizes) {
        window.holdChartResizes = false;
        for (const deliver of window.heldChartResizes.splice(0)) deliver();
        await Promise.all([...card.shadowRoot.querySelectorAll('f1-series-chart')].map(chart => chart.updateComplete));
      }
      return getCardSize();
    };
  });
  const size = await expectContained(page);
  expect(size.reportedSize).toBe(Math.ceil(size.cardHeight / 50));
  expect(size.cardHeight).not.toBe(initialHeight);
});

test('size events settle, stop after disconnection, and resume when the card is reattached', async ({ page }) => {
  await mountSections(page, { preset: 'weather' });
  await expectContained(page);
  await settleFrames(page);
  const initial = await page.evaluate(() => ({ ...window.sizingEvents }));
  expect(initial.updated).toBeGreaterThan(0);
  expect(initial.resize).toBeGreaterThan(0);
  await page.evaluate(() => { window.fixtureCard.hass = { ...window.fixtureCard.hass }; });
  await settleFrames(page);
  expect(await page.evaluate(() => window.sizingEvents)).toEqual(initial);

  await page.evaluate(() => {
    window.fixtureCard.remove();
    window.fixtureCard.shadowRoot.querySelector('ha-card').style.paddingBottom = '240px';
  });
  await settleFrames(page);
  expect(await page.evaluate(() => window.sizingEvents)).toEqual(initial);
  await page.evaluate(() => document.querySelector('#sizing-slot').append(window.fixtureCard));
  await expect.poll(() => page.evaluate(() => window.sizingEvents.updated)).toBeGreaterThan(initial.updated);
  await expectContained(page);
  await settleFrames(page);
  const reconnected = await page.evaluate(() => ({ ...window.sizingEvents }));
  expect(reconnected.resize).toBeGreaterThan(initial.resize);
  await settleFrames(page);
  expect(await page.evaluate(() => window.sizingEvents)).toEqual(reconnected);
});

test('entry discovery and loss preserve accurate themed sizing when the card template changes', async ({ page }) => {
  await mountSections(page, { config: { modules: [{ type: 'progression' }] }, rowHeight: 'calc(2rem + 12px)', rowGap: '.5rem', waiting: true });
  await expect(page.getByText('Waiting for F1 Sensor…', { exact: true })).toBeVisible();
  const waiting = await expectContained(page, 52);
  expect(waiting.slotHeight - waiting.cardHeight).toBeLessThan(52);

  for (let discovery = 0; discovery < 2; discovery++) {
    await page.evaluate(() => { window.fixtureCard.previewData = window.fixtureDemo.preview; });
    await expect(page.locator('f1-series-chart svg.plot')).toBeVisible();
    const populated = await expectContained(page, 52);
    expect(populated.slotHeight - populated.cardHeight).toBeLessThan(52);
    expect(populated.cardHeight).toBeGreaterThan(waiting.cardHeight + 200);

    await page.locator('#sizing-section').evaluate(section => {
      section.style.setProperty('--row-height', 'calc(5rem + 16px)');
      section.style.setProperty('--row-gap', '.75rem');
    });
    await expectContained(page, 108);

    await page.evaluate(() => { window.fixtureCard.previewData = { ...window.fixtureDemo.preview, entries: [] }; });
    await expect(page.getByText('Waiting for F1 Sensor…', { exact: true })).toBeVisible();
    await page.locator('#sizing-section').evaluate(section => {
      section.style.setProperty('--row-height', 'calc(2rem + 12px)');
      section.style.setProperty('--row-gap', '.5rem');
    });
    await expect.poll(async () => (await page.evaluate(() => window.sizingGeometry())).slotHeight).toBeLessThan(populated.slotHeight);
    const compact = await expectContained(page, 52);
    expect(compact.slotHeight - compact.cardHeight).toBeLessThan(52);
  }
});
