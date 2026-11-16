const { test, expect } = require('@playwright/test');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6vR8AAAAASUVORK5CYII=', 'base64');
const circuit = { id: 'baku', name: 'Baku', lat: 40.3725, lon: 49.8533 };

async function setup(page, { model = {}, options = { zoom: 12 } } = {}) {
  const requests = { metadata: 0, tiles: 0, base: 0 };
  const now = Math.floor(Date.now() / 1000 / 600) * 600;
  const frame = time => ({ time, path: `/v2/radar/${time}` });
  const metadata = { host: 'https://api.librewxr.net', generated: now,
    radar: { past: [frame(now - 600), frame(now)], nowcast: [frame(now + 600)] } };
  await page.route('https://api.librewxr.net/**', async route => {
    if (route.request().url().endsWith('.json')) { requests.metadata++; await route.fulfill({ json: metadata }); }
    else { requests.tiles++; await route.fulfill({ contentType: 'image/png', body: png }); }
  });
  await page.route('https://tile.openstreetmap.org/**', async route => { requests.base++; await route.fulfill({ contentType: 'image/png', body: png }); });
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(async ({ circuit, model, options }) => {
    await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/radar-view.js');
    const view = document.createElement('f1-radar-view');
    view.model = { circuits: [circuit], selectedId: circuit.id, ...model };
    view.module = { options };
    view.language = 'en';
    document.querySelector('#root').replaceChildren(view);
    window.radar = view;
  }, { circuit, model, options });
  return { requests, now, metadata };
}

test('renders bounded geographically centered layers and separates forecast from recent data', async ({ page }) => {
  const { requests, now } = await setup(page, { options: { zoom: 12 }, model: { circuits: [
    { id: 'albert_park', name: 'Albert Park', lat: -37.8497, lon: 144.968 }, circuit,
  ] } });
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.precipitation')).toHaveCount(9);
  await expect(view.locator('time')).toHaveAttribute('datetime', new Date(now * 1000).toISOString());
  await expect(view.getByRole('combobox')).toHaveValue('baku');
  await expect(view.getByRole('button', { name: 'Zoom in', exact: true })).toBeEnabled();
  expect(requests).toEqual({ metadata: 1, tiles: 9, base: 9 });
  await view.getByRole('slider').fill('2');
  await expect(view.locator('.badge')).toHaveText('Forecast');
  await expect(view.locator('time')).toHaveAttribute('datetime', new Date((now + 600) * 1000).toISOString());
  expect(requests.tiles).toBe(18);
  await expect(view.getByText(/blank layer does not confirm dry weather/)).toBeVisible();
  await expect(view.getByText(/satellite precipitation estimates/)).toBeVisible();
});

test('keeps the displayed frame and timestamp together while the next frame loads', async ({ page }) => {
  const { now } = await setup(page);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  const pending = [];
  await page.route(`https://api.librewxr.net/v2/radar/${now + 600}/**`, route => { pending.push(route); });
  await page.getByRole('slider').fill('2');
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  await expect(page.locator('f1-radar-view time')).toHaveAttribute('datetime', new Date(now * 1000).toISOString());
  await expect(page.locator('f1-radar-view .place')).toBeVisible();
  await expect.poll(() => pending.length).toBe(9);
  for (const route of pending) await route.fulfill({ contentType: 'image/png', body: png });
  await expect(page.locator('f1-radar-view .badge')).toHaveText('Forecast');
});

