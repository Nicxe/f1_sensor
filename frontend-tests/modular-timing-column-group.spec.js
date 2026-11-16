const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.locator('main').evaluate(node => { node.style.maxWidth = 'none'; });
});

const timing = page => page.locator('f1-module-view').first();
const drivers = view => view.locator('tr[data-driver]');

async function mount(page, { fields, options = {}, appearance = {} }) {
  await page.evaluate(({ fields, options, appearance }) => window.mountModular({ config: {
    appearance: { presentation: 'compact', font: 'system', logos: false, ...appearance },
    modules: [{ type: 'timing', fields, detail_fields: ['tyre_age'], options: {
      profile: 'custom', show_time_context: false, show_explanation: false, ...options,
    } }],
  } }), { fields, options, appearance });
  await expect(drivers(timing(page))).toHaveCount(5);
}

async function geometry(view) {
  return drivers(view).evaluateAll(rows => {
    const content = cell => {
      const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      const boxes = [];
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (!node.textContent.trim() || node.parentElement.closest('.sr,[hidden]')) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        boxes.push(...[...range.getClientRects()].filter(box => box.width && box.height));
      }
      return boxes.length ? { left: Math.min(...boxes.map(box => box.left)), right: Math.max(...boxes.map(box => box.right)) } : null;
    };
    return rows.map(row => Object.fromEntries([...row.querySelectorAll('td[data-field]')].map(cell => {
      const rect = cell.getBoundingClientRect(), style = getComputedStyle(cell), text = content(cell);
      return [cell.dataset.field, {
        left: rect.left, right: rect.right, width: rect.width,
        padding: parseFloat(style.paddingLeft) + parseFloat(style.paddingRight),
        inset: text ? text.left - rect.left - parseFloat(style.paddingLeft) : null,
        content: text, driverWidth: cell.querySelector('.driver')?.getBoundingClientRect().width,
      }];
    })));
  });
}

async function expectCloseDriverGap(view, gapField) {
  const rows = await geometry(view);
  const driverWidth = Math.max(...rows.map(row => row.driver.driverWidth));
  expect(rows[0].driver.width).toBeLessThanOrEqual(driverWidth + rows[0].driver.padding + 2);
  // The widest driver label should meet the next value after cell padding,
  // rather than an expanding share of the dashboard's unused width.
  const smallestGap = Math.min(...rows.filter(row => row[gapField].content).map(row => row[gapField].content.left - row.driver.content.right));
  expect(smallestGap).toBeGreaterThanOrEqual(0);
  expect(smallestGap).toBeLessThanOrEqual(32);
  for (const row of rows.filter(row => row[gapField].content)) expect(row[gapField].inset).toBeLessThanOrEqual(1);
}

for (const { width, position, display, gapFields } of [
  { width: 1100, position: 'position_with_change', display: 'combined', gapFields: ['timing_gap'] },
  { width: 1600, position: 'position', display: 'separate', gapFields: ['interval', 'gap'] },
]) {
  test(`compact Timing keeps identity and ${display} gaps together at ${width}px while timing columns fill the table`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mount(page, {
      fields: [position, 'driver', 'interval', 'gap', 'sector_1_with_minisectors', 'sector_2', 'sector_3', 'last_lap', 'best_lap', 'tyre'],
      options: { gap_display: display },
    });
    const view = timing(page);
    await expectCloseDriverGap(view, gapFields[0]);
    for (const field of [position, 'driver', ...gapFields]) {
      for (const cell of await view.locator(`[data-field="${field}"]`).all()) {
        expect(['left', 'start']).toContain(await cell.evaluate(node => getComputedStyle(node).textAlign));
      }
    }
    await expect(view.locator('th[data-field="last_lap"]')).toHaveCSS('text-align', 'right');
    await expect(drivers(view).first().locator('[data-field="sector_2"]')).toHaveCSS('text-align', 'right');
    const box = await view.locator('.table-scroll').evaluate(node => ({
      available: node.clientWidth, table: node.querySelector('table').getBoundingClientRect().width,
    }));
    expect(Math.abs(box.table - box.available)).toBeLessThanOrEqual(1);
    await expect(view.locator('table')).toHaveCount(1);
    await expect(view.locator('thead th[scope="col"]')).toHaveCount(display === 'combined' ? 9 : 10);
  });
}

