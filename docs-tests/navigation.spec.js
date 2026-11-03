const {test, expect} = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const pages = [
  '', 'getting-started/installation', 'cards/cards-overview',
  'cards/modular', 'cards/timing', 'reference/overview', 'entities/track-status',
  'features/replay-mode', 'features/team-radio-transcription', 'help/overview',
];

async function fillSearch(page, query) {
  // The server-rendered textbox is visible before hydration. Focusing starts
  // the index load; autocomplete exposes a combobox only once it is ready.
  await page.getByLabel('Search', {exact: true}).click();
  const input = page.getByRole('combobox', {name: 'Search', exact: true});
  await expect(input).toHaveAttribute('aria-autocomplete', 'list', {timeout: 15000});
  await input.fill(query);
}

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
    await fillSearch(page, query);
    const suggestion = page.locator('[class*="suggestion_"]').filter({hasText: title}).first();
    await expect(suggestion).toBeVisible({timeout: 15000});
    await suggestion.click();
    await expect(page).toHaveURL(route);
    expect(new URL(page.url()).pathname.startsWith(new URL(test.info().project.use.baseURL).pathname)).toBe(true);
    await expect(page.locator('main')).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test('production search waits for hydration on a cold load', async ({page, context}) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let releaseScripts;
  const scriptsReleased = new Promise(resolve => { releaseScripts = resolve; });
  await context.route(/\/assets\/js\/.*\.js(?:\?.*)?$/, async route => {
    await scriptsReleased;
    await route.continue();
  });
  try {
    // Expose the real server-rendered page while its JavaScript is still held.
    await page.goto('', {waitUntil: 'commit'});
    const input = page.getByLabel('Search', {exact: true});
    await Promise.all([
      fillSearch(page, 'team radio'),
      (async () => {
        await expect(input).toBeFocused();
        await expect(input).not.toHaveAttribute('role', 'combobox');
        await expect(input).toHaveValue('');
        releaseScripts();
      })(),
    ]);
    const suggestion = page.locator('[class*="suggestion_"]').filter({hasText: /Team Radio/i}).first();
    await expect(suggestion).toBeVisible({timeout: 15000});
    await suggestion.click();
    await expect(page).toHaveURL(/\/entities\/team-radio/);
    expect(new URL(page.url()).pathname.startsWith(new URL(test.info().project.use.baseURL).pathname)).toBe(true);
    await expect(page.locator('main')).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    releaseScripts();
  }
});

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
      if (route === '') {
        await expect(page.locator('main img[alt="Home Assistant"]:visible')).toHaveCount(1);
      }
      const images = page.locator('main img[src^="/f1_sensor/"]:visible');
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

test('mobile navigation, skip link and card overview work with a keyboard', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', {name: 'Skip to main content'})).toBeFocused();
  await page.keyboard.press('Enter');
  await page.getByRole('button', {name: 'Toggle navigation bar'}).click();
  await page.locator('.navbar-sidebar__item').first().getByRole('link', {name: 'Dashboards', exact: true}).click();
  await expect(page).toHaveURL(/\/cards\/cards-overview$/);
  await expect(page.getByRole('heading', {level: 1, name: 'F1 Sensor dashboard card'})).toBeVisible();
  const buildLink = page.getByRole('link', {name: 'Build and configure the card', exact: true});
  await buildLink.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/cards\/modular$/);
  await expect(page.getByRole('heading', {level: 1, name: 'Build your F1 Sensor card'})).toBeVisible();
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
  await fillSearch(page, 'live delay');
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
      await page.goto(new URL(route, test.info().project.use.baseURL).href);
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
      // Axe does not evaluate placeholder text, so measure the visible prompt too.
      const contrast = await page.getByLabel('Search', {exact: true}).evaluate(input => {
        const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(value => {
          const channel = value / 255;
          return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
        }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
        const foreground = luminance(getComputedStyle(input, '::placeholder').color);
        const background = luminance(getComputedStyle(input).backgroundColor);
        return (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05);
      });
      expect(contrast, `${theme} search placeholder contrast`).toBeGreaterThanOrEqual(4.5);
    }
  });
}

