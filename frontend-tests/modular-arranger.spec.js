const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const modules = [
  { id: 'timing', type: 'timing', column_span: 2 },
  { id: 'map', type: 'map' },
  { id: 'control', type: 'race_control', column_span: 'full' },
];
async function mount(page, config = {}, language = 'en') {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(({ config, modules, language }) => {
    window.mountModular({ editor: true, language, config: { layout: 'columns', columns: 3, grid_options: { columns: 'full' }, modules, ...config } });
    window.changes = [];
    window.fixtureCard.addEventListener('config-changed', event => window.changes.push(event.detail.config));
  }, { config, modules, language });
  await page.getByRole('button', { name: language === 'sv' ? 'Arrangera moduler' : 'Arrange modules', exact: true }).click();
  const board = page.locator('f1-module-arranger');
  await expect(board.locator('.tile')).toHaveCount((config.modules || modules).length);
  await board.scrollIntoViewIfNeeded();
  return board;
}
async function center(locator) {
  await locator.scrollIntoViewIfNeeded();
  const r = await locator.boundingBox();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
}
async function begin(page, handle) {
  const p = await center(handle); await page.mouse.move(p.x, p.y); await page.mouse.down(); return p;
}
async function order(page) { return page.evaluate(() => window.fixtureCard.config.modules.map(module => module.id)); }
async function events(page) { return page.evaluate(() => window.changes.length); }

// Real pointer input, including moving the captured pointer across Lit reorders.
test('drag reorders mixed spans, commits once, preserves sizing and Undo restores the whole move', async ({ page }) => {
  const board = await mount(page);
  const source = board.getByRole('button', { name: 'Move Timing', exact: true });
  const target = await center(board.locator('[data-id=map] .choose'));
  await begin(page, source);
  await page.mouse.move(target.x + 15, target.y, { steps: 8 });
  await expect(board.locator('.tile').first()).toHaveAttribute('data-id', 'map');
  await page.waitForTimeout(150); // Holding still must not oscillate the insertion point.
  await expect(board.locator('.tile').first()).toHaveAttribute('data-id', 'map');
  expect(await events(page)).toBe(0);
  await page.mouse.up();
  expect(await order(page)).toEqual(['map', 'timing', 'control']);
  expect(await events(page)).toBe(1);
  expect(await page.evaluate(() => window.savedConfig.grid_options)).toEqual({ columns: 'full' });
  expect(await page.evaluate(() => window.savedConfig.modules.map(m => m.column_span))).toEqual([1, 2, 'full']);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  expect(await order(page)).toEqual(['timing', 'map', 'control']);
});

test('resize snaps to columns, reflows neighbours locally, and emits one undoable change', async ({ page }) => {
  const board = await mount(page);
  const pitch = await board.locator('.board').evaluate(n => (n.clientWidth - 2) / 3);
  const p = await begin(page, board.getByRole('button', { name: 'Resize Timing', exact: true }));
  await page.mouse.move(p.x + pitch, p.y, { steps: 8 });
  await expect(board.locator('[data-id=timing] .width')).toHaveText('3 of 3 columns');
  const timing = await board.locator('[data-id=timing]').boundingBox();
  const map = await board.locator('[data-id=map]').boundingBox();
  expect(map.y).toBeGreaterThan(timing.y);
  expect(await events(page)).toBe(0);
  await page.mouse.up();
  expect(await events(page)).toBe(1);
  expect(await page.evaluate(() => window.savedConfig.modules[0].column_span)).toBe(3);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(board.locator('[data-id=timing] .width')).toHaveText('2 of 3 columns');
});

for (const cancel of ['escape', 'pointercancel', 'outside', 'close', 'external']) {
  test(`unfinished drag is discarded on ${cancel}`, async ({ page }) => {
    const board = await mount(page);
    const target = await center(board.locator('[data-id=map] .choose'));
    await begin(page, board.getByRole('button', { name: 'Move Timing', exact: true }));
    await page.mouse.move(target.x + 15, target.y, { steps: 6 });
    await expect(board.locator('.tile').first()).toHaveAttribute('data-id', 'map');
    if (cancel === 'escape') await page.keyboard.press('Escape');
    if (cancel === 'pointercancel') await board.locator('.board').dispatchEvent('pointercancel', { pointerId: 1 });
    if (cancel === 'outside') await page.mouse.move(5, 5);
    if (cancel === 'close') await page.evaluate(() => { window.fixtureCard.arranging = false; });
    if (cancel === 'external') await page.evaluate(() => window.fixtureCard.setConfig({ ...window.fixtureCard.config, title: 'External change' }));
    await page.mouse.up();
    expect(await order(page)).toEqual(['timing', 'map', 'control']);
    expect(await events(page)).toBe(0);
    if (cancel !== 'close') expect(await board.evaluate(n => n.gesture === null && n.frame === null)).toBe(true);
  });
}

