const { test, expect } = require('@playwright/test');

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6vR8AAAAASUVORK5CYII=', 'base64');

for (const phase of ['initial load', 'periodic refresh']) {
  test(`metadata timeout during ${phase} offers retry and recovers without background retries`, async ({ page }) => {
    await page.clock.install();
    let requests = 0, stalled = phase === 'initial load';
    const now = Math.floor(Date.now() / 1000 / 600) * 600;
    const frame = time => ({ time, path: `/v2/radar/${time}` });
    const metadata = { host: 'https://api.librewxr.net', generated: now,
      radar: { past: [frame(now - 600), frame(now)], nowcast: [frame(now + 600)] } };
    await page.route('https://api.librewxr.net/**', async route => {
      if (route.request().url().endsWith('.json')) {
        requests++;
        if (!stalled) await route.fulfill({ json: metadata });
      } else await route.fulfill({ contentType: 'image/png', body: png });
    });
    await page.route('https://tile.openstreetmap.org/**', route => route.fulfill({ contentType: 'image/png', body: png }));
    page.on('pageerror', error => { throw error; });
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.evaluate(async () => {
      await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/radar-view.js');
      const view = document.createElement('f1-radar-view');
      view.model = { circuits: [{ id: 'baku', name: 'Baku', lat: 40.3725, lon: 49.8533 }], selectedId: 'baku' };
      view.module = { options: { zoom: 13, show_explanation: false } };
      view.language = 'en';
      document.querySelector('#root').replaceChildren(view);
    });
    const view = page.locator('f1-radar-view');
    await expect.poll(() => requests).toBe(1);
    if (phase === 'periodic refresh') {
      await expect(view.locator('.place')).toBeVisible();
      stalled = true;
      await page.clock.fastForward(5 * 60 * 1000);
      await expect.poll(() => requests).toBe(2);
    }
    await page.clock.fastForward(15000);
    await expect(view.getByRole('button', { name: 'Try again', exact: true })).toBeVisible();
    await expect(view.locator('.precipitation')).toHaveCount(0);
    await expect(view.locator('time')).toHaveCount(0);
    const before = requests;
    await page.clock.fastForward(5 * 60 * 1000);
    expect(requests).toBe(before);
    stalled = false;
    await view.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(view.locator('.place')).toBeVisible();
    await expect(view.locator('time')).toHaveAttribute('datetime', new Date(now * 1000).toISOString());
    expect(requests).toBe(before + 1);
    await page.clock.fastForward(5 * 60 * 1000);
    await expect.poll(() => requests).toBe(before + 2);
    await expect(view.locator('.place')).toBeVisible();
  });
}
