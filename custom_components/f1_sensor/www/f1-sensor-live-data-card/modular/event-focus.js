// A selected event is usable only within the original observed data context.
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
const cursor = value => Number.isSafeInteger(value?.sequence) && value.sequence > 0
  && Number.isSafeInteger(value.source_time_ms) && value.source_time_ms >= 0
  && ['utc', 'replay_offset'].includes(value.time_domain);
const before = (value, boundary) => cursor(value) && cursor(boundary)
  && value.time_domain === boundary.time_domain && value.sequence <= boundary.sequence
  && value.source_time_ms <= boundary.source_time_ms;
const identity = value => value && text(value.token) && text(value.source_epoch)
  && Number.isSafeInteger(value.delay_epoch) && value.delay_epoch >= 0
  ? JSON.stringify([value.entry_id, value.source, value.session_id, value.source_epoch,
    value.delay_epoch, value.delay_seconds, value.token]) : null;
const envelope = (value, entryId, dataset) => value?.protocol_version === 1
  && value.entry_id === entryId && value.dataset === dataset && value.status === 'ready'
  && text(value.generation) && Number.isSafeInteger(value.revision) && value.revision > 0
  && ['live', 'replay'].includes(value.source);

export function eventFocusContext(entry, analysisResource, connected = true) {
  const pending = reason => ({ status: 'pending', reason, contextKey: null });
  const directResource = entry?.card_data?.driver_positions, sessionResource = entry?.card_data?.session_context;
  const direct = directResource?.data, session = sessionResource?.data, analysis = analysisResource?.data;
  if (!connected || sessionResource?.status !== 'ready' || directResource?.status !== 'ready'
    || analysisResource?.status !== 'ready') return pending('waiting_for_sources');
  if (!envelope(direct, entry.entry_id, 'driver_positions') || !envelope(session, entry.entry_id, 'session_context')
    || session.payload?.attributes?.no_spoiler !== false) return pending('unsafe_context');
  const a = direct.context, b = session.context;
  if (!text(a?.session_id) || !Number.isSafeInteger(a.replay_generation) || a.replay_generation < 0
    || typeof a.delay_seconds !== 'number' || !Number.isFinite(a.delay_seconds) || a.delay_seconds < 0
    || direct.source !== session.source || direct.generation !== session.generation
    || a.session_id !== b?.session_id || a.replay_generation !== b?.replay_generation
    || a.delay_seconds !== b?.delay_seconds) return pending('mismatched_context');
  const obs = direct.payload?.attributes?.race_trace_observation, marker = analysis?.race_trace_markers;
  const id = identity(obs?.context);
  if (obs?.version !== 1 || obs.status !== 'ready' || !id || obs.context.entry_id !== entry.entry_id
    || obs.context.source !== direct.source || obs.context.session_id !== a.session_id
    || obs.context.delay_seconds !== a.delay_seconds || !cursor(obs.timing_as_of)
    || obs.timing_as_of.time_domain !== (direct.source === 'live' ? 'utc' : 'replay_offset')
    || analysis?.protocol_version !== 1 || analysis.status !== 'ready' || !text(analysis.session_id)
    || marker?.version !== 1 || marker.status !== 'ready' || identity(marker.context) !== id)
    return pending('unverified_observation');
  if (!Array.isArray(analysis.timeline?.events) || analysis.timeline.events.length > 500
    || !Array.isArray(marker.events) || marker.events.length > 500) return pending('invalid_events');
  const events = new Map();
  for (const event of analysis.timeline.events) {
    const key = text(event?.event_id);
    if (key) { if (!events.has(key)) events.set(key, []); events.get(key).push(event); }
  }
  return { status: 'ready', contextKey: JSON.stringify([id, direct.generation, a.replay_generation, analysis.session_id]),
    identity: id, boundary: obs.timing_as_of, sessionId: analysis.session_id, events, markers: marker.events };
}

export function resolveEventFocus(source, selection) {
  const pending = reason => ({ status: 'pending', reason, event: null });
  if (source?.status !== 'ready' || !text(selection?.contextKey) || selection.contextKey !== source.contextKey
    || !text(selection.eventId) || !(source.events instanceof Map)) return pending('invalid_selection');
  const matches = source.events.get(selection.eventId) ?? [];
  if (!matches.length) return pending('event_unavailable');
  const latest = matches.reduce((best, event) => (event.revision ?? 0) > (best.revision ?? 0) ? event : best);
  if (matches.some(event => event.revision === latest.revision && JSON.stringify(event) !== JSON.stringify(latest)))
    return pending('ambiguous_event');
  const obs = latest.focus_observation;
  // A frame may contain historical messages: its cursor alone does not prove
  // when an individual message occurred. Replay offsets need a verified index.
  const timestamp = typeof latest.occurred_at === 'string' ? latest.occurred_at : '';
  const unzonedUtc = obs?.event_time_basis === 'utc_field'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(timestamp);
  const utc = unzonedUtc ? Date.parse(`${timestamp}Z`)
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp)
      ? Date.parse(timestamp) : NaN;
  const matchingMarkers = source.markers.filter(item => item?.event_id === latest.event_id && item.revision === latest.revision);
  const marker = matchingMarkers.length === 1 ? matchingMarkers[0] : null;
  const singleFrame = obs?.event_time_basis === 'single_frame' && latest.category === 'track_status'
    && latest.kind === 'track_status_changed' && marker?.source === 'TrackStatus'
    && marker.context_token === obs.context?.token
    && JSON.stringify(marker.observation_cursor) === JSON.stringify(obs.timing_as_of);
  if (!singleFrame && (source.boundary.time_domain !== 'utc' || !Number.isFinite(utc)
    || utc > obs?.timing_as_of?.source_time_ms || utc > source.boundary.source_time_ms))
    return pending('event_time_unverified');
  if (!Number.isSafeInteger(latest.revision) || latest.revision < 1 || latest.session_id !== source.sessionId
    || obs?.version !== 1 || obs.status !== 'ready' || identity(obs.context) !== source.identity
    || !before(obs.timing_as_of, source.boundary)) return pending('event_unverified');
  return { status: 'ready', reason: null, event: latest };
}
