import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  buildCatalog,
  renderMarkdown,
  serializeCatalog,
} from '../scripts/build_modular_field_catalog.mjs';

test('generated modular field catalog matches every delivered module variant', async () => {
  const catalog = buildCatalog();
  assert.equal(catalog.module_count, 20);
  assert.ok(catalog.field_count > 100);
  assert.ok(catalog.sources.includes('analysis'));
  assert.ok(catalog.sources.includes('history/results'));
  assert.ok(catalog.sources.includes('track_map'));
  const [json, markdown] = await Promise.all([
    readFile(new URL('../quality/modular-field-catalog.json', import.meta.url), 'utf8'),
    readFile(new URL('../quality/modular-field-catalog.md', import.meta.url), 'utf8'),
  ]);
  assert.equal(json, serializeCatalog(catalog));
  assert.equal(markdown, renderMarkdown(catalog));
});

test('content variants retain their distinct source and identity contracts', () => {
  const catalog = buildCatalog();
  const module = id => catalog.modules.find(item => item.id === id);
  const variant = (id, name) => module(id).variants.find(item => item.id === `content=${name}`);
  assert.equal(variant('weather', 'track_conditions').fields.find(field => field.id === 'temperature').source, 'track_weather');
  assert.equal(variant('weather', 'race_forecast').fields.find(field => field.id === 'temperature').source, 'weather');
  assert.equal(variant('archive', 'classification').fields.find(field => field.id === 'driver').source, 'history/results');
  assert.equal(variant('archive', 'lap_time').fields.find(field => field.id === 'lap_series').source, 'history/laps');
  assert.deepEqual(variant('incidents', 'track_limits_summary').fields.find(field => field.id === 'driver').identity, ['entry', 'session', 'driver']);
});
