const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('advanced branding is progressively revealed and saved independently of content and focus', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => {
    window.mountModular({ editor: true, config: { appearance: { accent: '#2255bb' }, context: { driver: '16' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } });
    window.fixtureCard.entries = window.fixtureDemo.preview.entries;
  });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Appearance', { exact: true }).click();
  await expect(editor.getByLabel('Style', { exact: true })).toBeVisible();
  await expect(editor.getByLabel('Heading font', { exact: true })).toBeHidden();
  await expect(editor.getByLabel('Decorative accent', { exact: true })).toBeHidden();
  await editor.getByText('Colors and branding', { exact: true }).click();
  await editor.getByLabel('Decorative accent', { exact: true }).selectOption('team');
  await editor.getByLabel('Accent team', { exact: true }).selectOption('Ferrari');
  await editor.getByLabel('Logo size', { exact: true }).selectOption('large');
  await editor.getByLabel('Logo variant', { exact: true }).selectOption('mono');
  await editor.getByText('Headings and surface', { exact: true }).click();
  await editor.getByLabel('Surface', { exact: true }).selectOption('soft');
  await editor.getByLabel('Style', { exact: true }).selectOption('minimal');
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.appearance).toMatchObject({ accent_mode: 'team', accent_team: 'Ferrari', accent: '#2255bb', logo_size: 'large', logo_style: 'mono', surface: 'soft' });
  expect(saved.context.driver).toBe('16'); expect(saved.context.team).toBe('');
  expect(saved.modules[0].fields).toEqual(['driver', 'last_lap']);
  await page.evaluate(() => {
    const demo = window.fixtureDemo;
    demo.hass.states[demo.preview.entries[0].entities.driver_list].attributes.drivers[0].team_color = '#aa33cc';
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(editor.locator('.preview ha-card')).toHaveCSS('border-top-color', 'rgb(170, 51, 204)');
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.locator('ha-card')).toHaveCSS('border-top-color', 'rgb(232, 0, 32)');
  await expect(page.locator('ha-card')).toHaveCSS('border-radius', '20px');
  await expect(page.locator('f1-team-logo .logo-frame').first()).toHaveClass(/mono/);
});

test('an individual palette reset follows theme while preserving other colors and accent choices', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { appearance: { mode: 'light', accent_mode: 'custom', accent: '#2255bb', palette: { personal: '#3366bb', timed: '#ffeeaa' } } } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Accessibility and timing colors', { exact: true }).click();
  await editor.getByText('Timing palette', { exact: true }).click();
  await editor.getByRole('button', { name: 'Reset Personal best', exact: true }).click();
  await expect(editor.getByLabel('Personal best', { exact: true })).toHaveValue('#176b36');
  await expect(editor.getByRole('button', { name: 'Reset Personal best', exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.savedConfig.appearance.palette)).toEqual({ timed: '#ffeeaa' });
  await editor.getByText('Appearance', { exact: true }).click();
  await editor.getByLabel('Theme', { exact: true }).selectOption('dark');
  await expect(editor.getByLabel('Personal best', { exact: true })).toHaveValue('#75dc94');
  await editor.getByRole('button', { name: 'Use automatic timing colors', exact: true }).click();
  expect(await page.evaluate(() => window.savedConfig.appearance)).toMatchObject({ accent: '#2255bb', accent_mode: 'custom', palette: {} });
});

