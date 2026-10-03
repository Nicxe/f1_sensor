"""Regression tests for modular live timing source availability."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CARD_DIR = ROOT / "custom_components" / "f1_sensor" / "www" / "f1-sensor-live-data-card"
DATA_PATH = CARD_DIR / "modular" / "data.js"
CONFIG_PATH = CARD_DIR / "modular" / "config.js"
SEMANTICS_PATH = CARD_DIR / "modular" / "semantics.js"

NODE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';

const { timingRows } = await import(pathToFileURL(process.env.F1_DATA_PATH));
const { normalizeConfig } = await import(pathToFileURL(process.env.F1_CONFIG_PATH));
const { SectorStore } = await import(pathToFileURL(process.env.F1_SEMANTICS_PATH));

const entry = {
  entry_id: 'fixture',
  entities: {
    driver_positions: 'sensor.positions',
    driver_list: 'sensor.drivers',
    current_tyres: 'sensor.tyres',
  },
};
const hass = {
  states: {
    'sensor.positions': {
      state: 'unknown',
      attributes: {
        current_qualifying_part: 2,
        drivers: [{
          racing_number: '4',
          tla: 'NOR',
          current_position: '1',
          q2_time: '1:36.500',
          completed_laps: 7,
        }],
      },
      last_updated: '2026-10-03T08:14:48Z',
    },
    'sensor.drivers': {
      state: '22',
      attributes: { drivers: [{ racing_number: '4', tla: 'NOR' }] },
    },
    'sensor.tyres': { state: 'unknown', attributes: { drivers: [] } },
  },
};
const moduleConfig = normalizeConfig({ modules: [{ type: 'timing' }] }).modules[0];
const result = timingRows(
  hass,
  entry,
  { key: 'qualifying', name: 'Qualifying' },
  new SectorStore(),
  moduleConfig,
);
process.stdout.write(JSON.stringify({
  sourceStatus: result.source.status,
  drivers: result.rows.map((row) => row.driver),
  currentPart: result.currentPart,
}));
"""


def test_qualifying_timing_uses_driver_attributes_when_lap_state_is_unknown() -> None:
    """Qualifying rows remain usable without the race-only LapCount state."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", NODE_SCRIPT],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "F1_DATA_PATH": str(DATA_PATH),
            "F1_CONFIG_PATH": str(CONFIG_PATH),
            "F1_SEMANTICS_PATH": str(SEMANTICS_PATH),
        },
        text=True,
    )

    assert json.loads(result.stdout) == {
        "sourceStatus": "available",
        "drivers": ["NOR"],
        "currentPart": 2,
    }
