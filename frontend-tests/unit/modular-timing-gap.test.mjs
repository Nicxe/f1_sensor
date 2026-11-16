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

const renderedText = value => String(value).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

for (const sessionKind of ['race', 'sprint']) for (const gap_primary of ['interval', 'gap']) {
  test(`${sessionKind} leader has one combined reference label with ${gap_primary} primary`, async () => {
    const view = await moduleView();
    view.module = { type: 'timing', options: { gap_display: 'combined', gap_primary }, fields: ['gap', 'interval'] };
    const leader = { id: '16', position: 1, gap: 'LAP 25', interval: 'LAP 25' };
    view.model = { sessionKind, rows: [leader] };
    const text = renderedText(view.combinedGapCell(leader));
    assert.equal((text.match(/\bLeader\b/g) ?? []).length, 1, text);
    assert.doesNotMatch(text, /Lap 25/i);
  });
}

test('combined gaps never infer a leader from lap text, filtered order or an unknown position', async () => {
  const view = await moduleView();
  for (const sessionKind of ['race', 'sprint']) for (const gap_primary of ['interval', 'gap']) for (const position of [2, 15, null, undefined, 0]) {
    view.module = { type: 'timing', options: { gap_display: 'combined', gap_primary }, fields: ['gap', 'interval'] };
    const driver = { id: '4', position, gap: 'LAP 25', interval: 'LAP 25' };
    // A focused or sorted card can have a lapped non-leader as its only row.
    view.model = { sessionKind, rows: [driver] };
    const text = renderedText(view.combinedGapCell(driver));
    assert.doesNotMatch(text, /\bLeader\b/, `${sessionKind}, ${gap_primary}, position ${position}: ${text}`);
    assert.equal((text.match(/Lap 25/gi) ?? []).length, 2, text);
  }
});

test('position one in practice, qualifying or an unknown session keeps the supplied gaps', async () => {
  const view = await moduleView();
  for (const sessionKind of ['practice', 'qualifying', 'sprint_qualifying', null]) for (const gap_primary of ['interval', 'gap']) {
    view.module = { type: 'timing', options: { gap_display: 'combined', gap_primary }, fields: ['gap', 'interval'] };
    const driver = { id: '16', position: 1, gap: 'LAP 25', interval: 'LAP 25' };
    view.model = { sessionKind, rows: [driver] };
    const text = renderedText(view.combinedGapCell(driver));
    assert.doesNotMatch(text, /\bLeader\b/, `${sessionKind}: ${text}`);
    assert.equal((text.match(/Lap 25/gi) ?? []).length, 2, text);
  }
});
