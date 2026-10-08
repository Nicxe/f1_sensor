"""Regression tests for modular overview event selection."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CARD_DIR = ROOT / "custom_components" / "f1_sensor" / "www" / "f1-sensor-live-data-card"
DATA_PATH = CARD_DIR / "modular" / "data.js"

NODE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';

const { overviewEvent } = await import(pathToFileURL(process.env.F1_DATA_PATH));

const state = (value, attributes = {}) => ({
  state: String(value), attributes, last_updated: '2026-10-06T10:00:00Z',
});
const entry = {
  entry_id: 'fixture',
  entities: {
    current_session: 'sensor.current_session',
    replay_status: 'sensor.replay_status',
    replay_player: 'media_player.replay_player',
    current_season: 'sensor.current_season',
    next_race: 'sensor.next_race',
  },
};
const hass = { states: {
  'sensor.current_session': state('Race', {
    season: 2026,
    meeting_key: 1248,
    session_key: 9848,
    meeting_name: 'Bahrain Grand Prix',
    meeting_location: 'Sakhir',
    meeting_country: 'Bahrain',
    circuit_short_name: 'Sakhir',
    start: '2026-04-12T15:00:00Z',
  }),
  'sensor.replay_status': state('playing', {
    selected_session: 'Bahrain Grand Prix - Race',
    selected_session_year: 2026,
    selected_meeting_key: 1248,
    selected_session_key: 9848,
  }),
  'media_player.replay_player': state('playing', {
    replay_state: 'playing',
    selected_session: 'Bahrain Grand Prix - Race',
    selected_session_year: 2026,
    selected_meeting_key: 1248,
    selected_session_key: 9848,
  }),
  'sensor.current_season': state(24, { season: '2026', races: [{
    season: '2026',
    raceName: 'Bahrain Grand Prix',
    Circuit: {
      circuitName: 'Bahrain International Circuit',
      Location: { locality: 'Sakhir', country: 'Bahrain' },
    },
    country_flag_url: 'https://flags.example/bh.png',
    circuit_map_url: 'https://maps.example/bahrain.webp',
  }] }),
  'sensor.next_race': state('Singapore Grand Prix', {
    season: '2026',
    race_name: 'Singapore Grand Prix',
    circuit_name: 'Marina Bay Street Circuit',
    circuit_country: 'Singapore',
    country_flag_url: 'https://flags.example/sg.png',
    circuit_map_url: 'https://maps.example/singapore.webp',
    race_start_utc: '2026-10-11T12:00:00Z',
  }),
} };

const replay = overviewEvent(hass, entry, { mode: 'follow', source: 'replay' });
delete hass.states['sensor.current_season'].attributes.races;
const replayWithoutCalendar = overviewEvent(
  hass,
  entry,
  { mode: 'follow', source: 'replay' },
);

process.stdout.write(JSON.stringify({ replay, replayWithoutCalendar }));
"""


def test_overview_follows_loaded_replay_instead_of_upcoming_race() -> None:
    """Replay context never leaks event details from the next race."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", NODE_SCRIPT],
        check=True,
        capture_output=True,
        env={**os.environ, "F1_DATA_PATH": str(DATA_PATH)},
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["replay"] == {
        "attributes": {
            "season": 2026,
            "race_name": "Bahrain Grand Prix",
            "circuit_name": "Bahrain International Circuit",
            "circuit_locality": "Sakhir",
            "circuit_country": "Bahrain",
            "country_flag_url": "https://flags.example/bh.png",
            "circuit_map_url": "https://maps.example/bahrain.webp",
            "race_start_utc": "2026-04-12T15:00:00Z",
        },
        "replay": True,
        "calendar_match": True,
        "context_available": True,
    }
    assert payload["replayWithoutCalendar"] == {
        "attributes": {
            "season": 2026,
            "race_name": "Bahrain Grand Prix",
            "circuit_name": "Sakhir",
            "circuit_locality": "Sakhir",
            "circuit_country": "Bahrain",
            "country_flag_url": None,
            "circuit_map_url": None,
            "race_start_utc": "2026-04-12T15:00:00Z",
        },
        "replay": True,
        "calendar_match": False,
        "context_available": True,
    }
