import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {card} from './card-module.mjs';

const observed = JSON.parse(readFileSync(new URL('./qualifying-part-events.json', import.meta.url)));

for (const mode of ['narrow', 'medium']) {
  test(`qualifying ${mode} Q2 column never borrows a Q1 time`, () => {
    const host = card('f1-qualifying-timing-card');
    const rows = host._buildRows(observed.drivers, [], [], 2);
    const col = host._columns(mode, 2, false).find(col => col.key === 'best_session');
    assert.equal(col.label, 'Q2');
    for (const number of ['16', '22']) {
      const row = rows.find(row => row.rn === number);
      assert.equal(row.q2_lap, null);
      assert.match(host._renderCell(row, col), /--:--\.---/);
      assert.ok(!host._renderCell(row, col).includes(row.q1_lap));
    }
    const timed = rows.find(row => row.rn === '3');
    assert.match(host._renderCell(timed, col), /1:22\.573/);
  });

  test(`qualifying ${mode} Q3 stays empty until its own slower lap arrives`, () => {
    const host = card('f1-qualifying-timing-card');
    const driver = {...observed.drivers.find(driver => driver.racing_number === '16'), q2_time:'1:23.500', q2_position:4};
    const col = host._columns(mode, 3, false).find(col => col.key === 'best_session');
    assert.equal(col.label, 'Q3');
    let row = host._buildRows([driver], [], [], 3)[0];
    assert.match(host._renderCell(row, col), /--:--\.---/);
    row = host._buildRows([{...driver, q3_time:'1:24.500', q3_position:2}], [], [], 3)[0];
    assert.match(host._renderCell(row, col), /1:24\.500/);
    assert.ok(!host._renderCell(row, col).includes('1:23.500'));
  });
}

test('wide qualifying keeps separately labelled earlier parts', () => {
  const host = card('f1-qualifying-timing-card');
  const row = host._buildRows(observed.drivers, [], [], 2).find(row => row.rn === '16');
  const cols = host._columns('wide', 2, false);
  assert.match(host._renderCell(row, cols.find(col => col.key === 'q1_lap')), /1:22\.902/);
  assert.match(host._renderCell(row, cols.find(col => col.key === 'q2_lap')), /--:--\.---/);
});

test('unknown qualifying part retains the existing BEST fallback', () => {
  const host = card('f1-qualifying-timing-card');
  const row = {q1_lap:'1:22.902', q1_lap_position:9, q2_lap:null, q3_lap:null};
  const col = host._columns('narrow', null, false).find(col => col.key === 'best_session');
  assert.equal(col.label, 'BEST');
  assert.match(host._renderCell(row, col), /1:22\.902/);
});
