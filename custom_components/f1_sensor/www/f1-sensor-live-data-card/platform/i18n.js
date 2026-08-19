const STRINGS = {
  en: {
    'a11y.open_details': 'Open details for {title}',
    'track_map.websocket_unavailable': 'Track map websocket unavailable',
    'track_map.no_position_data': 'No position data',
    'track_map.paused': 'Paused',
    'track_map.seeking': 'Seeking',
    'track_map.replay': 'Replay',
    'track_map.no_session': 'No session',
    'track_map.no_geometry': 'No geometry',
    'track_map.stale': 'Stale',
    'track_map.waiting': 'Waiting',
    'track_map.not_loaded': 'Not loaded',
    'track_map.closed': 'Closed',
  },
  sv: {
    'a11y.open_details': 'Öppna detaljer för {title}',
    'track_map.websocket_unavailable': 'Track Map-webbsocketen är inte tillgänglig',
    'track_map.no_position_data': 'Ingen positionsdata',
    'track_map.paused': 'Pausad',
    'track_map.seeking': 'Söker',
    'track_map.replay': 'Repris',
    'track_map.no_session': 'Ingen session',
    'track_map.no_geometry': 'Ingen bangeometri',
    'track_map.stale': 'Inaktuell',
    'track_map.waiting': 'Väntar',
    'track_map.not_loaded': 'Inte laddad',
    'track_map.closed': 'Stängd',
  },
};

const languageFor = (hass) => String(hass?.locale?.language || hass?.language || 'en')
  .toLowerCase()
  .split('-', 1)[0];

export const f1Translate = (hass, key, fallback = key, replacements = {}) => {
  const language = languageFor(hass);
  const template = STRINGS[language]?.[key] || STRINGS.en[key] || fallback;
  return Object.entries(replacements).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  );
};
