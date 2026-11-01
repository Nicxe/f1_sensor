const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

async function mount(page, { enabled = true, scene = 'qualifying', combined = false } = {}) {
  await page.evaluate(({ enabled, scene, combined }) => {
    window.mountModular({ scene, config: { modules: [{ id: 'timing', type: 'timing', fields: ['driver', ...[1, 2, 3].map(n => combined ? `sector_${n}_with_minisectors` : `sector_${n}`)], options: { push_laps: 'first', push_lap_deltas: enabled } }] } });
    window.setCheckpointFixture = (delta = {}, push = {}) => {
      const card = window.fixtureCard, entity = window.fixtureDemo.preview.entries[0].entities.driver_positions;
      const source = card.hass.states[entity];
      card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { ...source, attributes: { ...source.attributes,
        current_qualifying_part: 1,
        drivers: source.attributes.drivers.map(driver => driver.racing_number === '63' ? { ...driver,
          push_lap: { state: 'push', active: true, lap: 2, progress: .8, ...push },
          push_lap_delta: { status: 'available', lap: 2, session_part: 1, reference: { racing_number: '16', lap: 2, time: 95.2 }, sector_1: -.008, sector_2: .357, sector_3: 1.041, latest_sector: 3, ...delta },
        } : { ...driver, push_lap: { state: 'cooldown', active: false, progress: null } }),
      } } } };
    };
    window.setCheckpointFixture();
  }, { enabled, scene, combined });
}

test('qualifying push sectors show signed cumulative differences and the named reference', async ({ page }) => {
  await mount(page);
  const row = page.locator('tr[data-driver="63"]');
  await expect(row.locator('.push-delta')).toHaveText(['Δ -0.008', 'Δ +0.357', '—']);
  await expect(row.locator('.push-delta-reference')).toHaveText('Against LEC 1:35.200 · Q1');
  await expect(page.locator('tr[data-driver="16"] .push-delta')).toHaveCount(0);
  await expect(row.locator('.push-delta[data-sector="2"]')).toHaveAttribute('aria-label', 'Cumulative difference after S2: +0.357 s');
  await page.evaluate(() => window.setCheckpointFixture({}, { state: 'completed', active: false, progress: 1, last_lap_time: 96.241 }));
  await expect(row.locator('.push-delta[data-sector="3"]')).toHaveText('Δ +1.041');
  await expect(row.locator('.push-label')).toContainText('1:36.241');
  const a11y = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(a11y.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
});

test('combined sector cells support sprint qualifying and remain readable on a narrow display', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await mount(page, { scene: 'sprint_qualifying', combined: true });
  const row = page.locator('tr[data-driver="63"]');
  await expect(row.locator('.push-delta')).toHaveText(['Δ -0.008', 'Δ +0.357', '—']);
  await expect(row.locator('.push-delta-reference')).toHaveText('Against LEC 1:35.200 · SQ1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const mode of ['dark', 'light']) {
  for (const combined of [false, true]) {
    test(`push differences use neutral signs while sector colors retain their meanings: ${mode}, ${combined ? 'minisectors' : 'sectors'}`, async ({ page }) => {
      await mount(page, { combined });
      await page.evaluate(mode => {
        const card = window.fixtureCard, entity = window.fixtureDemo.preview.entries[0].entities.driver_positions;
        card.setConfig({ ...card.config, appearance: { ...card.config.appearance, mode } });
        const source = card.hass.states[entity];
        card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { ...source, attributes: { ...source.attributes,
          drivers: source.attributes.drivers.map(driver => driver.racing_number === '63' ? { ...driver,
            sector_current_lap: 3,
            sectors: { state: 's2_done', current_lap: 3, current: {
              sector_1: { time: 25.692, lap: 3, source: 'current', personal_fastest: true, overall_fastest: false },
              sector_2: { time: 38.199, lap: 3, source: 'current', personal_fastest: false, overall_fastest: false },
              sector_3: { time: null, lap: 3, source: null },
            } },
          } : driver),
        } } } };
      }, mode);
      const row = page.locator('tr[data-driver="63"]');
      await expect(row.locator('.push-delta')).toHaveText(['Δ -0.008', 'Δ +0.357', '—']);
      await expect(row.locator('.signal.personal .time')).toHaveText('25.692');
      await expect(row.locator('.signal.timed .time')).toHaveText('38.199');
      const readColors = () => row.evaluate(node => {
        const color = element => { const style = getComputedStyle(element); return { color: style.color, background: style.backgroundColor }; };
        return { text: getComputedStyle(node).color,
          differences: [...node.querySelectorAll('.push-delta:not(.unknown)')].map(color),
          sectors: [...node.querySelectorAll('.signal')].map(color) };
      });
      const before = await readColors();
      expect(before.differences).toEqual([
        { color: before.text, background: 'rgba(0, 0, 0, 0)' },
        { color: before.text, background: 'rgba(0, 0, 0, 0)' },
      ]);
      expect(before.sectors[0].background).not.toBe(before.sectors[1].background);
      await page.evaluate(() => {
        window.setCheckpointFixture({ sector_1: 0 });
        const card = window.fixtureCard, entity = window.fixtureDemo.preview.entries[0].entities.driver_positions;
        const source = card.hass.states[entity];
        card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { ...source, attributes: { ...source.attributes,
          drivers: source.attributes.drivers.map(driver => driver.racing_number === '63' ? { ...driver,
            sectors: { ...driver.sectors, current: { ...driver.sectors.current,
              sector_1: { ...driver.sectors.current.sector_1, overall_fastest: true },
            } },
          } : driver),
        } } } };
      });
      await expect(row.locator('.push-delta')).toHaveText(['Δ 0.000', 'Δ +0.357', '—']);
      await expect(row.locator('.signal.overall .time')).toHaveText('25.692');
      const after = await readColors();
      expect(after.differences).toEqual(before.differences);
      expect(after.sectors[0].background).not.toBe(before.sectors[0].background);
      expect(after.sectors[0].background).not.toBe(before.sectors[1].background);
      expect(after.sectors[1]).toEqual(before.sectors[1]);
    });
  }
}

