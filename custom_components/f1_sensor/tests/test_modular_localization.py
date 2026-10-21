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
  ),
  driverLabel: words('nl', 'Driver'),
  resultModule: moduleTitle({ type: 'results' }, 'nl'),
  incidentsModule: moduleTitle({ type: 'incidents' }, 'en'),
  sessionName: words('nl', 'Qualifying'),
  swedishFallback: words('sv-SE', 'Weather'),
  unknownFallback: words('zz-ZZ', 'Weather'),
  englishModule: label(MODULES.weather, 'en'),
}));
"""

LOCALE_SCRIPT = r"""
import { pathToFileURL } from 'node:url';

const localeDir = process.env.F1_LOCALE_DIR;
const { LOCALES: locales, translate, translatePlural } = await import(
  pathToFileURL(`${localeDir}/../index.js`)
);
const keys = Object.fromEntries(Object.entries(locales).map(
  ([language, messages]) => [language, Object.keys(messages).sort()],
));
const targetLanguages = Object.keys(locales).filter(language => language !== 'en');
const placeholders = value => [...new Set([...String(value).matchAll(/\{([a-zA-Z0-9_]+)\}/g)]
  .map(match => match[1]))].sort();
const mismatchedPlaceholders = keys.en.filter(key =>
  targetLanguages.some(language =>
    locales[language][key] !== undefined &&
    JSON.stringify(placeholders(locales.en[key]))
      !== JSON.stringify(placeholders(locales[language][key])),
  ),
);
const unexpectedTargetKeys = Object.fromEntries(targetLanguages.map(language => [
  language,
  keys[language].filter(key => locales.en[key] === undefined),
]));
const missingTargetKeysUseEnglish = targetLanguages.every(language =>
  keys.en
    .filter(key => !targetLanguages.some(candidate =>
      (language === candidate || language.startsWith(`${candidate}-`))
      && locales[candidate][key] !== undefined))
    .every(key => translate(language, key) === locales.en[key]),
);

process.stdout.write(JSON.stringify({
  keyCount: keys.en.length,
  unexpectedTargetKeys,
  missingTargetKeysUseEnglish,
  mismatchedPlaceholders,
  swedish: translate('sv-SE', 'modular.no_session_data_is_currently_available_your_settings_are_kept'),
  dutch: translate('nl-NL', 'modular.no_session_data_is_currently_available_your_settings_are_kept'),
  replacement: translate('sv', 'a11y.open_details', { title: 'Testkort' }),
  german: translate('de-DE', 'card.weather.name'),
  fallback: translate('zz-ZZ', 'card.weather.name'),
  singular: translatePlural('nl', 'modular.column_count', 1),
  plural: translatePlural('sv', 'modular.column_count', 3),
}));
"""


def _catalogs() -> dict[str, dict[str, str]]:
    """Read expectations independently from translator-owned JSON files."""
    return {
        path.stem.lower(): json.loads(path.read_text(encoding="utf-8"))
        for path in LOCALE_DIR.glob("*.json")
    }


def _message(language: str, key: str, **replacements: str) -> str:
    catalogs = _catalogs()
    text = catalogs[language].get(key, catalogs["en"][key])
    for name, value in replacements.items():
        text = text.replace("{" + name + "}", value)
    return text


def _source_messages(language: str, source: str) -> set[str]:
    """Source-text aliases can have different valid translator-owned wording."""
    catalogs = _catalogs()
    values = {
        catalogs[language].get(key, source)
        for key, text in catalogs["en"].items()
        if text == source
        and key.startswith(("legacy.modular.", "legacy.platform.", "modular."))
    }
    translated = values - {source}
    return translated or {source}


def test_modular_card_uses_dutch_for_labels_titles_and_messages() -> None:
    """Dutch profiles localize the modular card beyond shared card metadata."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", NODE_SCRIPT],
        check=True,
        capture_output=True,
        env={**os.environ, "F1_CATALOG_PATH": str(CATALOG_PATH)},
        text=True,
    )

    payload = json.loads(result.stdout)
    expected_sources = {
        "airTemperature": ("nl", "Air temperature"),
        "qualifyingBest": ("nl", "Q1 best"),
        "placesGained": ("nl", "Places gained"),
        "weatherModule": ("nl", "Weather overview"),
        "currentWeatherModule": ("nl", "Current circuit weather"),
        "statusMessage": (
            "nl",
            "No session data is currently available. Your settings are kept.",
        ),
        "driverLabel": ("nl", "Driver"),
        "resultModule": ("nl", "Results"),
        "incidentsModule": ("en", "Incidents"),
        "sessionName": ("nl", "Qualifying"),
        "swedishFallback": ("sv", "Weather"),
        "unknownFallback": ("en", "Weather"),
        "englishModule": ("en", "Weather"),
    }
    assert payload.keys() == expected_sources.keys()
    for name, (language, source) in expected_sources.items():
        assert payload[name] in _source_messages(language, source), name


