const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

for (const language of ['en', 'fr']) {
test(`telemetry complete-recording explanation is visible by default and can be hidden in ${language}`, async ({ page }) => {
  await page.evaluate(language => window.mountModular({ language, scene: 'replay', config: {
    modules: [{ type: 'telemetry' }],
  } }), language);
  const telemetry = page.locator('f1-telemetry-view');
  await expect(telemetry.locator('svg.plot').first()).toBeVisible();
  const selected = await telemetry.evaluate(node => node.model.selected);
  expect(selected.length).toBeGreaterThan(0);
  await expect(page.getByText(/Analysis of the complete recording\./)).toBeVisible();
  await expect(page.getByText(/including laps beyond the current playback position/)).toBeVisible();
  await expect(page.getByText(/Lap windows use observed timing updates/)).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    const states = structuredClone(card.hass.states);
    for (const [key, value] of Object.entries(states)) {
      if (key.startsWith('media_player.') && key.includes('replay')) value.attributes.media_position = 0;
    }
    card.hass = { ...card.hass, states };
  });
  await expect(page.getByText(/including laps beyond the current playback position/)).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, modules: card.config.modules.map(module => ({ ...module, options: { ...module.options, show_explanation: false } })) });
  });
  await expect(page.getByText(/Analysis of the complete recording\./)).toHaveCount(0);
  await expect(page.getByText(/including laps beyond the current playback position/)).toHaveCount(0);
  await expect(page.getByText(/Lap windows use observed timing updates/)).toHaveCount(0);
  await expect(telemetry.locator('svg.plot').first()).toBeVisible();
  expect(await telemetry.evaluate(node => node.model.selected)).toEqual(selected);
});
}

test('No Spoiler removes retrospective telemetry and its sample details', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: {
    modules: [{ type: 'telemetry' }],
  } }));
  await page.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(page.locator('f1-telemetry-view table')).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.hass = { ...card.hass, states: { ...card.hass.states,
      'switch.f1_demo_spoilers': { state: 'on', attributes: {} },
    } };
  });
  await expect(page.getByText('Spoiler protection is active.')).toBeVisible();
  await expect(page.locator('f1-telemetry-view')).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCard.telemetry.resources.size)).toBe(0);
});

test('legacy telemetry labels complete-recording windows and hides its chart with No Spoiler', async ({ page }) => {
  await page.goto('/frontend-tests/fixture.html');
  await page.waitForFunction(() => typeof window.mountF1Element === 'function');
  await page.evaluate(async () => {
    await window.mountF1Element({ type: 'f1-weekend-hub-card', language: 'fr' });
    const card = document.querySelector('f1-weekend-hub-card');
    card.setConfig({ ...card.config, default_view: 'telemetry', no_spoiler_entity: 'input_boolean.telemetry_spoiler' });
    card._activeView = 'telemetry';
    card._receiveSnapshot({ status: 'ready', provider: 'replay', phase: 'live', session_id: 'replay-test',
      replay: { session_id: 'replay-test', state: 'paused', position_ms: 0 },
      capabilities: { telemetry_compare: 'ready' }, drivers: [{ driver_number: 4, tla: 'NOR' }],
      timeline: { events: [] },
    });
    card._telemetry = { series: [{ driver_number: 4, lap_number: 12, sample_count: 2,
      samples: [{ time_s: 0, distance: 0, speed: 200 }, { time_s: 1, distance: 60, speed: 210 }],
    }] };
    card.hass = { ...card.hass, states: { ...card.hass.states,
      'input_boolean.telemetry_spoiler': { state: 'off', attributes: {} },
    } };
    await card.updateComplete;
  });
  const card = page.locator('f1-weekend-hub-card');
  await expect(card.locator('svg.wh-chart')).toBeVisible();
  await expect(card.getByText(/Analysis of the complete recording\./)).toBeVisible();
  await expect(card.getByText(/Lap windows use observed timing updates/)).toBeVisible();
  await expect(card.getByText(/not verified finish-line crossings/)).toBeVisible();
  await page.evaluate(() => {
    const card = document.querySelector('f1-weekend-hub-card');
    card.hass = { ...card.hass, states: { ...card.hass.states,
      'input_boolean.telemetry_spoiler': { state: 'on', attributes: {} },
    } };
  });
  await expect(card.locator('.wh-spoiler')).toBeVisible();
  await expect(card.locator('svg.wh-chart')).toHaveCount(0);
  await expect(card.locator('.wh-telemetry-form')).toHaveCount(0);
});