test('keyboard handles, click alternatives and full width work without dragging', async ({ page }) => {
  const board = await mount(page);
  await board.getByRole('button', { name: 'Move Timing', exact: true }).focus();
  await page.keyboard.press('End');
  expect(await order(page)).toEqual(['map', 'control', 'timing']);
  await expect(board.getByRole('button', { name: 'Move Timing', exact: true })).toBeFocused();
  await board.getByRole('button', { name: 'Resize Timing', exact: true }).focus();
  await page.keyboard.press('ArrowLeft');
  await expect(board.locator('[data-id=timing] .width')).toHaveText('1 of 3 columns');
  await board.getByLabel('Width of selected module', { exact: true }).selectOption('full');
  await board.getByLabel('Columns in layout', { exact: true }).selectOption('4');
  await expect(board.locator('[data-id=timing] .width')).toHaveText('Full card width');
  await page.getByRole('button', { name: 'Move up Timing', exact: true }).click();
  expect(await order(page)).toEqual(['map', 'timing', 'control']);
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card-editor').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});

test('stack and tabs allow sorting while preserving saved widths and showing hidden modules', async ({ page }) => {
  const board = await mount(page, { layout: 'tabs', modules: [...modules, { id: 'hidden', type: 'weather', enabled: false }] });
  await expect(board.locator('.resize')).toHaveCount(0);
  await expect(board.getByText('Hidden module', { exact: true })).toBeVisible();
  const p = await begin(page, board.getByRole('button', { name: 'Move Timing', exact: true }));
  await page.mouse.move(p.x, p.y + 205, { steps: 8 });
  await page.mouse.up();
  expect((await order(page))[0]).toBe('map');
  await board.getByLabel('Module layout', { exact: true }).selectOption('stack');
  await board.getByLabel('Module layout', { exact: true }).selectOption('columns');
  await expect(board.locator('[data-id=timing] .width')).toHaveText('2 of 3 columns');
  await expect(board.locator('[data-id=control] .width')).toHaveText('Full card width');
});

test('clicks and subthreshold movements do not create changes or alter full width', async ({ page }) => {
  const board = await mount(page);
  const p = await begin(page, board.getByRole('button', { name: 'Resize Race Control', exact: true }));
  await page.mouse.move(p.x + 2, p.y + 1); await page.mouse.up();
  expect(await events(page)).toBe(0);
  await expect(board.locator('[data-id=control] .width')).toHaveText('Full card width');
  await board.getByRole('button', { name: 'Move Timing', exact: true }).click();
  expect(await events(page)).toBe(0);
});

test('Swedish mobile layout scrolls within its overview and has large touch handles', async ({ page }) => {
  const board = await mount(page, { columns: 4 }, 'sv');
  await page.setViewportSize({ width: 390, height: 844 });
  await board.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const scroll = board.locator('.scroll');
  expect(await scroll.evaluate(n => n.scrollWidth > n.clientWidth)).toBe(true);
  const handle = board.getByRole('button', { name: 'Flytta Timing', exact: true });
  const p = await center(handle);
  const box = await handle.boundingBox();
  expect(box.width).toBeGreaterThanOrEqual(44); expect(box.height).toBeGreaterThanOrEqual(44);
  await expect(handle).toHaveCSS('touch-action', 'none');
  await expect(board.locator('[data-id=timing] .choose')).toHaveCSS('touch-action', 'auto');
  await expect(board.getByLabel('Vald moduls bredd', { exact: true })).toHaveValue('2');
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card-editor').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(a11y.violations).toEqual([]);
});


test('touch drag resizes and native scrolling remains available outside handles', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Real touch movement uses Chromium input emulation');
  const board = await mount(page);
  const client = await page.context().newCDPSession(page);
  await client.send('Emulation.setTouchEmulationEnabled', { enabled: true });
  const p = await center(board.getByRole('button', { name: 'Resize Timing', exact: true }));
  const pitch = await board.locator('.board').evaluate(n => (n.clientWidth - 2) / 3);
  await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: p.x, y: p.y }] });
  await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: p.x - pitch, y: p.y }] });
  await expect(board.locator('[data-id=timing] .width')).toHaveText('1 of 3 columns');
  expect(await events(page)).toBe(0);
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  expect(await events(page)).toBe(1);
  expect(await page.evaluate(() => window.savedConfig.modules[0].column_span)).toBe(1);
  await page.setViewportSize({ width: 390, height: 844 });
  const swipe = await center(board.locator('[data-id=timing] .choose'));
  await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: swipe.x, y: swipe.y }] });
  for (let step = 1; step <= 8; step++) await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: swipe.x - step * 12, y: swipe.y }] });
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(() => board.locator('.scroll').evaluate(n => n.scrollLeft)).toBeGreaterThan(0);
  expect(await events(page)).toBe(1);
  await client.detach();
});

test('resizing away and back preserves the full-width choice without an undo entry', async ({ page }) => {
  const board = await mount(page);
  const pitch = await board.locator('.board').evaluate(n => (n.clientWidth - 2) / 3);
  const p = await begin(page, board.getByRole('button', { name: 'Resize Race Control', exact: true }));
  await page.mouse.move(p.x - pitch, p.y, { steps: 6 });
  await expect(board.locator('[data-id=control] .width')).toHaveText('2 of 3 columns');
  await page.mouse.move(p.x, p.y, { steps: 6 });
  await expect(board.locator('[data-id=control] .width')).toHaveText('Full card width');
  await page.mouse.up();
  expect(await events(page)).toBe(0);
});

test('dragging near the overview edge scrolls to further modules and still cancels cleanly', async ({ page }) => {
  const board = await mount(page, { layout: 'stack', modules: Array.from({ length: 10 }, (_, i) => ({ id: `m${i}`, type: 'weather', title: `Weather ${i}` })) });
  const scroll = board.locator('.scroll');
  await scroll.scrollIntoViewIfNeeded();
  const p = await begin(page, board.locator('[data-id=m0] [data-handle=move]'));
  const r = await scroll.boundingBox();
  await page.mouse.move(p.x, r.y + r.height - 12, { steps: 8 });
  await expect.poll(() => scroll.evaluate(n => n.scrollTop)).toBeGreaterThan(100);
  await page.keyboard.press('Escape'); await page.mouse.up();
  expect(await events(page)).toBe(0);
  expect(await order(page)).toEqual(Array.from({ length: 10 }, (_, i) => `m${i}`));
});
