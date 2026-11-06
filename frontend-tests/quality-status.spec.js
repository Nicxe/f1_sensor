const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('replay explains identity conflicts and old cache formats, then clears the error on recovery', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ scene: 'replay', config: { modules: [{ type: 'replay' }] } });
    const { hass, preview } = window.fixtureDemo;
    const attrs = hass.states[preview.entries[0].entities.replay_status].attributes;
    attrs.download_error = 'load failed'; attrs.download_error_code = 'archive_identity_conflict';
    window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
  });
  await expect(page.getByRole('alert')).toContainText('archive contains data for another session');
  await page.evaluate(() => {
    const { hass, preview } = window.fixtureDemo;
    hass.states[preview.entries[0].entities.replay_status].attributes.download_error_code = 'cache_normalization_incompatible';
    window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
  });
  await expect(page.getByRole('alert')).toContainText('older timing format');
  await page.evaluate(() => {
    const { hass, preview } = window.fixtureDemo;
    const attrs = hass.states[preview.entries[0].entities.replay_status].attributes;
    attrs.download_error = null; attrs.download_error_code = null; attrs.archive_identity = { status: 'missing' };
    window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
  });
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByText('The archive does not include enough session identity data to verify this recording.')).toBeVisible();
});

test('prediction waiting reasons preserve published standings and follow the spoiler gate', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ language: 'sv', config: { modules: [{ type: 'standings', fields: ['driver', 'points', 'predicted_points'] }] } });
    const { hass, preview } = window.fixtureDemo, entry = preview.entries[0];
    hass.states[entry.entities.championship_prediction_drivers].attributes.prediction_status = 'waiting_for_session';
    window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
  });
  await expect(page.getByText('Waiting for session identity before showing championship projections.')).toBeVisible();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  for (const [status, text] of [
    ['waiting_for_prediction', 'Race or Sprint identified. Waiting for championship prediction data.'],
    ['not_applicable', 'Championship projections are available during Race and Sprint sessions.'],
  ]) {
    await page.evaluate(status => {
      const { hass, preview } = window.fixtureDemo, entry = preview.entries[0];
      hass.states[entry.entities.championship_prediction_drivers].attributes.prediction_status = status;
      window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
    }, status);
    await expect(page.getByText(text, { exact: true })).toBeVisible();
  }
  await page.setViewportSize({ width: 360, height: 800 });
  await page.emulateMedia({ forcedColors: 'active' });
  expect((await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations).toEqual([]);
  await page.evaluate(() => {
    const { hass, preview } = window.fixtureDemo;
    hass.states[preview.entries[0].global_entities.no_spoiler_mode].state = 'on';
    window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
  });
  await expect(page.locator('tbody tr')).toHaveCount(0);
  await expect(page.getByText('Championship projections are available during Race and Sprint sessions.')).toHaveCount(0);
});

test('an accepted token without positions is distinct from an authentication failure or normal idle', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'map' }] } });
    const demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.preview.map = { ...demo.preview.map, source: 'live', status: 'no_position_data', drivers: {} };
    entry.entities.f1tv_token_status = 'sensor.token';
    demo.hass.states['sensor.token'] = { state: 'valid', attributes: {} };
    window.fixtureCard.hass = { ...demo.hass, states: { ...demo.hass.states } };
  });
  await expect(page.getByText('The token is accepted, but no car positions have been received. Position access and session coverage are not confirmed.')).toBeVisible();
  await page.evaluate(() => {
    const demo = window.fixtureDemo;
    demo.hass.states['sensor.token'].state = 'expired';
    window.fixtureCard.hass = { ...demo.hass, states: { ...demo.hass.states } };
  });
  await expect(page.getByText('F1TV access needs attention. Check the F1 Sensor authentication settings.')).toBeVisible();
  await page.evaluate(() => {
    const demo = window.fixtureDemo;
    demo.preview.map.status = 'no_session';
    window.fixtureCard.hass = { ...demo.hass, states: { ...demo.hass.states } };
  });
  await expect(page.getByText('Waiting for the next session.', { exact: true })).toBeVisible();
  await expect(page.getByText('F1TV access needs attention. Check the F1 Sensor authentication settings.')).toHaveCount(0);
});

