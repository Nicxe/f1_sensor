const { test, expect } = require('@playwright/test');

test('Replay Control keeps the selected session when the unknown option disappears', async ({ page }) => {
  await page.goto('/frontend-tests/fixture.html');
  await page.waitForFunction(() => typeof window.mountF1Element === 'function');
  await page.evaluate(async () => {
    await window.mountF1Element({ type: 'f1-replay-control-card' });
    const card = document.querySelector('f1-replay-control-card');
    window.updateReplaySelectFixture = async (state, options, status = 'idle') => {
      card.hass = {
        ...card.hass,
        states: {
          ...card.hass.states,
          'select.f1_replay_session': { state, attributes: { options } },
          'sensor.f1_replay_status': { state: status, attributes: { selected_session: state } },
        },
      };
      await card.updateComplete;
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    };
    window.replaySessionOptions = [
      'Italian Grand Prix - Practice 2',
      'Italian Grand Prix - Practice 1',
      ...Array.from({ length: 66 }, (_, index) => `Archived session ${index + 1}`),
    ];
    await window.updateReplaySelectFixture('No sessions for 2026', []);
    await window.updateReplaySelectFixture('unknown', window.replaySessionOptions);
  });
  const card = page.locator('f1-replay-control-card');
  const session = card.locator('.rc-select-field.session select').first();
  await expect(session).toHaveValue('unknown');
  await page.evaluate(() => window.updateReplaySelectFixture(
    'Italian Grand Prix - Practice 2', window.replaySessionOptions, 'selected',
  ));
  await expect(card.locator('.rc-subtitle')).toHaveText('Italian Grand Prix - Practice 2');
  await expect(session).toHaveValue('Italian Grand Prix - Practice 2');
  for (const state of ['loading', 'ready']) {
    await page.evaluate((status) => window.updateReplaySelectFixture(
      'Italian Grand Prix - Practice 2', window.replaySessionOptions, status,
    ), state);
    await expect(session).toHaveValue('Italian Grand Prix - Practice 2');
  }
});
