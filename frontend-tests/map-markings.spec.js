const { test, expect } = require('@playwright/test');
const catalog = require('./fixtures/map-catalog-2026.json');
const assetBase = '/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/';
const variants = [
  { width: 320, orientation: 'source', vertical: 'flipped' },
  { width: 400, orientation: 'source', vertical: 'flipped' },
  { width: 640, orientation: 'source', vertical: 'flipped' },
  { width: 400, orientation: 'raw', vertical: 'flipped' },
  { width: 400, orientation: 'source', vertical: 'normal' },
];

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(async base => {
    const [{ mapModel, trackProjection }] = await Promise.all([
      import(`${base}map-data.js`), import(`${base}map-view.js`),
    ]);
    // Exercise the real delivered renderer, with the same projection used by
    // the subscription model. Unsupported bindings remain renderer-only cases.
    window.mountCatalogMap = async (record, variant, fields = ['track_map', 'map_corners']) => {
      const options = { ...variant, labels: 'off', show_car_markers: false, track_status_line_mode: variant.lineMode ?? 'off' };
      const module = { fields, options };
      const model = mapModel(record.snapshot, module);
      if (!record.frontend_binding_supported && record.snapshot.annotations) {
        const projection = trackProjection({ ...record.snapshot.track, rotation: options.orientation === 'raw' ? 0 : record.snapshot.track.rotation }, options.vertical === 'flipped');
        const corners = record.snapshot.annotations.layers.find(layer => layer.layer === 'corners');
        model.annotations.corners = corners.items.map(values => {
          const item = Object.fromEntries(corners.columns.map((name, index) => [name, values[index]]));
          return { id: item.id, label: item.label, point: projection.project(...item.anchor), offset: item.label_offset };
        });
      }
      if (variant.lineMode) model.trackStatus = 'Clear';
      let view = document.querySelector('f1-track-map-view');
      if (!view) view = document.createElement('f1-track-map-view');
      view.style.cssText = `display:block;width:${variant.width}px;--f1-panel:#17191e;--f1-text:#f2f3f7;--f1-muted:#a7adb8;--f1-border:#454b56`;
      view.settings = { language: 'en', appearance: { team_colors: true }, accessibility: { motion: 'reduced' } };
      view.module = module; view.model = model;
      document.querySelector('#root').replaceChildren(view);
      await view.updateComplete;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      await view.updateComplete;
      window.catalogView = view;
    };
    window.mapClearance = (selector = '.annotation-number') => {
      const view = window.catalogView, svg = view.shadowRoot.querySelector('svg');
      const path = svg.querySelector('.track-status-accent') ?? svg.querySelector('.track');
      const trackPadding = Number.parseFloat(getComputedStyle(path).strokeWidth) / 2;
      const length = path.getTotalLength(), samples = Math.max(1, Math.ceil(length / .12));
      const points = Array.from({ length: samples + 1 }, (_, index) => path.getPointAtLength(length * index / samples));
      const intersects = (p, q, box, padding) => {
        let lower = 0, upper = 1;
        for (const [start, delta, min, max] of [[p.x, q.x - p.x, box.left - padding, box.right + padding], [p.y, q.y - p.y, box.top - padding, box.bottom + padding]]) {
          if (Math.abs(delta) < 1e-10) { if (start < min || start > max) return false; continue; }
          const a = (min - start) / delta, b = (max - start) / delta;
          lower = Math.max(lower, Math.min(a, b)); upper = Math.min(upper, Math.max(a, b));
          if (lower > upper) return false;
        }
        return true;
      };
      const boxes = [...svg.querySelectorAll(selector)].map(text => {
        const bounds = text.getBBox(), outline = Number.parseFloat(getComputedStyle(text).strokeWidth) / 2;
        return { label: text.textContent, left: bounds.x - outline, right: bounds.x + bounds.width + outline, top: bounds.y - outline, bottom: bounds.y + bounds.height + outline };
      });
      const trackCollisions = boxes.filter(box => points.some((point, index) => index > 0 && intersects(points[index - 1], point, box, trackPadding))).map(box => box.label);
      const labelCollisions = boxes.flatMap((box, index) => boxes.slice(index + 1).filter(other => Math.min(box.right, other.right) > Math.max(box.left, other.left) && Math.min(box.bottom, other.bottom) > Math.max(box.top, other.top)).map(other => `${box.label}/${other.label}`));
      const outside = boxes.filter(box => box.left < 0 || box.right > 100 || box.top < 0 || box.bottom > 100).map(box => box.label);
      return { count: boxes.length, trackCollisions, labelCollisions, outside, finite: Number.isFinite(length) && length > 0, width: view.width };
    };
  }, assetBase);
});

for (const record of catalog.circuits) {
  test(`corner labels clear the track and each other for ${record.name}`, async ({ page }) => {
    const count = record.snapshot.annotations.layers.find(layer => layer.layer === 'corners').items.length;
    for (const variant of variants) {
      await page.evaluate(({ record, variant }) => window.mountCatalogMap(record, variant), { record, variant });
      const result = await page.evaluate(() => window.mapClearance());
      expect(result, JSON.stringify(variant)).toEqual({ count, trackCollisions: [], labelCollisions: [], outside: [], finite: true, width: variant.width });
    }
  });
}

