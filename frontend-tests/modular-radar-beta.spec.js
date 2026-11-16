const { test, expect } = require('@playwright/test');

const instant = new Date('2026-11-12T10:00:00Z');
const time = instant.getTime() / 1000;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6vR8AAAAASUVORK5CYII=', 'base64');
const metadata = () => ({
  host: 'https://api.librewxr.net', generated: time,
  radar: {
    past: [time - 600, time].map(time => ({ time, path: `/v2/radar/${time}` })),
    nowcast: [{ time: time + 600, path: `/v2/radar/${time + 600}` }],
  },
});

async function setup(page, { count = 1, language = 'en', metadataResponse, tileResponse } = {}) {
  const requests = { metadata: 0, radar: 0, base: 0 };
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.clock.install({ time: instant });
  await page.route('https://api.librewxr.net/**', async route => {
    if (route.request().url().endsWith('/public/weather-maps.json')) {
      requests.metadata++;
      if (metadataResponse) await metadataResponse(route);
      else await route.fulfill({ json: metadata() });
    } else {
      requests.radar++;
      if (tileResponse) await tileResponse(route, 'radar');
      else await route.fulfill({ contentType: 'image/png', body: png });
    }
  });
  await page.route('https://tile.openstreetmap.org/**', async route => {
    requests.base++;
    if (tileResponse) await tileResponse(route, 'base');
    else await route.fulfill({ contentType: 'image/png', body: png });
  });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(async ({ count, language }) => {
    await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/radar-view.js');
    const root = document.querySelector('#root');
    root.style.display = 'grid';
    root.style.gridTemplateColumns = `repeat(${count}, minmax(0, 1fr))`;
    root.style.gap = '16px';
    window.radarViews = Array.from({ length: count }, () => {
      const view = document.createElement('f1-radar-view');
      view.model = { circuits: [{ id: 'baku', name: 'Baku', lat: 40.3725, lon: 49.8533 }], selectedId: 'baku' };
      view.module = { options: { zoom: 12, show_explanation: false } };
      view.language = language;
      return view;
    });
    root.replaceChildren(...window.radarViews);
  }, { count, language });
  return { requests, errors };
}

test('disconnecting one card during a shared cold load preserves the remaining consumer', async ({ page }) => {
  const pending = [];
  const { requests, errors } = await setup(page, {
    count: 2,
    metadataResponse: async route => { pending.push(route); },
  });
  await expect(page.locator('f1-radar-view .notice')).toHaveCount(2);
  await expect.poll(() => requests.base).toBe(18);
  expect(requests.metadata).toBe(1);
  await page.evaluate(() => window.radarViews[0].remove());
  await pending[0].fulfill({ json: metadata() });
  await expect(page.locator('f1-radar-view .place')).toHaveText('Baku');
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  expect(requests.metadata).toBe(1);
  expect(requests.radar).toBe(9);
  await page.evaluate(() => document.querySelector('#root').prepend(window.radarViews[0]));
  await expect(page.locator('f1-radar-view .place')).toHaveCount(2);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(18);
  expect(requests.metadata).toBe(1);
  expect(errors).toEqual([]);
});

