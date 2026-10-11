"""Regression tests for modular live data card localization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CARD_DIR = ROOT / "custom_components" / "f1_sensor" / "www" / "f1-sensor-live-data-card"
CATALOG_PATH = CARD_DIR / "modular" / "catalog.js"
LOCALE_DIR = CARD_DIR / "localization" / "locales"

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
  incidentsModule: moduleTitle({ type: 'incidents' }, 'en'),
  sessionName: words('nl', 'Qualifying', 'Kval'),
  swedishFallback: words('sv-SE', 'Weather', 'Väder'),
  unknownFallback: words('de-DE', 'Weather', 'Väder'),
  englishModule: label(MODULES.weather, 'en'),
}));
"""

LOCALE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';

const localeDir = process.env.F1_LOCALE_DIR;
const load = async language => (await import(
  pathToFileURL(`${localeDir}/${language}.js`)
)).default;
const locales = Object.fromEntries(await Promise.all(
  ['en', 'sv', 'nl'].map(async language => [language, await load(language)]),
));
const { translate, translatePlural } = await import(
  pathToFileURL(`${localeDir}/../index.js`)
);
const keys = Object.fromEntries(Object.entries(locales).map(
  ([language, messages]) => [language, Object.keys(messages).sort()],
));
const placeholders = value => [...String(value).matchAll(/\{([^{}]+)\}/g)]
  .map(match => match[1]).sort();
const mismatchedPlaceholders = keys.en.filter(key =>
  ['sv', 'nl'].some(language =>
    JSON.stringify(placeholders(locales.en[key]))
      !== JSON.stringify(placeholders(locales[language][key])),
  ),
);

process.stdout.write(JSON.stringify({
  keysMatch: JSON.stringify(keys.en) === JSON.stringify(keys.sv)
    && JSON.stringify(keys.en) === JSON.stringify(keys.nl),
  keyCount: keys.en.length,
  mismatchedPlaceholders,
  swedish: translate('sv-SE', 'modular.no_session_data_is_currently_available_your_settings_are_kept'),
  dutch: translate('nl-NL', 'modular.no_session_data_is_currently_available_your_settings_are_kept'),
  replacement: translate('sv', 'a11y.open_details', { title: 'Testkort' }),
  fallback: translate('de-DE', 'card.weather.name'),
  singular: translatePlural('nl', 'modular.column_count', 1),
  plural: translatePlural('sv', 'modular.column_count', 3),
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
        "resultModule": "Uitslagen",
        "incidentsModule": "Incidents",
        "sessionName": "Kwalificatie",
        "swedishFallback": "Väder",
        "unknownFallback": "Weather",
        "englishModule": "Weather",
    }


def test_frontend_locales_have_matching_keys_and_placeholders() -> None:
    """Every shipped card locale is complete and uses safe replacements."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", LOCALE_SCRIPT],
        check=True,
        capture_output=True,
        env={**os.environ, "F1_LOCALE_DIR": str(LOCALE_DIR)},
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["keysMatch"] is True
    assert payload["keyCount"] >= 700
    assert payload["mismatchedPlaceholders"] == []
    assert payload["swedish"] == (
        "Sessionsdata är inte tillgängliga just nu. Dina inställningar finns kvar."
    )
    assert payload["dutch"] == (
        "Er zijn momenteel geen sessiegegevens beschikbaar. "
        "Je instellingen blijven behouden."
    )
    assert payload["replacement"] == "Öppna detaljer för Testkort"
    assert payload["fallback"] == "F1 Race Weather"
    assert payload["singular"] == "1 kolom"
    assert payload["plural"] == "3 kolumner"


def test_frontend_locales_are_in_the_runtime_asset_manifest() -> None:
    """The runtime sync must include every locale module used by the card."""
    frontend_source = (
        ROOT / "custom_components" / "f1_sensor" / "frontend.py"
    ).read_text()

    assert '"localization/index.js"' in frontend_source
    for language in ("en", "sv", "nl"):
        assert f'"localization/locales/{language}.js"' in frontend_source


def test_modular_static_messages_use_translation_keys() -> None:
    """New modular UI text must not embed parallel English and Swedish copies."""
    bilingual_call = re.compile(r"this\.w\(\s*(['\"])[^)\n]*\1\s*,\s*(['\"])")
    for path in (CARD_DIR / "modular").glob("*.js"):
        if path.name == "i18n.js":
            continue
        source = path.read_text()
        assert bilingual_call.search(source) is None
