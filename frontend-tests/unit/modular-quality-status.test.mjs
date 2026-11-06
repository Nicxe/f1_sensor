import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceStatusKey, modelTimestamp } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js';

test('an inactive source only claims ordinary session waiting with confirmed session context', () => {
  const source = { data_status: 'unavailable', reason: 'source_inactive' };
  assert.equal(sourceStatusKey(source), 'modular.source_inactive_unknown');
  assert.equal(sourceStatusKey(source, 'active'), 'modular.source_inactive_unknown');
  assert.equal(sourceStatusKey(source, 'before'), 'modular.source_waiting_for_session');
});

test('explicit source states distinguish unsupported, pending, unloaded and stale without an age heuristic', () => {
  assert.equal(sourceStatusKey({ data_status: 'unsupported' }), 'modular.source_unsupported');
  assert.equal(sourceStatusKey({ data_status: 'loading' }), 'modular.source_waiting_for_data');
  assert.equal(sourceStatusKey({ reason: 'waiting_for_current_context' }), 'modular.source_waiting_for_data');
  assert.equal(sourceStatusKey({ reason: 'source_not_loaded' }), 'modular.source_not_loaded');
  assert.equal(sourceStatusKey({ data_status: 'stale', reason: 'source_update_failed' }), 'modular.source_update_failed');
  const source = { data_status: 'ready', transport: 'direct', updated_at: '2026-01-01T00:00:00Z' };
  assert.equal(sourceStatusKey(source), null);
  assert.equal(modelTimestamp({ source }, Date.parse('2026-11-06T00:00:00Z')).kind, 'received');
});