test('synthetic document visibility pauses every consumer, stops timers and resumes without autoplay', async ({ page }) => {
  const { requests, errors } = await setup(page, { count: 2 });
  await expect(page.locator('f1-radar-view .place')).toHaveCount(2);
  for (const view of await page.locator('f1-radar-view').all()) {
    await view.getByRole('button', { name: 'Play', exact: true }).click();
  }
  // This tests the document lifecycle handler; it is not a real background-tab runtime test.
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('f1-radar-view img')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Pause', exact: true })).toHaveCount(0);
  const paused = { ...requests };
  await page.clock.fastForward(11 * 60 * 1000);
  expect(requests).toEqual(paused);
  await page.evaluate(() => {
    delete document.hidden;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(page.locator('f1-radar-view .place')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Play', exact: true })).toHaveCount(2);
  expect(requests.metadata).toBe(paused.metadata + 1);
  const resumed = { ...requests };
  await page.clock.fastForward(5000);
  expect(requests).toEqual(resumed);
  expect(errors).toEqual([]);
});

for (const invalid of ['denied', 'rate-limited', 'invalid JSON', 'foreign host']) {
  test(`an initial ${invalid} metadata response clears imagery and recovers only on retry`, async ({ page }) => {
    let failed = true;
    const { requests, errors } = await setup(page, { metadataResponse: async route => {
      if (!failed) return route.fulfill({ json: metadata() });
      if (invalid === 'denied') return route.fulfill({ status: 403 });
      if (invalid === 'rate-limited') return route.fulfill({ status: 429, headers: { 'retry-after': '60' } });
      if (invalid === 'invalid JSON') return route.fulfill({ contentType: 'application/json', body: '{broken' });
      return route.fulfill({ json: { ...metadata(), host: 'https://untrusted.invalid' } });
    } });
    const view = page.locator('f1-radar-view');
    await expect(view.getByRole('button', { name: 'Try again', exact: true })).toBeVisible();
    await expect(view.locator('img')).toHaveCount(0);
    await expect(view.locator('time')).toHaveCount(0);
    await expect(view.getByRole('slider')).toBeDisabled();
    expect(requests.radar).toBe(0);
    const stopped = { ...requests };
    await page.clock.fastForward(10 * 60 * 1000);
    expect(requests).toEqual(stopped);
    failed = false;
    await view.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(view.locator('.place')).toHaveText('Baku');
    await expect(view.locator('time')).toHaveAttribute('datetime', new Date(time * 1000).toISOString());
    expect(requests.metadata).toBe(2);
    expect(errors).toEqual([]);
  });
}

for (const layer of ['base', 'radar']) {
  test(`a stalled ${layer} layer times out, clears partial imagery and can be retried`, async ({ page }) => {
    let stalled = true;
    const { requests, errors } = await setup(page, { tileResponse: async (route, requestedLayer) => {
      if (stalled && requestedLayer === layer) return;
      await route.fulfill({ contentType: 'image/png', body: png });
    } });
    const view = page.locator('f1-radar-view');
    await expect.poll(() => requests[layer]).toBe(9);
    await page.clock.fastForward(15000);
    await expect(view.getByRole('button', { name: 'Try again', exact: true })).toBeVisible();
    await expect(view.locator('img')).toHaveCount(0);
    await expect(view.locator('time')).toHaveCount(0);
    const stopped = { ...requests };
    await page.clock.fastForward(60000);
    expect(requests).toEqual(stopped);
    stalled = false;
    await view.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(view.locator('.place')).toHaveText('Baku');
    await expect(view.getByRole('button', { name: 'Play', exact: true })).toBeEnabled();
    expect(errors).toEqual([]);
  });
}

for (const invalid of ['denied', 'invalid JSON']) {
  test(`a shared periodic ${invalid} metadata response clears all cards until each is retried`, async ({ page }) => {
    let failed = false;
    const { requests, errors } = await setup(page, {
      count: 2,
      metadataResponse: async route => {
        if (!failed) return route.fulfill({ json: metadata() });
        if (invalid === 'denied') return route.fulfill({ status: 403 });
        return route.fulfill({ contentType: 'application/json', body: '{broken' });
      },
    });
    const views = page.locator('f1-radar-view');
    await expect(views.locator('.place')).toHaveCount(2);
    expect(requests.metadata).toBe(1);
    failed = true;
    await page.clock.fastForward(5 * 60 * 1000);
    await expect(views.getByRole('button', { name: 'Try again', exact: true })).toHaveCount(2);
    await expect(views.locator('img')).toHaveCount(0);
    await expect(views.locator('time')).toHaveCount(0);
    expect(requests.metadata).toBe(2);
    const stopped = { ...requests };
    await page.clock.fastForward(10 * 60 * 1000);
    expect(requests).toEqual(stopped);
    failed = false;
    await views.nth(0).getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(views.nth(0).locator('.place')).toHaveText('Baku');
    await expect(views.nth(1).getByRole('button', { name: 'Try again', exact: true })).toBeVisible();
    expect(requests.metadata).toBe(3);
    await views.nth(1).getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(views.locator('.place')).toHaveCount(2);
    expect(requests.metadata).toBe(3);
    expect(errors).toEqual([]);
  });
}

for (const invalid of ['non-image response', 'undecodable image']) {
  test(`${invalid} produces an error rather than a clear map`, async ({ page }) => {
    let failed = true;
    const { errors } = await setup(page, { tileResponse: async (route, layer) => {
      if (failed && layer === 'radar') {
        return route.fulfill({ contentType: invalid === 'non-image response' ? 'text/html' : 'image/png', body: 'not an image' });
      }
      await route.fulfill({ contentType: 'image/png', body: png });
    } });
    const view = page.locator('f1-radar-view');
    await expect(view.getByRole('button', { name: 'Try again', exact: true })).toBeVisible();
    await expect(view.locator('img')).toHaveCount(0);
    await expect(view.locator('time')).toHaveCount(0);
    failed = false;
    await view.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(view.locator('.place')).toHaveText('Baku');
    expect(errors).toEqual([]);
  });
}

test('sparse regional translations keep translated controls and English radar safety information', async ({ page }) => {
  // Independent translation fixture: Weblate may translate any real target key later.
  await page.route('**/localization/available-locales.json*', route => route.fulfill({ json: ['en', 'sv'] }));
  await page.route('**/localization/locales/sv.json*', route => route.fulfill({ json: { 'modular.radar_play': 'Translated playback fixture' } }));
  const { errors } = await setup(page, { language: 'sv-SE' });
  const view = page.locator('f1-radar-view');
  await expect(view.getByRole('button', { name: 'Translated playback fixture', exact: true })).toBeEnabled();
  await expect(view.locator('.data-quality')).toContainText('Local coverage unverified. A clear map does not confirm dry weather.');
  await expect(view.locator('.frame-quality')).toContainText('Latest image: 0 min old');
  await expect(view.getByRole('slider')).toHaveAccessibleName('Precipitation timeline');
  await view.getByRole('slider').fill('2');
  await expect(view.locator('.data-quality')).toContainText('Extrapolation / model');
  expect(errors).toEqual([]);
});

test('narrow touch controls and keyboard timeline keep frame labels, zoom and data quality usable', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  const { errors } = await setup(page);
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.place')).toHaveText('Baku');
  await view.getByRole('button', { name: 'Play', exact: true }).tap();
  await expect(view.locator('.badge')).toHaveText('Forecast');
  await view.getByRole('button', { name: 'Pause', exact: true }).tap();
  const slider = view.getByRole('slider');
  await slider.focus();
  await slider.press('Home');
  await expect(view.locator('time')).toHaveAttribute('datetime', new Date((time - 600) * 1000).toISOString());
  await expect(slider).toHaveAttribute('aria-valuetext', /[−-]10 min/);
  await view.getByRole('button', { name: 'Latest', exact: true }).tap();
  await expect(view.locator('time')).toHaveAttribute('datetime', new Date(time * 1000).toISOString());
  await view.getByRole('button', { name: 'Zoom in', exact: true }).tap();
  await view.getByRole('button', { name: 'Zoom in', exact: true }).tap();
  await expect(view.getByRole('button', { name: 'Zoom in', exact: true })).toBeDisabled();
  await expect(view.locator('.place')).toHaveText('Baku');
  await expect(view.locator('.data-quality')).toBeVisible();
  await expect(view.getByRole('group', { name: 'Image intensity · dBZ', exact: true })).toBeVisible();
  expect(await view.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('compact narrow maps keep map attribution visible, clickable and clear of the scale', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  const { errors } = await setup(page);
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.place')).toHaveText('Baku');
  await expect(view.locator('.explanation')).toHaveCount(0);
  const map = view.locator('.map');
  const credit = map.getByRole('link', { name: /OpenStreetMap contributors/ });
  await expect(credit).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright');
  await expect(credit).toBeVisible();
  await credit.click({ trial: true });
  const mapBox = await map.boundingBox();
  const creditBox = await credit.boundingBox();
  const scaleBox = await map.locator('.scale').boundingBox();
  expect(creditBox.x).toBeGreaterThanOrEqual(mapBox.x);
  expect(creditBox.y).toBeGreaterThanOrEqual(mapBox.y);
  expect(creditBox.x + creditBox.width).toBeLessThanOrEqual(mapBox.x + mapBox.width);
  expect(creditBox.y + creditBox.height).toBeLessThanOrEqual(mapBox.y + mapBox.height);
  expect(scaleBox.y + scaleBox.height).toBeLessThanOrEqual(creditBox.y);
  expect(errors).toEqual([]);
});