test('compact grouping follows selected field order and still holds together with only identity and gaps', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  for (const { fields, display, rendered } of [
    { fields: ['driver', 'interval', 'last_lap'], display: 'separate', rendered: ['driver', 'interval', 'last_lap'] },
    { fields: ['interval', 'driver', 'position_with_change', 'best_lap'], display: 'separate', rendered: ['interval', 'driver', 'position_with_change', 'best_lap'] },
    { fields: ['position', 'driver', 'interval', 'gap'], display: 'combined', rendered: ['position', 'driver', 'timing_gap'] },
  ]) {
    await mount(page, { fields, options: { gap_display: display } });
    const view = timing(page);
    expect(await drivers(view).first().locator('td[data-field]').evaluateAll(nodes => nodes.map(node => node.dataset.field))).toEqual(rendered);
    expect(await page.evaluate(() => window.fixtureCard.config.modules[0].fields)).toEqual(fields);
    for (const field of rendered.filter(field => ['interval', 'timing_gap'].includes(field))) {
      const rows = await geometry(view);
      for (const row of rows.filter(row => row[field].content)) expect(row[field].inset).toBeLessThanOrEqual(1);
    }
    if (rendered.indexOf('driver') < rendered.length - 1 && ['interval', 'timing_gap'].includes(rendered[rendered.indexOf('driver') + 1])) {
      await expectCloseDriverGap(view, rendered[rendered.indexOf('driver') + 1]);
    }
  }
});

test('full driver names and branding fit the grouped columns while a narrow enlarged view scrolls inside the table', async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 900 });
  await mount(page, {
    fields: ['position_with_change', 'driver', 'interval', 'gap', 'sector_1_with_minisectors', 'sector_2', 'sector_3', 'last_lap', 'best_lap', 'tyre'],
    options: { gap_display: 'combined' }, appearance: { full_names: true, logos: true },
  });
  const view = timing(page);
  await expectCloseDriverGap(view, 'timing_gap');
  await expect(drivers(view).first().locator('.driver')).toContainText('Charles Leclerc');
  await expect(view.locator('f1-team-logo')).toHaveCount(5);
  for (const driver of await view.locator('td[data-field="driver"] .driver').all()) {
    const fits = await driver.evaluate(node => {
      const cell = node.closest('td').getBoundingClientRect(), content = node.getBoundingClientRect();
      return content.left >= cell.left && content.right <= cell.right + 1 && node.scrollWidth <= node.clientWidth + 1;
    });
    expect(fits).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => { document.documentElement.style.fontSize = '24px'; });
  const scroll = view.locator('.table-scroll');
  const overflow = await scroll.evaluate(node => ({ table: node.scrollWidth > node.clientWidth, document: document.documentElement.scrollWidth > innerWidth + 1 }));
  expect(overflow).toEqual({ table: true, document: false });
  await scroll.evaluate(node => { node.scrollLeft = node.scrollWidth; });
  const reachable = await drivers(view).first().locator('[data-field="tyre"]').evaluate(node => {
    const cell = node.getBoundingClientRect(), container = node.closest('.table-scroll').getBoundingClientRect();
    return cell.right <= container.right + 1 && cell.left >= container.left;
  });
  expect(reachable).toBe(true);
});

test('the current Timing presentation retains its existing spacing and combined-gap alignment', async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 900 });
  await mount(page, { fields: ['position', 'driver', 'interval', 'gap', 'sector_1', 'last_lap'], options: { gap_display: 'combined' } });
  const view = timing(page);
  const compactDriver = (await geometry(view))[0].driver.width;
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'current' } });
  });
  await expect(view).toHaveAttribute('data-presentation', 'current');
  const currentGap = await drivers(view).first().locator('[data-field="timing_gap"]').evaluate(node => {
    const value = node.querySelector('.gap-stack > span').getBoundingClientRect();
    return node.getBoundingClientRect().right - parseFloat(getComputedStyle(node).paddingRight) - value.right;
  });
  expect(Math.abs(currentGap)).toBeLessThanOrEqual(1);
  expect((await geometry(view))[0].driver.width).toBeGreaterThan(compactDriver + 24);
});
