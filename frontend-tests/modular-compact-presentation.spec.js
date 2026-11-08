const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.route('https://**/*', route => route.abort());
  await page.setViewportSize({ width: 1200, height: 1000 });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

const moduleView = (page, id) => page.locator(`f1-module-view[data-module-id="${id}"]`);

test('card compact mode keeps selected content and existing defaults across the original pilot and results', async ({ page }) => {
  const config = {
    appearance: { style: 'minimal', density: 'compact', logos: false },
    modules: [
      { id: 'timing', type: 'timing', fields: ['driver', 'sector_1', 'last_lap', 'tyre', 'tyre_age'] },
      { id: 'weather', type: 'weather', fields: ['temperature', 'humidity'], options: { content: 'current_conditions', presentation: 'compact_list' } },
      { id: 'control', type: 'race_control', options: { show_fia_logo: false, show_clear_button: false } },
      { id: 'tyres', type: 'tyres', fields: ['driver', 'tyre', 'tyre_age'], options: { rows: 2 } },
      { id: 'results', type: 'results', fields: ['driver', 'points'], options: { rows: 2 } },
    ],
  };
  await page.evaluate(config => window.mountModular({ config }), config);
  const types = ['timing', 'weather', 'control', 'tyres', 'results'];
  for (const id of types) await expect(moduleView(page, id)).toHaveAttribute('data-presentation', 'current');
  await expect(moduleView(page, 'weather').getByText('24.5 °C', { exact: true })).toBeVisible();
  await expect(moduleView(page, 'weather').getByText('Current circuit weather', { exact: true }).first()).toBeVisible();
  await expect(moduleView(page, 'control').getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  const savedModules = await page.evaluate(() => structuredClone(window.fixtureCard.config.modules));
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
  for (const id of types) await expect(moduleView(page, id)).toHaveAttribute('data-presentation', 'minimal');
  expect(await page.evaluate(() => window.fixtureCard.config.modules)).toEqual(savedModules);
  await expect(moduleView(page, 'weather').getByText('24.5 °C', { exact: true })).toBeVisible();
  await expect(moduleView(page, 'weather').getByText('Current circuit weather', { exact: true }).first()).toBeVisible();
  await expect(moduleView(page, 'control').getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  await expect(moduleView(page, 'tyres').getByRole('img', { name: 'Tyre · Soft', exact: true })).toBeVisible();
  await expect(moduleView(page, 'tyres').locator('tbody tr')).toHaveCount(2);
  await expect(moduleView(page, 'tyres').getByRole('columnheader', { name: 'Tyre age', exact: true })).toBeVisible();

  await page.evaluate(() => {
    const card = window.fixtureCard;
    const config = structuredClone(card.config);
    config.modules.find(module => module.id === 'weather').appearance.presentation = 'current';
    card.setConfig(config);
  });
  await expect(moduleView(page, 'weather')).toHaveAttribute('data-presentation', 'current');
  await expect(moduleView(page, 'timing')).toHaveAttribute('data-presentation', 'minimal');
  await expect(moduleView(page, 'weather').locator('dl.weather-list')).toBeVisible();
});

test('a compact card preserves the actual heading and table styles of modules with current overrides', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: {
    appearance: { style: 'f1', font: 'auto', density: 'comfortable', logos: false },
    modules: [
      { id: 'results', type: 'results', fields: ['driver', 'points'], appearance: { presentation: 'current' }, options: { rows: 2 } },
      { id: 'tyres-current', type: 'tyres', fields: ['driver', 'tyre', 'tyre_age'], appearance: { presentation: 'current' }, options: { rows: 2 } },
      { id: 'timing-follow', type: 'timing', fields: ['driver', 'sector_1'] },
    ],
  } }));
  const styles = async id => {
    const module = moduleView(page, id);
    await expect(module.locator('tbody td').first()).toBeVisible();
    return module.evaluate(element => {
      const heading = getComputedStyle(element.shadowRoot.querySelector('h2'));
      const cell = getComputedStyle(element.shadowRoot.querySelector('tbody td'));
      const header = getComputedStyle(element.shadowRoot.querySelector('thead th'));
      return {
        heading: { family: heading.fontFamily, size: heading.fontSize, weight: heading.fontWeight, transform: heading.textTransform },
        cell: { padding: cell.padding, size: cell.fontSize },
        header: { padding: header.padding, size: header.fontSize },
      };
    });
  };
  const before = { results: await styles('results'), tyres: await styles('tyres-current') };
  const beforeTiming = await styles('timing-follow');
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, appearance: { ...card.config.appearance, presentation: 'compact' } });
  });
  await expect(moduleView(page, 'timing-follow')).toHaveAttribute('data-presentation', 'minimal');
  await expect(moduleView(page, 'results')).toHaveAttribute('data-presentation', 'current');
  await expect(moduleView(page, 'tyres-current')).toHaveAttribute('data-presentation', 'current');
  expect(await styles('results')).toEqual(before.results);
  expect(await styles('tyres-current')).toEqual(before.tyres);
  const compactTiming = await styles('timing-follow');
  expect(compactTiming.heading.family).not.toBe(beforeTiming.heading.family);
  expect(compactTiming.cell.padding).not.toBe(beforeTiming.cell.padding);
});