test('unavailable references and changes of attempt never show a saved difference', async ({ page }) => {
  await mount(page);
  const row = page.locator('tr[data-driver="63"]');
  for (const delta of [{ reference: null }, { status: 'unavailable' }, { lap: 4 }, { session_part: 2 }]) {
    await page.evaluate(delta => window.setCheckpointFixture(delta), delta);
    await expect(row.locator('.push-delta')).toHaveText(['—', '—', '—']);
    await expect(row.locator('.push-delta-reference')).toHaveText(delta.status === 'unavailable' ? 'Reference lap unavailable' : 'Waiting for a complete reference lap');
  }
  await page.evaluate(() => window.setCheckpointFixture({}, { lap: 1, progress: .1 }));
  await expect(row.locator('.push-delta')).toHaveText(['—', '—', '—']);
  await page.evaluate(() => window.setCheckpointFixture({ sector_1: 0 }, { progress: .4 }));
  await expect(row.locator('.push-delta')).toHaveText(['Δ 0.000', '—', '—']);
});

test('checkpoint differences stay absent without opt-in and during practice or races', async ({ page }) => {
  await mount(page, { enabled: false });
  await expect(page.locator('.push-delta')).toHaveCount(0);
  for (const scene of ['practice', 'race', 'sprint']) {
    await mount(page, { scene });
    await expect(page.locator('.push-delta')).toHaveCount(0);
    await expect(page.locator('.push-delta-reference')).toHaveCount(0);
  }
});

test('the visual editor saves the opt-in beneath Push laps and preserves independent module choices', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: false, config: { modules: [{ id: 'timing', type: 'timing' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const options = editor.getByRole('region', { name: 'Selected module', exact: true }).locator('details').filter({ has: page.locator('summary').filter({ hasText: /^Module options$/ }) });
  await options.locator('summary').click();
  const checkbox = editor.getByRole('checkbox', { name: 'Show difference to best lap', exact: true });
  await expect(checkbox).toHaveCount(0);
  await editor.getByLabel('Push laps', { exact: true }).selectOption('only');
  await expect(checkbox).not.toBeChecked();
  await checkbox.check();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.push_lap_deltas)).toBe(true);
  await editor.getByRole('button', { name: 'Duplicate module', exact: true }).click();
  expect(await page.evaluate(() => window.savedConfig.modules.map(module => module.options.push_lap_deltas))).toEqual([true, true]);
  await checkbox.uncheck();
  expect(await page.evaluate(() => window.savedConfig.modules.map(module => module.options.push_lap_deltas))).toEqual([false, true]);
  await editor.getByLabel('Push laps', { exact: true }).selectOption('off');
  await expect(checkbox).toHaveCount(0);
});
