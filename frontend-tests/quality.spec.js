const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const PERFORMANCE_BUDGETS = require('../quality/performance-budgets.json').browser;

const openFixture = async (page) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto('/frontend-tests/fixture.html');
  await page.waitForFunction(() => typeof window.mountF1Gallery === 'function');
  return errors;
};

test('mounts and unmounts all cards and editors without browser errors', async ({ page }) => {
  const errors = await openFixture(page);
  const types = await page.evaluate(() => window.f1CardTypes());
  expect(types).toHaveLength(23);
  for (const type of types) {
    const card = await page.evaluate((current) => window.mountF1Element({ type: current }), type);
    expect(card.tag).toBe(type);
    const editor = await page.evaluate(
      (current) => window.mountF1Element({ type: current, editor: true }),
      type,
    );
    expect(editor.tag).toBe(`${type}-editor`);
  }
  const compatibilityAlias = await page.evaluate(
    () => window.mountF1Element({ type: 'f1-session-archive-card' }),
  );
  expect(compatibilityAlias.tag).toBe('f1-session-archive-card');
  expect(errors).toEqual([]);
});

test('all cards expose keyboard actions and the shared native action contract', async ({ page }) => {
  await openFixture(page);
  const types = [
    ...await page.evaluate(() => window.f1CardTypes()),
    'f1-session-archive-card',
  ];
  for (const type of types) {
    await page.evaluate((current) => window.mountF1Element({ type: current }), type);
    await page.evaluate(() => {
      window.__f1ActionDetail = null;
      document.querySelector('#mount').addEventListener('hass-action', (event) => {
        window.__f1ActionDetail = event.detail;
      }, { once: true });
      const root = document.querySelector('#mount').firstElementChild.renderRoot;
      const target = root.querySelector('[data-f1-card-action], ha-card[role="button"]');
      if (!target) throw new Error('No keyboard action target found');
      target.focus();
    });
    await page.keyboard.press('Enter');
    await expect.poll(() => page.evaluate(() => window.__f1ActionDetail)).toMatchObject({ action: 'tap' });
  }
});

test('tap, hold, double tap and legacy service actions use the native event contract', async ({ page }) => {
  await openFixture(page);
  await page.evaluate(async () => {
    await window.mountF1Element({ type: 'f1-weekend-hub-card' });
    const element = document.querySelector('f1-weekend-hub-card');
    element.setConfig({
      ...element.config,
      tap_action: { action: 'call-service', service: 'input_boolean.toggle' },
      hold_action: { action: 'navigate', navigation_path: '/lovelace/f1' },
      double_tap_action: { action: 'url', url_path: 'https://example.invalid/f1' },
    });
    await element.updateComplete;
  });
  const invoke = async (action, dispatch) => {
    await page.evaluate(() => { window.__f1ActionDetail = null; });
    await dispatch();
    await expect.poll(() => page.evaluate(() => window.__f1ActionDetail)).toMatchObject({ action });
    return page.evaluate(() => window.__f1ActionDetail);
  };
  await page.evaluate(() => {
    document.querySelector('#mount').addEventListener('hass-action', (event) => {
      window.__f1ActionDetail = event.detail;
    });
  });
  const tap = await invoke('tap', () => page.evaluate(() => {
    document.querySelector('f1-weekend-hub-card')._handleCardAction('tap');
  }));
  expect(tap.config.tap_action).toMatchObject({
    action: 'perform-action',
    perform_action: 'input_boolean.toggle',
  });
  await invoke('hold', () => page.evaluate(() => {
    document.querySelector('f1-weekend-hub-card')._handleCardAction('hold');
  }));
  await invoke('double_tap', () => page.evaluate(() => {
    document.querySelector('f1-weekend-hub-card')._handleCardAction('double_tap');
  }));
});

test('axe finds no serious or critical violations across cards and editors', async ({ page }) => {
  await openFixture(page);
  await page.evaluate(() => window.mountF1Gallery());
  const cards = await new AxeBuilder({ page }).include('#mount').analyze();
  expect(cards.violations.filter(({ impact }) => ['serious', 'critical'].includes(impact))).toEqual([]);
  await page.evaluate(() => window.mountF1Element({ type: 'f1-session-archive-card' }));
  const alias = await new AxeBuilder({ page }).include('#mount').analyze();
  expect(alias.violations.filter(({ impact }) => ['serious', 'critical'].includes(impact))).toEqual([]);
  await page.evaluate(() => window.mountF1Gallery({ editor: true }));
  const editors = await new AxeBuilder({ page }).include('#mount').analyze();
  expect(editors.violations.filter(({ impact }) => ['serious', 'critical'].includes(impact))).toEqual([]);
});

