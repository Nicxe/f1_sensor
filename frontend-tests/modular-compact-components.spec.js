const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.setViewportSize({ width: 1200, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, modules, { presentation = 'compact', scene = 'race', width } = {}) {
  await page.evaluate(({ modules, presentation, scene, width }) => {
    window.mountModular({ scene, config: {
      appearance: { style: 'ha', mode: 'dark', font: 'system', logos: false, presentation }, modules,
    } });
    if (width) window.fixtureCard.style.width = `${width}px`;
  }, { modules, presentation, scene, width });
}

test('dedicated components retain current defaults and follow independent module presentation choices', async ({ page }) => {
  await mount(page, [
    { id: 'map', type: 'map' },
    { id: 'chart', type: 'progression' },
    { id: 'telemetry', type: 'telemetry' },
    { id: 'radio', type: 'team_radio' },
    { id: 'history', type: 'tyres', options: { content: 'history' } },
  ], { presentation: 'current', scene: 'replay' });
  const tags = ['f1-track-map-view', 'f1-series-chart', 'f1-telemetry-view', 'f1-team-radio-view', 'f1-tyre-history-view'];
  for (const tag of tags) {
    await expect(page.locator(tag)).toHaveAttribute('presentation', 'current');
    await expect(page.locator(tag)).toHaveCSS('font-size', '16px');
  }
  expect(await page.locator('f1-series-chart .plot').evaluate(node => node.viewBox.baseVal.height)).toBe(320);
  const fields = await page.evaluate(() => window.fixtureCard.config.modules.map(module => module.fields));
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
  for (const tag of tags) await expect(page.locator(tag)).toHaveAttribute('presentation', 'compact');
  expect(await page.evaluate(() => window.fixtureCard.config.modules.map(module => module.fields))).toEqual(fields);
  await page.evaluate(() => {
    const card = window.fixtureCard, config = structuredClone(card.config);
    config.modules.find(module => module.id === 'radio').appearance.presentation = 'current';
    card.setConfig(config);
  });
  await expect(page.locator('f1-team-radio-view')).toHaveAttribute('presentation', 'current');
  for (const tag of tags.filter(tag => tag !== 'f1-team-radio-view')) await expect(page.locator(tag)).toHaveAttribute('presentation', 'compact');
});

test('compact radio reduces its identity header without losing transcript, time, status or usable audio controls', async ({ page }) => {
  await mount(page, [{ id: 'radio', type: 'team_radio' }], { presentation: 'current', width: 360 });
  const radio = page.locator('f1-team-radio-view');
  await expect(radio.locator('.radio-head')).toBeVisible();
  const before = await radio.evaluate(view => ({
    header: view.shadowRoot.querySelector('.radio-head').getBoundingClientRect().height,
    turns: [...view.shadowRoot.querySelectorAll('.turn')].map(node => node.textContent),
    meta: view.shadowRoot.querySelector('.meta').textContent,
    time: view.shadowRoot.querySelector('time').dateTime,
  }));
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
  await expect(radio).toHaveAttribute('presentation', 'compact');
  const after = await radio.evaluate(view => ({
    header: view.shadowRoot.querySelector('.radio-head').getBoundingClientRect().height,
    turns: [...view.shadowRoot.querySelectorAll('.turn')].map(node => node.textContent),
    meta: view.shadowRoot.querySelector('.meta').textContent,
    time: view.shadowRoot.querySelector('time').dateTime,
    controls: [...view.shadowRoot.querySelectorAll('.audio button,.audio input')].map(node => {
      const bounds = node.getBoundingClientRect(); return { width: bounds.width, height: bounds.height };
    }),
    overflow: view.scrollWidth > view.clientWidth,
  }));
  expect(after.header).toBeLessThan(before.header);
  expect(after.turns).toEqual(before.turns);
  expect(after.meta).toBe(before.meta);
  expect(after.time).toBe(before.time);
  expect(after.overflow).toBe(false);
  for (const control of after.controls) {
    expect(control.height).toBeGreaterThanOrEqual(44);
    expect(control.width).toBeGreaterThanOrEqual(44);
  }
  await expect(radio.getByRole('button', { name: 'Play Team Radio', exact: true })).toBeDisabled();
  const audit = await new AxeBuilder({ page }).include('f1-sensor-card').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(audit.violations).toEqual([]);
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, font: 'f1' } });
  });
  await expect(radio).toHaveAttribute('data-configured-font', 'f1');
  expect(await radio.locator('.identity strong').evaluate(node => getComputedStyle(node).fontFamily)).toContain('F1 Barlow Condensed');
});