test('periodic metadata refresh retains the displayed timestamp while a shifted catalog loads', async ({ page }) => {
  await page.clock.install();
  const { now, metadata, requests } = await setup(page);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  const pending = [];
  await page.route(`https://api.librewxr.net/v2/radar/${now + 600}/**`, route => { pending.push(route); });
  const frame = time => ({ time, path: `/v2/radar/${time}` });
  metadata.generated = now + 600;
  metadata.radar = { past: [frame(now), frame(now + 600)], nowcast: [frame(now + 1200)] };
  await page.clock.fastForward(10 * 60 * 1000);
  await expect.poll(() => pending.length).toBe(9);
  expect(requests.metadata).toBe(2);
  expect(await page.evaluate(() => window.radar.metadata.frames[1].time)).toBe(now + 600);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  await expect(page.locator('f1-radar-view time')).toHaveAttribute('datetime', new Date(now * 1000).toISOString());
  for (const route of pending) await route.fulfill({ contentType: 'image/png', body: png });
  await expect(page.locator('f1-radar-view time')).toHaveAttribute('datetime', new Date((now + 600) * 1000).toISOString());
  await page.evaluate(() => window.radar.remove());
  expect(await page.evaluate(() => window.radar.displayFrame)).toBe(null);
  expect(await page.evaluate(() => window.radar.radarImages.length)).toBe(0);
});

test('tile failures clear the map and require a user retry rather than retrying on every model update', async ({ page }) => {
  await setup(page, { options: { zoom: 12, show_explanation: false } });
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  let failures = 0;
  await page.route('https://api.librewxr.net/v2/radar/**', async route => { failures++; await route.fulfill({ status: 503 }); });
  await page.getByRole('slider').fill('0');
  await expect(page.getByText(/map could not be loaded/)).toBeVisible();
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(0);
  const previous = failures;
  await page.evaluate(async () => {
    for (let index = 0; index < 3; index++) { window.radar.model = { ...window.radar.model }; await window.radar.updateComplete; }
  });
  expect(failures).toBe(previous);
  await page.unroute('https://api.librewxr.net/v2/radar/**');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
});

for (const mode of ['blocked', 'demo']) test(`${mode} mode performs no external requests`, async ({ page }) => {
  const { requests } = await setup(page, { model: { [mode]: true } });
  await expect(page.getByRole('slider')).toBeDisabled();
  expect(requests).toEqual({ metadata: 0, tiles: 0, base: 0 });
});

test('hidden and disconnected views stop playback, release images, and resume safely', async ({ page }) => {
  const { requests } = await setup(page);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  await page.getByRole('button', { name: 'Play', exact: true }).click();
  await page.evaluate(() => { window.radar.style.display = 'none'; });
  await expect.poll(() => page.evaluate(() => window.radar._key)).toBe(null);
  expect(await page.evaluate(() => window.radar.playing)).toBe(false);
  const previous = requests.tiles;
  await page.evaluate(() => { window.radar.remove(); });
  expect(await page.evaluate(() => window.radar.radarImages.length)).toBe(0);
  expect(requests.tiles).toBe(previous);
  await page.evaluate(() => { window.radar.style.display = ''; document.querySelector('#root').append(window.radar); });
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  expect(requests.metadata).toBe(1);
});

test('playback advances frames and pause keeps the selected frame stable', async ({ page }) => {
  await setup(page);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  await page.getByRole('button', { name: 'Play', exact: true }).click();
  await expect(page.locator('f1-radar-view .badge')).toHaveText('Forecast');
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  expect(await page.evaluate(() => window.radar.playing)).toBe(false);
  expect(await page.evaluate(() => window.radar.frameIndex)).toBe(2);
});

test('hiding the document aborts pending frame requests and removes displayed current weather', async ({ page }) => {
  const { now } = await setup(page);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  const pending = [];
  await page.route(`https://api.librewxr.net/v2/radar/${now + 600}/**`, route => { pending.push(route); });
  await page.getByRole('slider').fill('2');
  await expect.poll(() => pending.length).toBe(9);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(await page.evaluate(() => window.radar._frameController.signal.aborted)).toBe(true);
  expect(await page.evaluate(() => window.radar.active)).toBe(false);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(0);
  await expect(page.locator('f1-radar-view time')).toHaveCount(0);
});