for (const lineMode of ['off', 'full', 'accent']) {
  test(`Austin labels clear the visible ${lineMode} track stroke`, async ({ page }) => {
    const record = catalog.circuits.find(item => item.circuit_key === '9');
    await page.evaluate(({ record, variant }) => window.mountCatalogMap(record, variant), { record, variant: { ...variants[1], lineMode } });
    const result = await page.evaluate(() => window.mapClearance());
    expect(result.trackCollisions).toEqual([]);
    expect(result.labelCollisions).toEqual([]);
    expect(result.count).toBe(20);
  });
}

test('label placement refreshes after resizing and same-ID annotation changes', async ({ page }) => {
  const record = catalog.circuits.find(item => item.circuit_key === '9');
  await page.evaluate(({ record, variant }) => window.mountCatalogMap(record, variant), { record, variant: variants[0] });
  const resized = await page.evaluate(async () => {
    const view = window.catalogView, points = view.model.points;
    const before = view.shadowRoot.querySelector('.annotation-number').getAttribute('font-size');
    view.style.width = '640px';
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await view.updateComplete;
    return { before, after: view.shadowRoot.querySelector('.annotation-number').getAttribute('font-size'), sameGeometry: points === view.model.points, clearance: window.mapClearance() };
  });
  expect(resized.sameGeometry).toBe(true);
  expect(resized.before).not.toBe(resized.after);
  expect(resized.clearance.trackCollisions).toEqual([]);
  expect(resized.clearance.count).toBe(20);

  const moved = await page.evaluate(async () => {
    const view = window.catalogView;
    view.model = { ...view.model, points: [[10, 20], [80, 20], [80, 80], [10, 80], [10, 20]], annotations: { lines: [], points: [], unavailable: [], corners: [{ id: 'turn_01', label: '1', point: [40, 20], offset: [0, -8] }] } };
    await view.updateComplete;
    const position = () => { const text = view.shadowRoot.querySelector('.annotation-number'); return [text.getAttribute('x'), text.getAttribute('y'), text.textContent]; };
    const before = position(), points = view.model.points;
    view.model = { ...view.model, annotations: { ...view.model.annotations, corners: [{ id: 'turn_01', label: '21', point: [60, 80], offset: [0, 8] }] } };
    await view.updateComplete;
    return { before, after: position(), sameGeometry: points === view.model.points, clearance: window.mapClearance() };
  });
  expect(moved.sameGeometry).toBe(true);
  expect(moved.before.slice(0, 2)).not.toEqual(moved.after.slice(0, 2));
  expect(moved.after[2]).toBe('21');
  expect(moved.clearance.trackCollisions).toEqual([]);
});

const upcoming = new Set(['9', '65', '14', '150', '70']);
for (const record of catalog.circuits.filter(item => upcoming.has(item.circuit_key))) {
  test(`upcoming ${record.name} keeps combined circuit labels clear`, async ({ page }, testInfo) => {
    const fields = ['track_map', 'map_corners', 'map_start_finish', 'map_sectors', 'map_speed_traps', 'map_detection_zones'];
    const count = record.snapshot.annotations.layers.filter(layer => ['corners', 'sectors', 'speed_traps'].includes(layer.layer)).reduce((sum, layer) => sum + layer.items.length, 0);
    for (const variant of [variants[0], variants[2]]) {
      await page.evaluate(({ record, variant, fields }) => window.mountCatalogMap(record, variant, fields), { record, variant: { ...variant, lineMode: 'accent' }, fields });
      const result = await page.evaluate(() => window.mapClearance('.annotation-number, .annotation-tag-text, .annotation-feature-text'));
      expect(result, JSON.stringify(variant)).toEqual({ count, trackCollisions: [], labelCollisions: [], outside: [], finite: true, width: variant.width });
      await page.locator('f1-track-map-view').screenshot({ path: testInfo.outputPath(`${record.name}-${variant.width}.png`) });
    }
  });
}

test('static outlines are smooth while live-derived geometry preserves its original segments', async ({ page }) => {
  const record = catalog.circuits.find(item => item.circuit_key === '9');
  await page.evaluate(({ record, variant }) => window.mountCatalogMap(record, variant), { record, variant: variants[1] });
  const paths = await page.evaluate(async () => {
    const view = window.catalogView;
    const staticPath = view.shadowRoot.querySelector('.track').getAttribute('d');
    const points = view.model.points;
    view.model = { ...view.model, geometrySource: 'replay_position_sample' };
    await view.updateComplete;
    const recordedPath = view.shadowRoot.querySelector('.track').getAttribute('d');
    view.model = { ...view.model, geometrySource: null };
    await view.updateComplete;
    return { staticPath, recordedPath, unknownPath: view.shadowRoot.querySelector('.track').getAttribute('d'), samePoints: points === view.model.points };
  });
  expect(paths.staticPath).toMatch(/C/);
  expect(paths.recordedPath).not.toMatch(/C/);
  expect(paths.recordedPath).toMatch(/L/);
  expect(paths.unknownPath).toBe(paths.recordedPath);
  expect(paths.samePoints).toBe(true);
});

test('Las Vegas gains a smooth static outline without unsupported corner markings', async ({ page }) => {
  const record = catalog.unmarked_circuits.find(item => item.circuit_key === '152');
  await page.evaluate(({ record, variant }) => window.mountCatalogMap(record, variant), { record, variant: variants[1] });
  const result = await page.evaluate(() => ({ ...window.mapClearance(), path: window.catalogView.shadowRoot.querySelector('.track').getAttribute('d'), unavailable: window.catalogView.model.annotations.unavailable }));
  expect(result.path).toMatch(/C/);
  expect(result.count).toBe(0);
  expect(result.finite).toBe(true);
  expect(result.unavailable).toContain('map_corners');
});