test('the setup path advances to configuration and the first dashboard', async ({page}) => {
  await page.goto('getting-started/installation');
  const next = page.locator('.pagination-nav__link--next');
  await expect(next).toHaveAttribute('href', /\/getting-started\/add-integration$/);
  await next.click();
  await expect(page.getByRole('heading', {level: 1, name: 'Configure F1 Sensor'})).toBeVisible();
  await page.locator('.pagination-nav__link--next').click();
  await expect(page.getByRole('heading', {level: 1, name: 'Your first dashboard'})).toBeVisible();
});

test('desktop navigation stays on one line without overlapping channel or search controls', async ({page}) => {
  for (const width of [997, 1050, 1199]) {
    await page.setViewportSize({width, height: 900});
    await page.goto('');
    const nav = page.locator('nav.navbar');
    const help = await nav.getByRole('link', {name: 'Help', exact: true}).boundingBox();
    const channel = await nav.locator('.navbar-channel-menu').boundingBox();
    const search = await nav.getByLabel('Search', {exact: true}).boundingBox();
    expect(help.x + help.width, `Help and channel overlap at ${width}px`).toBeLessThanOrEqual(channel.x);
    expect(channel.x + channel.width, `Channel and search overlap at ${width}px`).toBeLessThanOrEqual(search.x);
    const start = await nav.getByRole('link', {name: 'Get started', exact: true}).boundingBox();
    expect(start.height, `Get started wraps at ${width}px`).toBeLessThan(50);
  }
});

test('navigation changes context without losing the full reference', async ({page}) => {
  await page.goto('getting-started/installation');
  const sidebar = page.locator('.theme-doc-sidebar-menu');
  await expect(sidebar.locator('a[href$="/entities/pit-stops"]')).toHaveCount(0);
  await page.locator('.navbar').getByRole('link', {name: 'Reference', exact: true}).click();
  await expect(page.getByRole('heading', {level: 1, name: 'Entity and automation reference'})).toBeVisible();
  await expect(sidebar.getByText('Drivers and timing', {exact: true})).toBeVisible();
  await page.locator('.navbar').getByRole('link', {name: 'Dashboards', exact: true}).click();
  await sidebar.getByRole('button', {name: 'Modules', exact: true}).click();
  await expect(sidebar.locator('a[href$="/cards/timing"]')).toBeVisible();
  await expect(sidebar.locator('a[href$="/entities/pit-stops"]')).toHaveCount(0);
  await expect(sidebar.getByRole('link', {name: 'Browse all documentation', exact: true})).toBeVisible();
});

test('the entity catalogue finds fields, filters topics, and recovers from no results', async ({page}) => {
  await page.goto('reference/overview');
  const catalogue = page.getByRole('region', {name: 'Entity reference catalogue'});
  const find = catalogue.getByRole('searchbox', {name: 'Find an entity or attribute'});
  await find.fill('pit_stop_time');
  await expect(catalogue.getByRole('link', {name: 'Pit Stops', exact: true})).toBeVisible();
  await expect(catalogue.getByRole('link', {name: 'Track Status', exact: true})).toHaveCount(0);
  await find.fill('yellow');
  await expect(catalogue.getByRole('link', {name: 'Track Status', exact: true})).toBeVisible();
  await catalogue.getByRole('button', {name: 'Clear filters'}).click();
  await catalogue.getByLabel('Topic', {exact: true}).selectOption('Schedule and weather');
  await expect(catalogue.getByRole('link', {name: 'Next Race', exact: true})).toBeVisible();
  await expect(catalogue.getByRole('link', {name: 'Pit Stops', exact: true})).toHaveCount(0);
  await find.fill('not-a-real-f1-field');
  await expect(catalogue.getByText(/No matching entities/)).toBeVisible();
  await catalogue.getByRole('button', {name: 'Clear filters'}).click();
  await expect(catalogue.getByRole('link', {name: 'Pit Stops', exact: true})).toBeVisible();
});

