import assert from 'node:assert/strict';
import test from 'node:test';
import { moduleView } from './card-module.mjs';

test('qualifying timing gaps use the displayed delta precision', async () => {
  const view = await moduleView();
  view.module = { type: 'timing', options: {}, fields: ['qualifying_gap'] };
  view.model = { sessionKind: 'qualifying' };

  assert.equal(view.cell({ qualifying_gap: 82.847 - 82.631 }, 'qualifying_gap'), '<span class="time">+0.216</span>');
  assert.equal(view.cell({ qualifying_gap: 0 }, 'qualifying_gap'), '<span class="time">0.000</span>');
  assert.equal(view.cell({ qualifying_gap: null }, 'qualifying_gap'), '—');
});