test('editor saves card and module presentation independently of timing columns and legacy information choices', async ({ page }) => {
  const fields = ['position', 'driver', 'interval', 'gap', 'sector_1_with_minisectors', 'tyre', 'tyre_age'];
  await page.evaluate(fields => window.mountModular({ editor: true, nativePreview: false, config: {
    modules: [{ id: 'timing', type: 'timing', fields, options: { gap_display: 'combined', gap_primary: 'gap', tyre_age_inline: true, show_gap_toggle: true } }],
  } }), fields);
  const editor = page.locator('f1-sensor-card-editor');
  await editor.locator('summary').filter({ hasText: /^Appearance$/ }).click();
  await expect(editor.getByLabel('Card presentation', { exact: true })).toHaveValue('current');
  await editor.getByLabel('Card presentation', { exact: true }).selectOption('compact');
  await editor.locator('summary').filter({ hasText: /^Module appearance$/ }).click();
  await expect(editor.getByLabel('Module presentation', { exact: true })).toHaveValue('inherit');
  await editor.getByLabel('Module presentation', { exact: true }).selectOption('current');
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.appearance.presentation).toBe('compact');
  expect(saved.modules[0].appearance.presentation).toBe('current');
  expect(saved.modules[0].fields).toEqual(fields);
  expect(saved.modules[0].options).toMatchObject({ gap_display: 'combined', gap_primary: 'gap', tyre_age_inline: true, show_gap_toggle: true });
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(moduleView(page, 'timing')).toHaveAttribute('data-presentation', 'current');
  await expect(page.getByLabel('Card presentation', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Module presentation', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('group', { name: 'Gap mode', exact: true })).toHaveCount(0);

  await page.evaluate(config => window.mountModular({ editor: true, nativePreview: false, config }), saved);
  await editor.locator('summary').filter({ hasText: /^Module appearance$/ }).click();
  await editor.getByLabel('Module presentation', { exact: true }).selectOption('inherit');
  const inherited = await page.evaluate(() => window.savedConfig);
  await page.evaluate(config => window.mountModular({ config }), inherited);
  await expect(moduleView(page, 'timing')).toHaveAttribute('data-presentation', 'minimal');
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].fields)).toEqual(fields);
  const combined = moduleView(page, 'timing').locator('tr[data-driver="63"] [data-field="timing_gap"]');
  await expect(combined.locator('[data-gap]').first()).toHaveAttribute('data-gap', 'gap');
});

test('compact Race Control wraps full messages and keeps category, precise time and chosen fields', async ({ page }) => {
  const message = 'CAR 16 - REVIEW OF THE INCIDENT AT TURN 4. ' + 'The stewards are reviewing the timing and the available evidence. '.repeat(5);
  await page.evaluate(message => {
    window.mountModular({ config: { appearance: { presentation: 'compact' }, modules: [{ id: 'control', type: 'race_control', options: { show_clear_button: false, show_fia_logo: false } }] } });
    const card = window.fixtureCard;
    card.previewData = { ...card.previewData, events: [
      { event_id: 'long', utc: '2026-09-13T13:31:00Z', category: 'Other', message },
      { event_id: 'safety', utc: '2026-09-13T13:30:00Z', category: 'SafetyCar', message: 'SAFETY CAR DEPLOYED' },
    ] };
  }, message);
  const control = moduleView(page, 'control');
  const long = control.locator('li').filter({ hasText: message });
  await expect(long.getByText(message, { exact: true })).toBeVisible();
  await expect(control.getByText('SAFETY CAR DEPLOYED', { exact: true })).toBeVisible();
  await expect(long.getByText('Other', { exact: true })).toBeVisible();
  const timestamp = await long.locator('time').first().getAttribute('datetime');
  expect(Date.parse(timestamp)).toBe(Date.parse('2026-09-13T13:31:00Z'));
  await long.getByText('Details', { exact: true }).click();
  await expect(long.locator('details time')).toBeVisible();
  await expect(long.locator('details time')).toContainText('2026');
  await long.getByText('Details', { exact: true }).click();
  await expect(long.getByText(message, { exact: true })).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    const config = structuredClone(card.config);
    config.modules[0].fields = ['message'];
    card.setConfig(config);
  });
  await expect(control.locator('time')).toHaveCount(0);
  await expect(control.getByText(message, { exact: true })).toBeVisible();
  await expect(control.getByText('Other', { exact: true })).toBeVisible();
});

test('compact weather and tyre choices remain readable and usable on a narrow touch screen in both themes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.mountModular({ config: {
    appearance: { presentation: 'compact', logos: false, tyre_style: 'ring' },
    modules: [
      { id: 'weather', type: 'weather', fields: ['temperature', 'track_temperature', 'rainfall'], options: { content: 'track_conditions', presentation: 'compact_list' } },
      { id: 'tyres', type: 'tyres', fields: ['driver', 'tyre', 'tyre_age'], options: { rows: 2 } },
    ],
  } }));
  const weather = moduleView(page, 'weather'), tyres = moduleView(page, 'tyres');
  for (const mode of ['dark', 'light']) {
    await page.evaluate(mode => {
      const card = window.fixtureCard;
      card.setConfig({ ...card.config, appearance: { ...card.config.appearance, mode } });
    }, mode);
    await expect(weather.getByText('Track weather observations', { exact: true }).first()).toBeVisible();
    await expect(weather.getByText('No rain detected', { exact: true })).toBeVisible();
    await expect(tyres.getByRole('img', { name: 'Tyre · Soft', exact: true })).toBeVisible();
    const driver = tyres.getByRole('button', { name: /LEC/ });
    await expect(driver).toBeVisible();
    const box = await driver.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThanOrEqual(44);
    await driver.click();
    await expect(tyres).toContainText('Charles Leclerc');
    await driver.click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const audit = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
    expect(audit.violations.filter(item => ['critical', 'serious'].includes(item.impact))).toEqual([]);
  }
});
