const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const pages = [
  '', 'getting-started/installation', 'cards/cards-overview',
  'cards/next-race', 'entities/track-status', 'help/overview',
];

for (const [query, title, route] of [
  ['track map', /Track Map/i, /\/(cards|features)\/track-map/],
  ['live delay', /Live Delay/i, /\/(features\/live-delay|reference\/live-delay-controls)/],
  ['team radio', /Team Radio/i, /\/entities\/team-radio/],
  ['favorite driver', /Favorite Driver/i, /\/(entities|features)\/favorite-driver/],
  ['sensor.f1_track_status', /Track Status/i, /\/(entities|reference|blueprints)\//],
]) {
  test(`production search opens a relevant result for ${query}`, async ({page}) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('');
    const input = page.getByRole('textbox', {name: 'Search', exact: true});
    await input.fill(query);
    const suggestion = page.locator('[class*="suggestion_"]').filter({hasText: title}).first();
    await expect(suggestion).toBeVisible({timeout: 15000});
    await suggestion.click();
    await expect(page).toHaveURL(route);
    expect(new URL(page.url()).pathname).toMatch(/^\/f1_sensor\//);
    await expect(page.locator('main')).toBeVisible();
    expect(errors).toEqual([]);
  });
}

for (const theme of ['light', 'dark']) {
  test(`documentation is accessible and reflows in ${theme} mode`, async ({page}) => {
    test.setTimeout(120000);
    await page.emulateMedia({colorScheme: theme});
    for (const route of pages) {
      await page.setViewportSize({width: 1440, height: 1000});
      await page.goto(route);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      await page.evaluate(() => document.fonts.ready);
      const violations = (await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
      expect(violations.map(({id, nodes}) => ({id, elements: nodes.map(n => n.target)})), route).toEqual([]);
      const images = page.locator('main img[src^="/f1_sensor/"]');
      for (const img of await images.all()) {
        await img.scrollIntoViewIfNeeded();
        await expect.poll(() => img.evaluate(el => el.complete && el.naturalWidth > 0)).toBe(true);
      }
      for (const width of [320, 390, 768, 1440]) {
        await page.setViewportSize({width, height: 900});
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
        expect(overflow, `${route} at ${width}px`).toBe(false);
      }
    }
  });
}

test('mobile navigation, skip link and gallery filters work with a keyboard', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', {name: 'Skip to main content'})).toBeFocused();
  await page.keyboard.press('Enter');
  await page.getByRole('button', {name: 'Toggle navigation bar'}).click();
  await page.getByRole('button', {name: 'Back to main menu'}).click();
  await page.locator('.navbar-sidebar__item').first().getByRole('link', {name: 'Dashboards', exact: true}).click();
  await expect(page).toHaveURL(/\/cards\/cards-overview$/);
  const filters = page.getByRole('group', {name: 'Filter dashboard cards'});
  const firstCategory = filters.getByRole('button').nth(1);
  await firstCategory.focus();
  await page.keyboard.press('Enter');
  await expect(firstCategory).toHaveAttribute('aria-pressed', 'true');
  await filters.getByRole('button', {name: 'All cards', exact: true}).click();
  await expect(page.getByRole('status').filter({hasText: '23 cards'})).toBeVisible();
});

test('delay illustration responds without changing the integration', async ({page}) => {
  await page.goto('features/live-delay');
  const slider = page.getByRole('slider', {name: /Example broadcast delay/});
  await slider.focus();
  await page.keyboard.press('ArrowRight');
  await expect(slider).toHaveValue('35');
  await expect(page.getByRole('status').filter({hasText: '35-second delay'})).toBeVisible();
});

test('pairing query and fragment survive loading and reloading the helper', async ({page}) => {
  const query = new URLSearchParams({callback_url: 'https://ha.example.invalid/api/f1_sensor/f1tv_auth/pairing', session_id: 'docs-test', nonce: 'not-a-secret-test-value', expires_at: '2030-01-01T00:00:00Z', flow_id: 'docs-flow'});
  const suffix = `?${query}#pairing-test`;
  await page.goto(`help/f1tv-token-helper${suffix}`);
  await expect(page.getByRole('heading', {level: 1, name: 'F1TV Token Helper', exact: true})).toBeVisible();
  expect(new URL(page.url()).search + new URL(page.url()).hash).toBe(suffix);
  await page.reload();
  expect(new URL(page.url()).search + new URL(page.url()).hash).toBe(suffix);
  await page.goto('help/f1tv-token-helper-privacy');
  await expect(page.getByRole('heading', {level: 1, name: 'F1TV Token Helper Privacy Policy'})).toBeVisible();
});

test('mobile search remains usable with a collapsed navbar', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('');
  const input = page.getByRole('textbox', {name: 'Search', exact: true});
  await input.click();
  await input.fill('live delay');
  const result = page.locator('[class*="suggestion_"]').filter({hasText: /Live Delay: sync with your TV/i}).first();
  await expect(result).toBeVisible({timeout: 15000});
  await result.click();
  await expect(page).toHaveURL(/\/features\/live-delay/);
});

test('200 percent zoom equivalent retains content and navigation', async ({browser}) => {
  // A 1440 × 900 display at 200% browser zoom has a 720 × 450 CSS viewport.
  // Headless Chromium does not implement browser-chrome zoom keyboard shortcuts.
  const context = await browser.newContext({viewport: {width: 720, height: 450}, deviceScaleFactor: 2, reducedMotion: 'reduce'});
  const page = await context.newPage();
  try {
    for (const route of pages) {
      await page.goto(`http://127.0.0.1:4174/f1_sensor/${route}`);
      await expect(page.locator('h1')).toBeVisible();
      await expect(page.getByRole('button', {name: 'Toggle navigation bar'})).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), route).toBe(true);
    }
  } finally {
    await context.close();
  }
});

for (const platform of ['Linux', 'macOS']) {
  test(`search shortcut contrast meets AA on ${platform}`, async ({page}) => {
    await page.addInitScript(platform => {
      Object.defineProperty(navigator, 'userAgentData', {value: {platform}, configurable: true});
    }, platform);
    for (const theme of ['light', 'dark']) {
      await page.emulateMedia({colorScheme: theme});
      await page.goto('./');
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('.navbar kbd').first()).toHaveText(platform === 'Linux' ? 'ctrl' : '⌘');
      const {violations} = await new AxeBuilder({page}).include('.navbar').withRules(['color-contrast']).analyze();
      expect(violations).toEqual([]);
    }
  });
}