test('logo frames retain size through loading, fallback and reuse for an unknown team', async ({ page }) => {
  let releaseImages;
  const imageGate = new Promise(resolve => { releaseImages = resolve; });
  await page.route('https://media.formula1.com/**', async route => {
    await imageGate;
    await route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30"><circle cx="15" cy="15" r="12" fill="#fff"/></svg>' });
  });
  await page.evaluate(() => window.mountModular({ config: { appearance: { logo_size: 'large' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } }));
  const logo = page.locator('f1-team-logo').first(), driver = page.locator('button.driver').first();
  await expect(logo.locator('.initials')).toBeVisible();
  const before = await driver.boundingBox();
  expect((await logo.boundingBox()).width).toBe(40);
  releaseImages();
  await expect(logo.locator('.initials')).toBeHidden();
  expect(await driver.boundingBox()).toEqual(before);
  await page.evaluate(() => {
    window.previousLogoImage = window.fixtureCard.shadowRoot.querySelector('f1-module-view').shadowRoot.querySelector('f1-team-logo').shadowRoot.querySelector('img');
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    for (const key of ['driver_list', 'driver_positions']) demo.hass.states[entry.entities[key]].attributes.drivers[0].team = 'Unknown Historic Team';
    window.fixtureCard.hass = { ...demo.hass };
  });
  await expect(logo.locator('.initials')).toHaveText('UH');
  await expect(logo.locator('.initials')).toBeVisible();
  await expect(logo.locator('img')).toHaveCount(0);
  await page.evaluate(() => window.previousLogoImage.dispatchEvent(new Event('load')));
  await expect(logo.locator('.initials')).toBeVisible();
  expect((await logo.boundingBox()).width).toBe(40);
  await expect(driver).toHaveAccessibleName(/Unknown Historic Team/);
  for (const [size, width] of [['small', 24], ['normal', 32], ['large', 40]]) {
    await page.evaluate(size => window.fixtureCard.setConfig({ ...window.fixtureCard.config, appearance: { ...window.fixtureCard.config.appearance, logo_size: size } }), size);
    await expect(logo).toHaveCSS('width', `${width}px`);
    expect((await driver.boundingBox()).height).toBeGreaterThanOrEqual(44);
  }
  await page.unroute('https://media.formula1.com/**');
  await page.route('https://media.formula1.com/**', route => route.abort());
  await page.evaluate(() => window.mountModular({ config: { appearance: { logo_size: 'small' }, modules: [{ type: 'timing', fields: ['driver'] }] } }));
  await expect(page.locator('f1-team-logo').first().locator('img')).toBeHidden();
  await expect(page.locator('f1-team-logo').first().locator('.initials')).toBeVisible();
});

test('surface and accent combinations preserve readable timing and independent status colors', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  for (const mode of ['light', 'dark']) {
    for (const surface of ['style', 'framed', 'soft', 'flat']) {
      for (const style of ['f1', 'ha', 'minimal']) {
        await page.evaluate(config => window.mountModular({ config }), { appearance: { mode, surface, style, accent_mode: 'custom', accent: '#2255bb', palette: { personal: '#123456' } }, modules: [{ type: 'timing', fields: ['driver', 'sector_1', 'last_lap'] }] });
        await expect(page.locator('ha-card')).toHaveCSS('border-top-color', 'rgb(34, 85, 187)');
        await expect(page.locator('.signal.personal').first()).toHaveCSS('background-color', 'rgb(18, 52, 86)');
        const rows = await page.locator('tbody tr').evaluateAll(nodes => nodes.slice(0, 2).map(node => getComputedStyle(node).backgroundColor));
        expect(rows[0] !== rows[1]).toBe(surface === 'soft');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
      const violations = (await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact));
      expect(violations).toEqual([]);
    }
  }
  await page.emulateMedia({ forcedColors: 'active' });
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact))).toEqual([]);
});

test('custom timing colors retain text and shape meaning in high-contrast grayscale', async ({ page }) => {
  await page.evaluate(() => {
    document.documentElement.style.filter = 'grayscale(1)';
    window.mountModular({ config: {
      appearance: { palette: { overall: '#ff2200', personal: '#00cc55', timed: '#ffee00' } },
      accessibility: { high_contrast: true, signals: 'both' },
      modules: [{ type: 'timing', fields: ['driver', 'sector_1', 'sector_2', 'sector_3', 'last_lap'] }],
    } });
  });
  for (const [status, symbol, text] of [['overall', '◆', 'Overall fastest'], ['personal', '●', 'Personal best'], ['timed', '■', 'Recorded time']]) {
    const signal = page.locator(`.signal.${status}`).first();
    await expect(signal).toBeVisible();
    await expect(signal).toContainText(symbol);
    await expect(signal).toContainText(text);
  }
  await page.locator('.timing-legend summary').click();
  await expect(page.getByText('Lap change: ▼ faster, ▲ slower, = unchanged at the displayed precision, compared with the previous completed lap. Missing comparison data gives no arrow.', { exact: true })).toBeVisible();
  const violations = (await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations.filter(v => ['serious', 'critical'].includes(v.impact));
  expect(violations).toEqual([]);
});