test('direct data explains unavailable and stale states without inventing an inactive session', async ({ page }) => {
  await page.evaluate(async () => {
    window.mountModular({ config: { modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    await card.updateComplete;
    entry.data_api = { enabled: ['driver_positions'] };
    const payload = { ...demo.hass.states[entry.entities.driver_positions] };
    window.qualityResource = { entryId: entry.entry_id, key: 'driver_positions', state: { status: 'ready', data: {
      status: 'unavailable', reason: 'source_inactive', source: 'live', generation: 'quality-1', payload,
    } } };
    card.cardDataResources.set('quality', window.qualityResource); card.revision++;
  });
  await expect(page.getByText('The data source is inactive. Current session data is not available.')).toBeVisible();
  for (const [status, reason, message] of [
    ['loading', 'waiting_for_data', 'Waiting for current data.'],
    ['unsupported', 'unsupported_dataset', 'This function is not supported by the selected data source.'],
    ['stale', 'source_update_failed', 'The source update failed. Displayed values are the last known data.'],
  ]) {
    await page.evaluate(({ status, reason }) => {
      Object.assign(window.qualityResource.state.data, { status, reason }); window.fixtureCard.revision++;
    }, { status, reason });
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    if (status === 'stale') await expect(page.locator('tbody tr').first()).toBeVisible();
  }
  await page.evaluate(() => {
    Object.assign(window.qualityResource.state.data, { status: 'ready', reason: null }); window.fixtureCard.revision++;
  });
  await expect(page.getByText('The source update failed. Displayed values are the last known data.')).toHaveCount(0);
  await expect(page.locator('tbody tr').first()).toBeVisible();
});

test('weather uses explicit source status before its generic unavailable explanation', async ({ page }) => {
  await page.evaluate(async () => {
    window.mountModular({ config: { modules: [{ type: 'weather', options: { content: 'current_conditions' } }] } });
    const card = window.fixtureCard, entry = window.fixtureDemo.preview.entries[0];
    await card.updateComplete;
    entry.data_api = { enabled: ['weather'] };
    window.weatherQualityResource = { entryId: entry.entry_id, key: 'weather', state: { status: 'ready', data: {
      status: 'loading', reason: 'waiting_for_data', source: 'static', generation: 'quality-1', payload: null,
    } } };
    card.cardDataResources.set('weather-quality', window.weatherQualityResource); card.revision++;
  });
  await expect(page.getByText('Waiting for current data.', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    Object.assign(window.weatherQualityResource.state.data, { status: 'unsupported', reason: 'unsupported_dataset' });
    window.fixtureCard.revision++;
  });
  await expect(page.getByText('This function is not supported by the selected data source.', { exact: true })).toBeVisible();
});

for (const protection of ['on', 'unknown']) {
  test(`an old ready Race Control message does not become stale by age and ${protection} spoiler protection hides even a frozen view`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-11-06T12:00:00Z'));
    await page.evaluate(async () => {
      window.mountModular({ config: {
        context: { show_freeze_control: true },
        modules: [{ type: 'race_control', options: { presentation: 'list' } }],
      } });
      const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
      const event = {
        event_id: 'old-ready-control', utc: '2026-01-01T12:00:00Z',
        category: 'Flag', flag: 'CLEAR', message: 'TRACK CLEAR AFTER OLD OBSERVATION',
      };
      card.previewData = { ...demo.preview, now: Date.parse('2026-11-06T12:00:00Z'), events: [event] };
      await card.updateComplete;
      entry.data_api = { enabled: ['race_control'] };
      card.cardDataResources.set('old-ready-control', {
        entryId: entry.entry_id, key: 'race_control', state: { status: 'ready', data: {
          status: 'ready', reason: null, source: 'live', generation: 'quality-1',
          timestamps: { received_at: event.utc },
          payload: { state: event.message, attributes: event },
        } },
      });
      card.revision++;
    });
    const control = page.getByRole('region', { name: 'Race Control', exact: true });
    const message = 'TRACK CLEAR AFTER OLD OBSERVATION';
    await expect(control.getByText(message, { exact: true })).toBeVisible();
    await expect(control.getByText('The source update failed. Displayed values are the last known data.', { exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeVisible();
    await page.evaluate(protection => {
      const { hass, preview } = window.fixtureDemo;
      hass.states[preview.entries[0].global_entities.no_spoiler_mode].state = protection;
      window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
    }, protection);
    await expect(control.getByText(protection === 'on'
      ? 'Spoiler protection is active.'
      : 'Spoiler status cannot be verified. Refresh F1 Sensor before showing sensitive data.', { exact: true })).toBeVisible();
    await expect(page.getByText(message, { exact: true })).toHaveCount(0);
    await expect(control.locator('.events li')).toHaveCount(0);
    await expect(page.locator(`[title*="${message}"], [aria-label*="${message}"]`)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toHaveCount(0);
    await page.evaluate(() => {
      const { hass, preview } = window.fixtureDemo;
      hass.states[preview.entries[0].global_entities.no_spoiler_mode].state = 'off';
      window.fixtureCard.hass = { ...hass, states: { ...hass.states } };
    });
    await expect(control.getByText(message, { exact: true })).toBeVisible();
    await expect(control.getByText('The source update failed. Displayed values are the last known data.', { exact: true })).toHaveCount(0);
  });
}