for (const width of [900, 360]) {
  test(`compact progression protects configured plot height and readable axes at ${width}px card width`, async ({ page }) => {
    await mount(page, [{ id: 'chart', type: 'progression', options: { chart_height: 360, legend_position: 'right' } }], { width });
    const chart = page.locator('f1-series-chart');
    await expect(chart).toHaveAttribute('presentation', 'compact');
    await expect(chart.locator('.plot')).toBeVisible();
    await expect(chart.locator('.chart-layout')).toHaveCSS('flex-direction', width < 600 ? 'column' : 'row');
    await expect.poll(() => chart.evaluate(view => {
      const plot = view.shadowRoot.querySelector('.plot');
      return Math.abs(plot.viewBox.baseVal.width - plot.getBoundingClientRect().width);
    })).toBeLessThan(1.5);
    const geometry = await chart.evaluate(view => {
      const plot = view.shadowRoot.querySelector('.plot'), axis = view.shadowRoot.querySelector('.axis');
      const scale = plot.getBoundingClientRect().width / plot.viewBox.baseVal.width;
      return {
        configuredHeight: plot.viewBox.baseVal.height,
        height: plot.getBoundingClientRect().height,
        axisSize: parseFloat(getComputedStyle(axis).fontSize) * scale,
        labels: [...view.shadowRoot.querySelectorAll('.legend-name')].map(node => node.textContent),
      };
    });
    expect(geometry.configuredHeight).toBe(360);
    expect(geometry.height).toBeGreaterThanOrEqual(359);
    expect(geometry.axisSize).toBeGreaterThanOrEqual(11.9);
    expect(geometry.labels[0]).toMatch(/●/);
    const toggle = chart.locator('.legend-toggle').first();
    expect((await toggle.boundingBox()).height).toBeGreaterThanOrEqual(44);
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await expect(chart.getByText('Gaps mean data is missing.', { exact: true })).toBeVisible();
    await chart.getByRole('button', { name: 'Show data table', exact: true }).click();
    await expect(chart.locator('table')).toBeVisible();
    await expect(chart.locator('tbody tr')).toHaveCount(4);
    await page.evaluate(() => {
      const card = window.fixtureCard, config = structuredClone(card.config);
      config.modules[0].appearance.presentation = 'current';
      card.setConfig(config);
    });
    await expect(chart).toHaveAttribute('presentation', 'current');
    expect(await chart.evaluate(view => view.observedWidthTarget === view)).toBe(true);
    await expect(chart).toHaveCSS('font-size', '16px');
    await expect.poll(() => chart.evaluate(view => Math.abs(view.chartWidth - Math.round(view.getBoundingClientRect().width)))).toBeLessThan(1.5);
    expect(await chart.locator('.plot').evaluate(node => node.viewBox.baseVal.height)).toBe(360);
  });
}