test('Swedish locale and English fallback render without raw translation keys', async ({ page }) => {
  await openFixture(page);
  await page.evaluate(() => window.mountF1Element({ type: 'f1-weekend-hub-card', language: 'sv-SE' }));
  const swedishText = await page.evaluate(
    () => document.querySelector('f1-weekend-hub-card').renderRoot.textContent,
  );
  expect(swedishText).toContain('Helghubb');
  expect(swedishText).not.toMatch(/card\.[a-z_.]+|track_map\.[a-z_.]+/);
  await page.evaluate(() => window.mountF1Element({ type: 'f1-weekend-hub-card', language: 'zz-ZZ' }));
  const fallbackText = await page.evaluate(
    () => document.querySelector('f1-weekend-hub-card').renderRoot.textContent,
  );
  expect(fallbackText).toContain('Weekend Hub');
});

test('Swedish localization covers the complete card and editor gallery', async ({ page }) => {
  await openFixture(page);
  await page.evaluate(() => window.mountF1Gallery({ language: 'sv-SE' }));
  const cardText = await page.evaluate(() => [...document.querySelector('#mount').children]
    .map((element) => element.renderRoot.textContent).join('\n'));
  for (const untranslated of [
    'Tyres Statistics',
    'Driver Championship',
    'Replay Control',
    'Waiting for track map data',
    'Select entities in the editor',
  ]) expect(cardText).not.toContain(untranslated);

  await page.evaluate(() => window.mountF1Gallery({ language: 'sv-SE', editor: true }));
  const editorText = await page.evaluate(() => [...document.querySelector('#mount').children]
    .map((element) => element.renderRoot.textContent).join('\n'));
  for (const untranslated of [
    'Data Sources',
    'REQUIRED SENSORS',
    'OPTIONAL SENSORS',
    'Provides live session type and timing data',
    'This sensor is required for the card to function',
  ]) expect(editorText).not.toContain(untranslated);
});

test('card picker metadata follows the browser language with English fallback', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'language', { configurable: true, value: 'sv-SE' });
  });
  await openFixture(page);
  const metadata = await page.evaluate(() => window.customCards.map(({ name, description }) => ({
    name,
    description,
  })));
  expect(metadata).toHaveLength(23);
  expect(metadata[0]).toEqual({
    name: 'F1 Helghubb',
    description: 'En synkroniserad samlingsplats för live, repris och analys efter sessionen',
  });
});

test('Home Assistant timezone wins when the browser timezone differs', async ({ page }) => {
  await openFixture(page);
  await page.evaluate(() => window.mountF1Element({ type: 'f1-next-race-card' }));
  const text = await page.evaluate(
    () => document.querySelector('f1-next-race-card').renderRoot.textContent,
  );
  const browserHour = await page.evaluate(() => new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    hour12: false,
  }).format(new Date('2026-09-06T13:00:00Z')));
  expect(browserHour).not.toBe('15');
  expect(text).toContain('15:00');
});

for (const matrix of [
  { name: 'mobile-dark-sv', width: 360, theme: 'dark', language: 'sv-SE' },
  { name: 'tablet-light-en', width: 700, theme: 'light', language: 'en-GB' },
  { name: 'wide-dark-en', width: 1050, theme: 'dark', language: 'en-GB' },
]) {
  test(`visual matrix ${matrix.name}`, async ({ page }) => {
    await page.setViewportSize({ width: matrix.width, height: 900 });
    await openFixture(page);
    await page.evaluate((options) => window.mountF1Gallery(options), matrix);
    await expect(page).toHaveScreenshot(`${matrix.name}.png`, { fullPage: true });
  });
}

test('200 percent zoom, reduced motion, forced colors and coarse pointer remain usable', async ({ page }) => {
  await page.setViewportSize({ width: 700, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce', forcedColors: 'active' });
  await openFixture(page);
  await page.evaluate(async () => {
    document.body.style.zoom = '2';
    await window.mountF1Element({ type: 'f1-weekend-hub-card' });
  });
  const card = page.locator('f1-weekend-hub-card');
  await expect(card).toBeVisible();
  await expect(page).toHaveScreenshot('zoom-forced-colors.png', { fullPage: true });
});

test('render performance stays inside the Phase 5 browser budget', async ({ page }) => {
  await openFixture(page);
  const result = await page.evaluate(async () => {
    const longTasks = [];
    const observer = new PerformanceObserver((list) => longTasks.push(...list.getEntries().map(({ duration }) => duration)));
    observer.observe({ entryTypes: ['longtask'] });
    const start = performance.now();
    await window.mountF1Gallery();
    const duration = performance.now() - start;
    observer.disconnect();
    return { duration, longestTask: Math.max(0, ...longTasks) };
  });
  expect(result.duration).toBeLessThan(PERFORMANCE_BUDGETS.gallery_render_ms);
  expect(result.longestTask).toBeLessThan(PERFORMANCE_BUDGETS.long_task_ms);
});