test('the module finder filters, recovers, and opens its focused guide on mobile', async ({page}) => {
  await page.goto('cards/cards-overview');
  const catalogue = page.getByRole('region', {name: 'Dashboard module catalogue'});
  const initialCount = await catalogue.locator('article').count();
  expect(initialCount).toBeGreaterThan(0);
  const find = catalogue.getByRole('searchbox', {name: 'Find a module'});
  await find.fill('minisectors');
  await expect(catalogue.getByRole('link', {name: 'Minisectors', exact: true})).toBeVisible();
  await expect(catalogue.getByRole('link', {name: 'Timing', exact: true})).toHaveCount(0);
  await find.fill('');
  await catalogue.getByLabel('Module topic', {exact: true}).selectOption('Officials');
  await expect(catalogue.getByRole('link', {name: 'FIA documents', exact: true})).toBeVisible();
  await find.fill('not-a-real-module');
  await expect(catalogue.getByText(/No matching modules/)).toBeVisible();
  await catalogue.getByRole('button', {name: 'Clear filters'}).click();
  await expect(catalogue.locator('article')).toHaveCount(initialCount);
  await find.fill('schedule');
  await catalogue.getByRole('link', {name: 'Schedule', exact: true}).click();
  await expect(page.locator('#calendar-module')).toBeVisible();
  await expect(page.locator('#calendar-module')).toBeInViewport();
  await find.fill('');
  const violations = (await new AxeBuilder({page}).include('main').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()).violations;
  expect(violations.map(({id, nodes}) => ({id, elements: nodes.map(n => n.target)}))).toEqual([]);
  await page.setViewportSize({width: 390, height: 844});
  await find.fill('minisectors');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await catalogue.getByRole('link', {name: 'Minisectors', exact: true}).click();
  await expect(page).toHaveURL(/\/cards\/minisectors/);
});

test('the module list and guide links work without JavaScript', async ({browser}) => {
  const context = await browser.newContext({javaScriptEnabled: false, baseURL: test.info().project.use.baseURL});
  try {
    const page = await context.newPage();
    await page.goto('cards/cards-overview');
    const catalogue = page.getByRole('region', {name: 'Dashboard module catalogue'});
    await catalogue.locator('summary').click();
    for (const item of await catalogue.locator('article').all()) await expect(item).toBeVisible();
    await catalogue.getByRole('link', {name: 'Minisectors', exact: true}).click();
    await expect(page).toHaveURL(/\/cards\/minisectors/);
    await expect(page.getByRole('heading', {level: 1, name: /minisector/i})).toBeVisible();
  } finally {
    await context.close();
  }
});

for (const [query, title, route] of [
  ['TV delay', /Live Delay/i, /\/features\/live-delay/],
  ['flag lights', /Track Status|light/i, /\/(blueprints\/track-status-light|features\/live-delay)/],
  ['no live data', /Find and fix|Frequently asked|Live data/i, /\/(help|entities)\//],
  ['no F1TV account', /F1TV|Frequently asked/i, /\/(features|help)\//],
  ['replay', /Replay/i, /\/(features\/replay-mode|reference\/replay-controls|blueprints\/replay-sync)/],
  ['pit count', /Pit|pit visits/i, /\/(entities|cards)\/pit-stops|\/help\/faq.*#why-does-pit-stops-have-a-count-but-no-stop-times/],
]) {
  test(`task search finds an answer for ${query}`, async ({page}) => {
    await page.goto('');
    await fillSearch(page, query);
    const suggestion = page.locator('[class*="suggestion_"]').filter({hasText: title}).first();
    await expect(suggestion).toBeVisible({timeout: 15000});
    await suggestion.click();
    await expect(page).toHaveURL(route);
  });
}