test('OSM receives the genuine browser origin despite HA no-referrer without changing radar or caching policy', async ({ page }) => {
  const requests = [];
  page.on('request', request => {
    if (/^https:\/\/(tile\.openstreetmap\.org|api\.librewxr\.net)\//.test(request.url())) requests.push(request);
  });
  await page.route('**/frontend-tests/modular.html', async route => {
    const response = await route.fetch();
    await route.fulfill({ response, headers: { ...response.headers(), 'referrer-policy': 'no-referrer' } });
  });
  await page.addInitScript(() => {
    const original = window.fetch;
    window.radarFetchOptions = [];
    window.fetch = (url, options) => {
      if (/^https:\/\/(tile\.openstreetmap\.org|api\.librewxr\.net)\//.test(String(url))) {
        window.radarFetchOptions.push({ url: String(url), referrerPolicy: options?.referrerPolicy, cache: options?.cache });
      }
      return original(url, options);
    };
  });
  await setup(page);
  await expect(page.locator('f1-radar-view .precipitation')).toHaveCount(9);
  const base = requests.filter(request => request.url().includes('tile.openstreetmap.org'));
  const radar = requests.filter(request => request.url().includes('api.librewxr.net'));
  expect(base).toHaveLength(9);
  expect(base.every(request => request.headers().referer === 'http://127.0.0.1:4173/')).toBe(true);
  expect(radar.every(request => !request.headers().referer)).toBe(true);
  const options = await page.evaluate(() => window.radarFetchOptions);
  expect(options.filter(item => item.url.includes('tile.openstreetmap.org')).every(item => item.referrerPolicy === 'strict-origin-when-cross-origin')).toBe(true);
  expect(options.filter(item => item.url.includes('api.librewxr.net')).every(item => item.referrerPolicy === undefined)).toBe(true);
  expect(options.every(item => item.cache === undefined)).toBe(true);
});


test('close view overlays the geographic circuit, scales native weather parents and reports image cadence', async ({ page }) => {
  const urls = [];
  page.on('request', request => { if (/^https:\/\/(tile.openstreetmap.org|api.librewxr.net)\//.test(request.url())) urls.push(request.url()); });
  await setup(page);
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.precipitation')).toHaveCount(9);
  await expect(view.getByRole('img', { name: 'Circuit outline', exact: true })).toBeVisible();
  await expect(view.locator('.track-line')).toHaveAttribute('d', /^M[0-9.,-]+ L/);
  await expect(view.locator('.scale')).toContainText('km');
  await expect(view.getByText('Images 10 min apart', { exact: true })).toBeVisible();
  await expect(view.getByText('Latest image', { exact: true })).toBeVisible();
  const explanations = [/Current weather only\./, /satellite precipitation estimates/, /Zooming in enlarges/, /blank layer does not confirm dry weather/];
  for (const text of explanations) await expect(view.getByText(text)).toBeVisible();
  await expect(view.locator('.window span')).toHaveText('30 minutes before and after the latest image');
  const displayedTime = await view.locator('time').getAttribute('datetime');
  await page.evaluate(() => { window.radar.module = { options: { ...window.radar.module.options, show_explanation: false } }; });
  await expect(view.locator('.explanation')).toHaveCount(0);
  await expect(view.locator('.window span')).toHaveCount(0);
  for (const text of explanations) await expect(view.getByText(text)).toHaveCount(0);
  await expect(view.locator('time')).toHaveAttribute('datetime', displayedTime);
  await expect(view.locator('.frame-quality')).toContainText('Latest image:');
  await expect(view.locator('.frame-quality')).toContainText('Images 10 min apart');
  await expect(view.getByRole('button', { name: 'Play', exact: true })).toBeEnabled();
  await expect(view.getByRole('button', { name: 'Latest', exact: true })).toBeEnabled();
  await expect(view.getByRole('slider')).toBeEnabled();
  await expect(view.locator('.attribution').getByRole('link', { name: 'LibreWXR', exact: true })).toBeVisible();
  await expect(view.locator('.map-attribution').getByRole('link', { name: 'OpenStreetMap contributors', exact: true })).toBeVisible();
  await expect(view.locator('.attribution').getByRole('link', { name: 'CC BY-SA 4.0', exact: true })).toBeVisible();
  await page.evaluate(() => { window.radar.module = { options: { ...window.radar.module.options, show_explanation: true } }; });
  for (const text of explanations) await expect(view.getByText(text)).toBeVisible();
  await expect(view.locator('.window span')).toBeVisible();
  const before = await view.locator('.track-line').getAttribute('d');
  const start = urls.length;
  await view.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(view.locator('.place')).toBeVisible();
  await view.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(view.locator('.place')).toBeVisible();
  await expect(view.getByRole('button', { name: 'Zoom in', exact: true })).toBeDisabled();
  expect(await view.locator('.track-line').getAttribute('d')).not.toBe(before);
  const fetched = urls.slice(start), native = fetched.filter(url => url.includes('/v2/radar/'));
  expect(native.length).toBeGreaterThan(0);
  expect(native.every(url => /\/256\/12\//.test(url))).toBe(true);
  expect(fetched.some(url => /tile.openstreetmap.org\/14\//.test(url))).toBe(true);
  const count = await view.locator('.precipitation').count();
  expect(count).toBeGreaterThan(0); expect(count).toBeLessThanOrEqual(4);
});

test('near timeline uses actual ten-minute frames and Latest returns from forecast to latest observation', async ({ page }) => {
  const { now, metadata } = await setup(page);
  await expect(page.locator('f1-radar-view .place')).toBeVisible();
  await page.getByRole('slider').fill('2');
  await expect(page.locator('f1-radar-view .relative')).toHaveText('+10 min');
  await page.getByRole('button', { name: 'Latest', exact: true }).click();
  await expect(page.locator('f1-radar-view time')).toHaveAttribute('datetime', new Date(now * 1000).toISOString());
  await expect(page.locator('f1-radar-view .relative')).toHaveText('Latest image');
  expect(metadata.radar.nowcast.length).toBe(1);
});

test('missing outline keeps a location marker and provisional geometry is explicitly distinguished', async ({ page }) => {
  await setup(page, { options: { zoom: 12, show_explanation: false }, model: { circuits: [{ ...circuit, id: 'unknown_track' }], selectedId: 'unknown_track' } });
  await expect(page.locator('f1-radar-view .marker')).toBeVisible();
  await expect(page.locator('f1-radar-view .circuit-outline')).toHaveCount(0);
  await expect(page.getByText('A mapped circuit outline is unavailable for this circuit.', { exact: true })).toBeVisible();
  await page.evaluate(() => { window.radar.model = { circuits: [{ id: 'madring', name: 'Madring', lat: 40.47, lon: -3.62 }], selectedId: 'madring' }; });
  await expect(page.locator('f1-radar-view .circuit-outline.provisional')).toBeVisible();
  await expect(page.getByText('Mapped outline may differ from the current race layout.', { exact: true })).toBeVisible();
});

test('the default view uses close circuit scale and ages the latest image without increasing network polling', async ({ page }) => {
  await page.clock.install();
  const urls = [];
  page.on('request', request => { if (request.url().startsWith('https://tile.openstreetmap.org/')) urls.push(request.url()); });
  const { requests } = await setup(page, { options: {} });
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.place')).toBeVisible();
  expect(urls).toHaveLength(9);
  expect(urls.every(url => url.includes('tile.openstreetmap.org/13/'))).toBe(true);
  await expect(view.locator('.scale')).toHaveText('1 km');
  const age = view.locator('.frame-quality span').first();
  const firstAge = Number((await age.innerText()).match(/\d+/)[0]);
  await page.clock.fastForward(60000);
  await expect(age).toHaveText(`Latest image: ${firstAge + 1} min old`);
  expect(requests.metadata).toBe(1);
  await page.evaluate(() => window.radar.remove());
  const previous = requests.metadata;
  await page.clock.fastForward(10 * 60000);
  expect(requests.metadata).toBe(previous);
});

test('configured opening zoom and changed zoom settings control the map without resetting ordinary updates', async ({ page }) => {
  const urls = [];
  page.on('request', request => { if (request.url().startsWith('https://tile.openstreetmap.org/')) urls.push(request.url()); });
  await setup(page, { options: { zoom: 8 } });
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.place')).toBeVisible();
  expect(urls).toHaveLength(9);
  expect(urls.every(url => url.includes('/8/'))).toBe(true);
  await view.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(view.locator('.place')).toBeVisible();
  await page.evaluate(() => { window.radar.model = { ...window.radar.model }; window.radar.module = { options: { zoom: 8, show_circuit_selector: false } }; });
  await expect(view.getByRole('combobox')).toHaveCount(0);
  expect(await page.evaluate(() => window.radar.zoom)).toBe(9);
  await page.evaluate(() => { window.radar.module = { options: { zoom: 14, show_circuit_selector: false } }; });
  await expect(view.locator('.place')).toBeVisible();
  await expect(view.getByRole('button', { name: 'Zoom in', exact: true })).toBeDisabled();
  expect(urls.slice(-9).every(url => url.includes('/14/'))).toBe(true);
});

test('temporary circuit choices follow a changed next race or installation while surviving ordinary updates', async ({ page }) => {
  await setup(page, { model: { selectionKey: 'installation-a:baku', circuits: [circuit,
    { id: 'shanghai', name: 'Shanghai', lat: 31.3389, lon: 121.22 },
    { id: 'albert_park', name: 'Albert Park', lat: -37.8497, lon: 144.968 },
  ] } });
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.place')).toHaveText('Baku');
  await view.getByRole('combobox').selectOption('shanghai');
  await expect(view.locator('.place')).toHaveText('Shanghai');
  await page.evaluate(() => { window.radar.model = { ...window.radar.model, contextKey: 'ordinary-session-update' }; });
  await expect(view.locator('.place')).toHaveText('Shanghai');
  await page.evaluate(() => { window.radar.model = { ...window.radar.model, selectedId: 'albert_park', selectionKey: 'installation-a:albert-park' }; });
  await expect(view.getByRole('combobox')).toHaveValue('albert_park');
  await expect(view.locator('.place')).toHaveText('Albert Park');
  await view.getByRole('combobox').selectOption('baku');
  await expect(view.locator('.place')).toHaveText('Baku');
  await page.evaluate(() => { window.radar.model = { ...window.radar.model, selectionKey: 'installation-b:albert-park' }; });
  await expect(view.getByRole('combobox')).toHaveValue('albert_park');
  await expect(view.locator('.place')).toHaveText('Albert Park');
});

test('hiding the circuit selector clears a temporary selection and continues to show the next circuit name', async ({ page }) => {
  await setup(page, { model: { circuits: [circuit, { id: 'shanghai', name: 'Shanghai', lat: 31.3389, lon: 121.22 }] } });
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.place')).toHaveText('Baku');
  await view.getByRole('combobox').selectOption('shanghai');
  await expect(view.locator('.place')).toHaveText('Shanghai');
  await page.evaluate(() => { window.radar.module = { options: { zoom: 12, show_circuit_selector: false } }; });
  await expect(view.getByRole('combobox')).toHaveCount(0);
  await expect(view.locator('.place')).toHaveText('Baku');
  await expect(view.getByRole('button', { name: 'Zoom in', exact: true })).toBeVisible();
  await page.evaluate(() => { window.radar.module = { options: { zoom: 12, show_circuit_selector: true } }; });
  await expect(view.getByRole('combobox')).toHaveValue('baku');
});

test('an unavailable next circuit does not fall back to the first calendar circuit or fetch a map', async ({ page }) => {
  const { requests } = await setup(page, { model: { selectedId: null } });
  const view = page.locator('f1-radar-view');
  await expect(view.locator('.notice')).toContainText('The next circuit is unavailable.');
  await expect(view.getByRole('combobox')).toHaveValue('');
  expect(requests).toEqual({ metadata: 0, tiles: 0, base: 0 });
  await view.getByRole('combobox').selectOption('baku');
  await expect(view.locator('.place')).toHaveText('Baku');
  await page.evaluate(() => { window.radar.module = { options: { zoom: 12, show_circuit_selector: false } }; });
  await expect(view.getByRole('combobox')).toHaveCount(0);
  await expect(view.locator('.notice')).toContainText('The next circuit is unavailable.');
  await expect(view.locator('.precipitation')).toHaveCount(0);
});

test('compact maps keep local data uncertainty and the intensity legend for every circuit and forecast', async ({ page }) => {
  const urls = [];
  page.on('request', request => { if (request.url().startsWith('https://api.librewxr.net/')) urls.push(request.url()); });
  await setup(page, { options: { zoom: 13, show_explanation: false }, model: { circuits: [circuit,
    { id: 'shanghai', name: 'Shanghai', lat: 31.3389, lon: 121.22 },
    { id: 'albert_park', name: 'Melbourne', lat: -37.8497, lon: 144.968 },
    { id: 'losail', name: 'Qatar', lat: 25.49, lon: 51.4542 },
    { id: 'yas_marina', name: 'Abu Dhabi', lat: 24.4672, lon: 54.6031 },
  ] } });
  const view = page.locator('f1-radar-view');
  for (const id of ['baku', 'shanghai', 'albert_park', 'losail', 'yas_marina']) {
    await view.getByRole('combobox').selectOption(id);
    await expect(view.locator('.place')).toBeVisible();
    await expect(view.locator('.data-quality')).toContainText('Radar / satellite / model');
    await expect(view.locator('.data-quality')).toContainText('Local coverage unverified. A clear map does not confirm dry weather.');
    await expect(view.getByRole('group', { name: 'Image intensity · dBZ', exact: true })).toBeVisible();
    await expect(view.locator('.explanation')).toHaveCount(0);
  }
  await view.getByRole('slider').fill('2');
  await expect(view.locator('.badge')).toHaveText('Forecast');
  await expect(view.locator('.data-quality')).toContainText('Extrapolation / model');
  await expect(view.locator('.data-quality')).toContainText('Local coverage unverified.');
  await view.getByRole('button', { name: 'Latest', exact: true }).click();
  await expect(view.locator('.data-quality')).toContainText('Radar / satellite / model');
  expect(urls.filter(url => url.includes('/v2/radar/')).every(url => url.endsWith('/2/1_0.png'))).toBe(true);
  expect(urls.every(url => url.includes('/v2/radar/') || url.endsWith('/public/weather-maps.json'))).toBe(true);
});

test('legend labels explain the provider scale and remain readable on a narrow map', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await setup(page, { options: { zoom: 13, show_explanation: false } });
  const view = page.locator('f1-radar-view');
  const legend = view.getByRole('group', { name: 'Image intensity · dBZ', exact: true });
  await expect(legend).toBeVisible();
  const colours = ['rgba(146, 136, 113, 0.533)', 'rgba(206, 192, 135, 0.8)', 'rgb(136, 221, 238)',
    'rgb(0, 119, 170)', 'rgb(255, 238, 0)', 'rgb(255, 119, 0)', 'rgb(238, 0, 0)',
    'rgb(255, 170, 255)', 'rgb(255, 68, 255)', 'rgb(170, 0, 170)'];
  for (let index = 0; index < colours.length; index++) {
    await expect(legend.locator('.legend-swatch').nth(index)).toHaveCSS('background-color', colours[index]);
  }
  for (const label of ['0', '5', '10', '20', '30', '40', '50', '60', '70', '80+']) {
    await expect(legend.getByText(label, { exact: true })).toBeVisible();
  }
  await legend.locator('summary').click();
  await expect(legend).toContainText('The same scale is used for all precipitation, including snow.');
  await expect(legend).toContainText('not a measured rain rate in mm/h');
  expect(await legend.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expect(view.locator('.data-quality')).toBeVisible();
  expect(await view.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
});