def test_frontend_locales_use_source_keys_fallbacks_and_safe_placeholders() -> None:
    """Target locales remain Weblate-safe while missing keys use English."""
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", LOCALE_SCRIPT],
        check=True,
        capture_output=True,
        env={**os.environ, "F1_LOCALE_DIR": str(LOCALE_DIR)},
        text=True,
    )

    payload = json.loads(result.stdout)
    catalogs = _catalogs()
    assert payload["keyCount"] == len(catalogs["en"])
    assert payload["unexpectedTargetKeys"] == {
        language: [] for language in catalogs if language != "en"
    }
    assert payload["missingTargetKeysUseEnglish"] is True
    assert payload["mismatchedPlaceholders"] == []
    assert payload["swedish"] == _message(
        "sv", "modular.no_session_data_is_currently_available_your_settings_are_kept"
    )
    assert payload["dutch"] == _message(
        "nl", "modular.no_session_data_is_currently_available_your_settings_are_kept"
    )
    assert payload["replacement"] == _message(
        "sv", "a11y.open_details", title="Testkort"
    )
    assert payload["german"] == _message("de", "card.weather.name")
    assert payload["fallback"] == _message("en", "card.weather.name")
    assert payload["singular"] == _message("nl", "modular.column_count.one", count="1")
    assert payload["plural"] == _message("sv", "modular.column_count.other", count="3")


def test_frontend_locales_are_in_the_runtime_asset_manifest(tmp_path: Path) -> None:
    """The runtime sync must include every locale asset used by the card."""
    from custom_components.f1_sensor.frontend import (
        LIVE_DATA_CARD_LOCALE_MANIFEST,
        _sync_bundled_live_data_card_assets,
    )

    runtime = tmp_path / "runtime"
    _sync_bundled_live_data_card_assets(runtime)
    assert json.loads((runtime / LIVE_DATA_CARD_LOCALE_MANIFEST).read_text()) == sorted(
        path.stem for path in LOCALE_DIR.glob("*.json")
    )
    for source in LOCALE_DIR.glob("*.json"):
        assert (
            runtime / "localization" / "locales" / source.name
        ).read_bytes() == source.read_bytes()


def test_frontend_locale_json_is_weblate_compatible() -> None:
    """Card locales use flat string mappings that Weblate can edit directly."""
    for path in sorted(LOCALE_DIR.glob("*.json")):
        messages = json.loads(path.read_text(encoding="utf-8"))
        if path.stem == "en":
            assert messages
        assert all(isinstance(key, str) for key in messages)
        assert all(isinstance(value, str) for value in messages.values())


def test_modular_static_messages_use_translation_keys() -> None:
    """New modular UI text must not embed parallel English and Swedish copies."""
    bilingual_call = re.compile(r"this\.w\(\s*(['\"])[^)\n]*\1\s*,\s*(['\"])")
    for path in (CARD_DIR / "modular").glob("*.js"):
        if path.name == "i18n.js":
            continue
        source = path.read_text()
        assert bilingual_call.search(source) is None
