/** Complete, deterministic HA boundary for Race Trace presentation/lifecycle tests. */
async function mountRaceTrace(page, { config = {}, entries = 1, cards = 1 } = {}) {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(async ({ config, entries: count, cards: cardCount }) => {
    const base = '/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/';
    const [{ makeDemo }, { MODULES }, { connectionDiagnostics }] = await Promise.all([
      import(base + 'demo.js'), import(base + 'catalog.js'), import(base + 'connection.js'),
    ]);
    const entries = [], datasets = new Map(), analyses = new Map(), states = {}, records = [], handlers = new Map(), calls = [];
    const times = [[90, 90, 91, 90], [91, 89.5, 92, 110], [90, 90.25, 90.75, 89.5], [90, 89, 90, 91], [90, 90, 90, 90]];
    for (let index = 0; index < count; index++) {
      const demo = makeDemo('race', 'en', `trace-${index}`), entry = demo.preview.entries[0];
      const enabled = [...new Set([...MODULES.lap_chart.sources, 'session_context', 'current_session', 'session_status', 'replay_status'])];
      entry.data_api = { protocol_version: 1, lap_history_version: 1, enabled };
      entries.push(entry); Object.assign(states, demo.hass.states);
      const observationContext = { token: `token-${index}`, entry_id: entry.entry_id, source: 'live', session_id: 'race-1', source_epoch: `source-${index}`, delay_epoch: 0, delay_seconds: 0 };
      const cursor = sequence => ({ sequence, source_time_ms: 1800000000000 + sequence * 1000, time_domain: 'utc' });
      analyses.set(entry.entry_id, { protocol_version: 1, status: 'ready', race_trace_markers: {
        version: 1, status: 'ready', reason: null, context: structuredClone(observationContext), as_of: cursor(95), events: [
          { event_id: 'pit-81', revision: 1, kind: 'pit', phase: 'point', driver_number: 81, lap_number: 3, anchor_type: 'driver_lap', source: 'PitStopSeries', context_token: observationContext.token, observation_cursor: cursor(90) },
          { event_id: 'vsc-start', revision: 1, kind: 'vsc', phase: 'start', source: 'TrackStatus', context_token: observationContext.token, observation_cursor: cursor(80), reference_anchors: {
            4: { lap_number: 2, basis: 'confirmed_completed', observation_cursor: cursor(79) }, 81: { lap_number: 2, basis: 'confirmed_completed', observation_cursor: cursor(78) },
          } },
        ],
      } });
      const drivers = ['4', '81', '16', '63', '55'].map((number, i) => ({
        racing_number: number, tla: ['NOR', 'PIA', 'LEC', 'RUS', 'SAI'][i], name: ['Lando Norris', 'Oscar Piastri', 'Charles Leclerc', 'George Russell', 'Carlos Sainz'][i],
        team: i < 2 ? 'McLaren' : 'Other', team_color: i < 2 ? '#ff8700' : '#56aaff', current_position: i + 1, completed_laps: 4,
        laps: Object.fromEntries(times[i].map((time, lap) => [lap + 1, time])),
        lap_metadata: Object.fromEntries(times[i].map((_, lap) => [lap + 1, { association: 'confirmed', reason: null }])),
      }));
      for (const dataset of enabled) {
        const payload = structuredClone(demo.hass.states[entry.entities[dataset]] ?? { state: 'idle', attributes: {} });
        if (dataset === 'driver_positions') Object.assign(payload.attributes, { drivers, lap_history_version: 1, lap_history_session_type: 'Race',
          race_trace_observation: { version: 1, status: 'ready', reason: null, context: observationContext, timing_as_of: cursor(100) } });
        if (dataset === 'driver_list') payload.attributes.drivers = drivers;
        if (dataset === 'session_context') Object.assign(payload, { state: 'live', attributes: { no_spoiler: false, replay_state: 'idle', live_delay_seconds: 0 } });
        datasets.set(`${entry.entry_id}:${dataset}`, { protocol_version: 1, entry_id: entry.entry_id, dataset, generation: 'generation-1', revision: 1,
          source: 'live', status: 'ready', reason: null, context: { session_id: 'race-1', replay_generation: 0, delay_seconds: 0, qualifying_part: null }, payload });
      }
    }
    const connection = {
      connected: true,
      addEventListener(type, callback) { if (!handlers.has(type)) handlers.set(type, new Set()); handlers.get(type).add(callback); },
      removeEventListener(type, callback) { handlers.get(type)?.delete(callback); },
      async subscribeEvents(callback, type) { const record = { callback, type, active: true }; records.push(record); return () => { record.active = false; }; },
      async subscribeMessage(callback, message) {
        const record = { callback, message, active: true }; records.push(record);
        if (message.type === 'f1_sensor/data/subscribe') queueMicrotask(() => {
          if (record.active) for (const key of message.data_keys) callback(structuredClone(datasets.get(`${message.entry_id}:${key}`)));
        });
        if (message.type === 'f1_sensor/analysis/subscribe') queueMicrotask(() => {
          if (record.active) callback(structuredClone(analyses.get(message.entry_id)));
        });
        return () => { record.active = false; };
      },
    };
    const hass = { states, connection, locale: { language: 'en', number_format: 'comma_decimal', time_zone: 'UTC' }, language: 'en',
      config: { time_zone: 'UTC' }, themes: { darkMode: true },
      async callWS(message) { calls.push(structuredClone(message)); return message.type === 'f1_sensor/entities' ? entries : {}; },
      async callService(...args) { calls.push(args); },
    };
    const send = (dataset, mutate = () => {}, entryId = entries[0].entry_id) => {
      const snapshot = datasets.get(`${entryId}:${dataset}`); snapshot.revision++; mutate(snapshot);
      for (const record of records) if (record.active && record.message?.type === 'f1_sensor/data/subscribe'
        && record.message.entry_id === entryId && record.message.data_keys.includes(dataset)) record.callback(structuredClone(snapshot));
    };
    const cards = [];
    const sendAnalysis = (mutate = () => {}, entryId = entries[0].entry_id) => {
      const snapshot = analyses.get(entryId); mutate(snapshot);
      for (const record of records) if (record.active && record.message?.type === 'f1_sensor/analysis/subscribe'
        && record.message.entry_id === entryId) record.callback(structuredClone(snapshot));
    };
    const mount = (custom = {}, entryId = entries[0].entry_id) => {
      const card = document.createElement('f1-sensor-card'); card.hass = hass;
      card.setConfig({ f1_entry_id: entryId, appearance: { font: 'system', logos: false },
        modules: [{ type: 'lap_chart', options: { metric: 'cumulative_lap_delta', reference_driver: '4', selected: ['81'], presentation: 'both' } }], ...custom });
      document.querySelector('#root').append(card); cards.push(card); return card;
    };
    window.raceTrace = { entries, datasets, analyses, connection, handlers, records, calls, hass, cards, send, sendAnalysis, mount,
      snapshot: (key = 'driver_positions', entryId = entries[0].entry_id) => datasets.get(`${entryId}:${key}`),
      diagnostics: () => ({ ...connectionDiagnostics(connection), activeSubscriptions: records.filter(record => record.active).length,
        connectionListeners: [...handlers.values()].reduce((sum, listeners) => sum + listeners.size, 0) }),
      disconnect() { connection.connected = false; for (const callback of handlers.get('disconnected') ?? []) callback(); },
      reconnect() { connection.connected = true; for (const callback of handlers.get('ready') ?? []) callback(); },
      remove() { for (const card of cards.splice(0)) card.remove(); },
    };
    for (let index = 0; index < cardCount; index++) mount(config, entries[Math.min(index, entries.length - 1)].entry_id);
    await Promise.all(cards.map(card => card.updateComplete));
  }, { config, entries, cards });
}

module.exports = { mountRaceTrace };
