"""Regression tests for modular live data card localization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CARD_DIR = ROOT / "custom_components" / "f1_sensor" / "www" / "f1-sensor-live-data-card"
CATALOG_PATH = CARD_DIR / "modular" / "catalog.js"

NODE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';

const { FIELDS, label, MODULES, moduleTitle, words } = await import(
  pathToFileURL(process.env.F1_CATALOG_PATH)
);

process.stdout.write(JSON.stringify({
  airTemperature: label(FIELDS.temperature, 'nl-NL'),
  qualifyingBest: label(FIELDS.q1_time, 'nl'),
  placesGained: label(FIELDS.position_change, 'nl'),
  weatherModule: moduleTitle({ type: 'weather' }, 'nl'),
  currentWeatherModule: moduleTitle(
    { type: 'weather', options: { content: 'current_conditions' } },
    'nl',
  ),
  statusMessage: words(
    'nl',
    'No session data is currently available. Your settings are kept.',
    'Sessionsdata är inte tillgängliga just nu. Dina inställningar finns kvar.',
  ),
  dynamicColumns: words('nl', '3 of 4 columns', '3 av 4 kolumner'),
  driverLabel: words('nl', 'Driver', 'Förare'),
  resultModule: moduleTitle({ type: 'results' }, 'nl'),
  sessionName: words('nl', 'Qualifying', 'Kval'),
  swedishFallback: words('sv-SE', 'Weather', 'Väder'),
  unknownFallback: words('de-DE', 'Weather', 'Väder'),
  englishModule: label(MODULES.weather, 'en'),
}));
"""


def test_modular_card_uses_dutch_for_labels_titles_and_messages() -> None:
    """Dutch profiles localize the modular card beyond shared card metadata."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", NODE_SCRIPT],
        check=True,
        capture_output=True,
        env={**os.environ, "F1_CATALOG_PATH": str(CATALOG_PATH)},
        text=True,
    )

    assert json.loads(result.stdout) == {
        "airTemperature": "Luchttemperatuur",
        "qualifyingBest": "Q1 beste tijd",
        "placesGained": "Gewonnen plaatsen",
        "weatherModule": "Weeroverzicht",
        "currentWeatherModule": "Huidig circuitweer",
        "statusMessage": (
            "Er zijn momenteel geen sessiegegevens beschikbaar. "
            "Je instellingen blijven behouden."
        ),
        "dynamicColumns": "3 van 4 kolommen",
        "driverLabel": "Coureur",
        "resultModule": "Resultaten",
        "sessionName": "Kwalificatie",
        "swedishFallback": "Väder",
        "unknownFallback": "Weather",
        "englishModule": "Weather",
    }