test('compact telemetry retains signal units, recording scope, plot area and data tables in a narrow module', async ({ page }) => {
  await mount(page, [{ id: 'telemetry', type: 'telemetry', fields: ['telemetry_speed', 'telemetry_delta_s'] }], { scene: 'replay', width: 360 });
  const telemetry = page.locator('f1-telemetry-view');
  await expect(telemetry).toHaveAttribute('presentation', 'compact');
  await expect(telemetry.locator('svg.plot').first()).toBeVisible();
  await expect(telemetry.getByText(/Analysis of the complete recording\./)).toBeVisible();
  await expect(telemetry.locator('h3').first()).toContainText('km/h');
  const plots = await telemetry.locator('svg.plot').evaluateAll(nodes => nodes.map(node => ({
    height: node.viewBox.baseVal.height,
    axisSize: parseFloat(getComputedStyle(node.querySelector('.axis')).fontSize) * node.getBoundingClientRect().width / node.viewBox.baseVal.width,
  })));
  for (const plot of plots) {
    expect(plot.height).toBeGreaterThanOrEqual(230);
    expect(plot.axisSize).toBeGreaterThanOrEqual(11.9);
  }
  await telemetry.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(telemetry.locator('table')).toBeVisible();
  await expect(telemetry.getByRole('columnheader', { name: 'Speed (km/h)', exact: true })).toBeVisible();
  await expect(telemetry.getByRole('columnheader', { name: 'Recorded gap', exact: true })).toBeVisible();
  await telemetry.locator('details').first().locator('summary').click();
  const pickers = telemetry.locator('.pickers select');
  await expect(pickers).toHaveCount(2);
  await expect(telemetry.locator('.pickers')).toHaveCSS('grid-template-columns', /^\d+(?:\.\d+)?px$/);
  const [driver, lap] = await Promise.all([pickers.nth(0).boundingBox(), pickers.nth(1).boundingBox()]);
  expect(driver.height).toBeGreaterThanOrEqual(44);
  expect(lap.height).toBeGreaterThanOrEqual(44);
  expect(lap.y).toBeGreaterThan(driver.y);
});

test('compact map preserves track and driver semantics while reducing its surrounding metadata', async ({ page }) => {
  await mount(page, [{ id: 'map', type: 'map' }], { presentation: 'current', width: 360 });
  const map = page.locator('f1-track-map-view');
  await expect(map.locator('.track')).toBeVisible();
  const before = await map.evaluate(view => ({
    path: view.shadowRoot.querySelector('.track').getAttribute('d'),
    names: [...view.shadowRoot.querySelectorAll('.marker text')].map(node => node.textContent),
    stale: view.shadowRoot.querySelectorAll('.marker.stale').length,
  }));
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
  await expect(map).toHaveAttribute('presentation', 'compact');
  const after = await map.evaluate(view => ({
    path: view.shadowRoot.querySelector('.track').getAttribute('d'),
    names: [...view.shadowRoot.querySelectorAll('.marker text')].map(node => node.textContent),
    stale: view.shadowRoot.querySelectorAll('.marker.stale').length,
  }));
  expect(after).toEqual(before);
  await expect(map.locator('.map-footer')).toBeVisible();
  await expect(map.locator('.map-status').filter({ hasText: 'Track:' })).toContainText('Clear');
  const drivers = map.locator('.driver-list button');
  await expect(drivers).toHaveCount(5);
  for (const button of await drivers.all()) expect((await button.boundingBox()).height).toBeGreaterThanOrEqual(44);
});

test('compact tyre history keeps stint geometry, age and keyboard expansion intact', async ({ page }) => {
  await mount(page, [{ id: 'history', type: 'tyres', options: { content: 'history' } }], { presentation: 'current', width: 360 });
  const history = page.locator('f1-tyre-history-view');
  await expect(history.locator('.segment').first()).toBeVisible();
  const before = await history.locator('.segment').evaluateAll(nodes => nodes.map(node => ({ left: node.style.left, width: node.style.width })));
  const ages = await history.locator('.age').allTextContents();
  const laneHeight = (await history.locator('.lane').first().boundingBox()).height;
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
  await expect(history).toHaveAttribute('presentation', 'compact');
  expect(await history.locator('.segment').evaluateAll(nodes => nodes.map(node => ({ left: node.style.left, width: node.style.width })))).toEqual(before);
  expect(await history.locator('.age').allTextContents()).toEqual(ages);
  expect((await history.locator('.lane').first().boundingBox()).height).toBeCloseTo(laneHeight, 0);
  const button = history.locator('.driver-row').first();
  expect((await button.boundingBox()).height).toBeGreaterThanOrEqual(44);
  await button.press('Enter');
  await expect(button).toHaveAttribute('aria-expanded', 'true');
  await expect(history.locator('.stints')).toBeVisible();
  await expect(history.getByRole('columnheader', { name: 'Before this stint', exact: true })).toBeVisible();
  await button.press('Enter');
  await expect(button).toHaveAttribute('aria-expanded', 'false');
});
