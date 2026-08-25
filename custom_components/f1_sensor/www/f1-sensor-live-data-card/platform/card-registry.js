export const F1_CARD_DEFINITIONS = [
  ['f1-weekend-hub-card', 'F1 Weekend Hub', 'One synchronized home for live, replay, and post-session analysis'],
  ['f1-sensor-live-data-card', 'F1 Tyres Statistics', 'F1-style tyres statistics with top times and deltas'],
  ['f1-pitstop-overview-card', 'F1 Pit Stops & Tyres', 'Pit stop overview with tyre and stop timing columns'],
  ['f1-driver-lap-times-card', 'F1 Driver Lap Times', 'Driver lap table with latest, best, and configurable lap history'],
  ['f1-championship-prediction-drivers-card', 'F1 Championship Standings Drivers', 'Driver championship standings with race projection overlay'],
  ['f1-championship-prediction-teams-card', 'F1 Championship Standings Teams', 'Constructor championship standings with race projection overlay'],
  ['f1-season-progression-card', 'F1 Season Progression', 'Season progression chart for driver or constructor points'],
  ['f1-last-race-results-card', 'F1 Results', 'Current-season and on-demand historical race, Sprint, and qualifying results'],
  ['f1-lap-position-progression-card', 'F1 Lap Position Progression', 'Post-race lap position chart for completed races'],
  ['f1-replay-control-card', 'F1 Replay Control', 'Replay session selectors, playback controls, and progress'],
  ['f1-track-map-card', 'F1 Track Map', 'Live and replay track map with car positions and track status'],
  ['f1-investigations-card', 'F1 Investigations & Penalties', 'Investigation and penalty tracker grouped by driver'],
  ['f1-track-limits-card', 'F1 Track Limits', 'Track limits violations, deletions, warnings, and penalties'],
  ['f1-next-race-card', 'F1 Next Race Overview', 'Next race countdown, schedule, weather, and history'],
  ['f1-weather-card', 'F1 Race Weather', 'Current circuit conditions and race-start forecast'],
  ['f1-season-calendar-card', 'F1 Season Calendar', 'Full Formula 1 season calendar'],
  ['f1-live-session-card', 'F1 Live Session Status', 'Live session, weather, track status, and lap progress'],
  ['f1-race-control-card', 'F1 Race Control', 'Race control message banner with FIA styling'],
  ['f1-fia-documents-card', 'F1 FIA Documents', 'Race weekend documents with direct links and publication times'],
  ['f1-qualifying-timing-card', 'F1 Qualifying Timing', 'Live qualifying timing with sectors, tyres, and best laps'],
  ['f1-practice-timing-card', 'F1 Free Practice Timing', 'Practice timing with sectors, tyres, and fastest laps'],
  ['f1-race-lap-card', 'F1 Race Lap', 'Race timing with sectors, laps, tyres, and pit stops'],
  ['f1-starting-grid-card', 'F1 Starting Grid', 'Starting grid for the active Sprint or Race'],
].map(([type, name, description]) => ({
  type,
  name,
  description,
  configurable: true,
  preview: true,
}));

export const F1_CARD_TAGS = new Set(F1_CARD_DEFINITIONS.flatMap(({ type }) => [
  type,
  `${type}-editor`,
]));

export const registerF1CardMetadata = () => {
  window.customCards = window.customCards || [];
  const registered = new Set(window.customCards.map((card) => card?.type));
  for (const definition of F1_CARD_DEFINITIONS) {
    if (!registered.has(definition.type)) window.customCards.push(definition);
  }
};
