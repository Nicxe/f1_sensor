// Independent backwards-compatibility contract, not derived from the production
// registry. New cards are welcome; silently dropping a supported card is not.
const LEGACY_CARD_TYPES = Object.freeze([
  'f1-weekend-hub-card',
  'f1-sensor-live-data-card',
  'f1-pitstop-overview-card',
  'f1-driver-lap-times-card',
  'f1-championship-prediction-drivers-card',
  'f1-championship-prediction-teams-card',
  'f1-season-progression-card',
  'f1-last-race-results-card',
  'f1-lap-position-progression-card',
  'f1-replay-control-card',
  'f1-track-map-card',
  'f1-investigations-card',
  'f1-track-limits-card',
  'f1-next-race-card',
  'f1-weather-card',
  'f1-season-calendar-card',
  'f1-live-session-card',
  'f1-race-control-card',
  'f1-fia-documents-card',
  'f1-qualifying-timing-card',
  'f1-practice-timing-card',
  'f1-race-lap-card',
  'f1-starting-grid-card',
]);
const COMPATIBILITY_CARD_TYPES = Object.freeze(['f1-session-archive-card']);
const SUPPORTED_CARD_TYPES = Object.freeze(['f1-sensor-card', ...LEGACY_CARD_TYPES]);

module.exports = { LEGACY_CARD_TYPES, COMPATIBILITY_CARD_TYPES, SUPPORTED_CARD_TYPES };
