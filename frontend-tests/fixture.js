const COMPONENT_ROOT = '/custom_components/f1_sensor/www/f1-sensor-live-data-card';

for (const tag of [
  'ha-card',
  'ha-icon',
  'ha-select',
  'ha-textfield',
  'ha-switch',
  'ha-formfield',
  'ha-icon-button',
  'ha-control-button',
]) {
  if (!customElements.get(tag)) customElements.define(tag, class extends HTMLElement {});
}

const entityState = (state, attributes = {}) => ({
  state: String(state),
  attributes,
  last_changed: '2026-08-31T12:00:00Z',
  last_updated: '2026-08-31T12:00:00Z',
});

const states = {
  'sensor.f1_current_session': entityState('no_session', {
    meeting_name: 'Italian Grand Prix',
    session_name: 'Race',
    session_type: 'Race',
  }),
  'sensor.f1_session_status': entityState('inactive'),
  'sensor.f1_track_status': entityState('Clear'),
  'sensor.f1_lap_count': entityState('0', { total_laps: 53 }),
  'sensor.f1_driver_list': entityState('20', { drivers: [] }),
  'sensor.f1_driver_positions': entityState('unknown', { positions: [] }),
  'sensor.f1_next_race': entityState('Italian Grand Prix', {
    race_name: 'Italian Grand Prix',
    circuit_name: 'Monza',
    race_start: '2026-09-06T13:00:00Z',
  }),
  'sensor.f1_race_weather': entityState('available', {
    temperature: 24,
    humidity: 55,
    pressure: 1012,
    wind_speed: 3.4,
  }),
  'sensor.f1_season_calendar': entityState('24', { races: [] }),
  'sensor.f1_latest_race_results': entityState('available', { results: [] }),
  'sensor.f1_replay_status': entityState('idle'),
};

const translations = {
  'ui.common.loading': 'Loading',
};

const emptyResponse = (message) => {
  if (message?.type?.includes('/subscribe')) return undefined;
  if (message?.type?.includes('config/entity_registry/list')) return [];
  if (message?.type?.includes('config_entries/get')) return { entries: [{ entry_id: 'phase5-entry', title: 'F1 Sensor' }] };
  if (message?.type?.includes('/analysis/')) return { protocol_version: 1, status: 'waiting', items: [], events: [] };
  if (message?.type?.includes('/history/')) return { protocol_version: 1, sessions: [], results: [] };
  return {};
};

window.makeHass = (language = 'en-GB', theme = 'dark') => ({
  states,
  locale: { language, time_format: '24', time_zone: 'Europe/Stockholm' },
  language,
  config: {
    time_zone: 'Europe/Stockholm',
    unit_system: { temperature: '°C', wind_speed: 'm/s', pressure: 'hPa' },
  },
  themes: { darkMode: theme === 'dark' },
  user: { is_admin: true, name: 'Phase 5 QA' },
  connection: {
    subscribeMessage: async () => () => {},
    subscribeEvents: async () => () => {},
  },
  callWS: async (message) => emptyResponse(message),
  callService: async () => undefined,
  formatEntityState: (stateObj) => stateObj?.state ?? 'unknown',
  formatEntityAttributeValue: (stateObj, key) => stateObj?.attributes?.[key] ?? 'unknown',
  formatEntityAttributeName: (_stateObj, key) => key,
  formatNumber: (value, options) => new Intl.NumberFormat(language, options).format(value),
  localize: (key) => translations[key] || key,
});

const waitForRender = async (element) => {
  if (element.updateComplete) await element.updateComplete;
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (element.updateComplete) await element.updateComplete;
};

await import(`${COMPONENT_ROOT}/register.js?v=phase5`);

const mount = document.querySelector('#mount');

window.f1CardTypes = () => window.customCards.map(({ type }) => type);

window.mountF1Element = async ({ type, editor = false, language = 'en-GB', theme = 'dark' }) => {
  mount.replaceChildren();
  mount.className = '';
  document.body.classList.toggle('light', theme === 'light');
  document.documentElement.lang = language;
  const tag = editor ? `${type}-editor` : type;
  const ElementClass = customElements.get(tag);
  if (!ElementClass) throw new Error(`Custom element ${tag} is not registered`);
  const hass = window.makeHass(language, theme);
  const element = document.createElement(tag);
  const config = editor
    ? { type: `custom:${type}`, entity: 'sensor.f1_current_session' }
    : await ElementClass.getStubConfig?.(hass) || { type: `custom:${type}` };
  config.entity ||= 'sensor.f1_current_session';
  config.tap_action = { action: 'more-info' };
  if (editor) element.setConfig?.(config);
  else element.setConfig(config);
  element.hass = hass;
  mount.appendChild(element);
  await waitForRender(element);
  return { tag, config, hasCard: Boolean(element.renderRoot?.querySelector('ha-card')) };
};

window.mountF1Gallery = async ({ editor = false, language = 'en-GB', theme = 'dark' } = {}) => {
  mount.replaceChildren();
  mount.className = 'gallery';
  document.body.classList.toggle('light', theme === 'light');
  document.documentElement.lang = language;
  const hass = window.makeHass(language, theme);
  const mounted = [];
  for (const type of window.f1CardTypes()) {
    const tag = editor ? `${type}-editor` : type;
    const ElementClass = customElements.get(tag);
    if (!ElementClass) throw new Error(`Custom element ${tag} is not registered`);
    const element = document.createElement(tag);
    const config = editor
      ? { type: `custom:${type}`, entity: 'sensor.f1_current_session' }
      : await ElementClass.getStubConfig?.(hass) || { type: `custom:${type}` };
    config.entity ||= 'sensor.f1_current_session';
    config.tap_action = { action: 'more-info' };
    element.setConfig?.(config);
    element.hass = hass;
    mount.appendChild(element);
    await waitForRender(element);
    mounted.push(tag);
  }
  return mounted;
};

await import('./realtime-fixture.js');
