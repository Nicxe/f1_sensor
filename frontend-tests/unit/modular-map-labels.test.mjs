import assert from 'node:assert/strict';
import test from 'node:test';
import { trackMapView } from './card-module.mjs';

test('corner numbers avoid a track crossing their preferred label position', async () => {
  const view = await trackMapView();
  view.model = { points: [[30, 47.2], [70, 47.2]], rows: [] };
  view.module = { options: { track_status_line_mode: 'off' } };
  const annotations = { corners: [{ id: 'turn_01', label: '1', point: [50, 50], offset: [3, -4] }], lines: [], points: [] };
  const labels = view.markingLabels(annotations, [], 3.5);
  const { box } = labels.get('corner:turn_01');
  assert.ok(box.bottom + .9 < 47.2 || box.top - .9 > 47.2, 'the corner number must clear the visible track and text strokes');
});

test('replacing offsets on the same annotation ID invalidates cached placement', async () => {
  const view = await trackMapView();
  view.model = { points: [[5, 5], [95, 5]], rows: [] };
  view.module = { options: { track_status_line_mode: 'off' } };
  const corner = { id: 'turn_01', label: '1', point: [50, 50], offset: [3, -4] };
  const annotations = { corners: [corner], lines: [], points: [] };
  const before = view.markingLabels(annotations, [], 3.5).get('corner:turn_01');
  corner.offset = [-3, 4];
  const after = view.markingLabels(annotations, [], 3.5).get('corner:turn_01');
  assert.notEqual(after.x, before.x);
  assert.notEqual(after.y, before.y);
});
