// Race Trace requires the direct lap contract. Entity history cannot establish
// source generations or whether a time was observed with its lap number.
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;

function envelope(data, entryId, dataset) {
  return data?.protocol_version === 1 && data.entry_id === entryId && data.dataset === dataset
    && text(data.generation) && Number.isSafeInteger(data.revision) && data.revision > 0
    && ['live', 'replay'].includes(data.source);
}

function contextIdentity(data) {
  const context = data?.context;
  if (!text(context?.session_id) || !Number.isSafeInteger(context.replay_generation) || context.replay_generation < 0
    || typeof context.delay_seconds !== 'number' || !Number.isFinite(context.delay_seconds) || context.delay_seconds < 0) return null;
  return JSON.stringify([data.entry_id, data.source, data.generation, context.session_id, context.replay_generation, context.delay_seconds]);
}

export function raceTraceSource(entry, connected = true) {
  const result = (status, reason, contextKey = null) => ({ status, reason, contextKey, drivers: [] });
  if (entry?.data_api?.configuration_required) return result('blocked', 'configuration_required');
  if (entry?.data_api?.lap_history_version !== 1
    || !['driver_positions', 'session_context'].every(key => entry.data_api.enabled?.includes(key))) return result('unsupported', 'unsupported_contract');

  const contextResource = entry.card_data?.session_context, context = contextResource?.data;
  if (contextResource?.status !== 'ready' || !envelope(context, entry.entry_id, 'session_context') || context.status !== 'ready') {
    return result('blocked', 'protection_unknown');
  }
  const protectedValue = context.payload?.attributes?.no_spoiler;
  if (protectedValue !== false) return result('blocked', protectedValue === true ? 'no_spoiler' : 'protection_unknown');
  const contextKey = contextIdentity(context);
  if (!contextKey) return result('pending', 'waiting_for_context');

  const resource = entry.card_data?.driver_positions, direct = resource?.data;
  if (direct?.status === 'blocked') return result('blocked', 'no_spoiler', contextKey);
  if (!connected || resource?.status !== 'ready') return result('pending', 'waiting_for_timing', contextKey);
  if (!envelope(direct, entry.entry_id, 'driver_positions') || contextIdentity(direct) !== contextKey) return result('pending', 'waiting_for_context', contextKey);
  if (direct.status !== 'ready') return result('pending', 'waiting_for_timing', contextKey);
  const attributes = direct.payload?.attributes;
  if (attributes?.lap_history_version !== 1) return result('pending', 'waiting_for_timing', contextKey);
  const kind = text(attributes.lap_history_session_type)?.toLowerCase();
  if (!kind || ['unknown', 'unavailable'].includes(kind)) return result('pending', 'waiting_for_session', contextKey);
  if (!['race', 'sprint'].includes(kind)) return result('not_applicable', 'race_or_sprint_required', contextKey);
  if (!Array.isArray(attributes.drivers)) return result('pending', 'waiting_for_timing', contextKey);
  return { status: 'ready', reason: null, contextKey, drivers: attributes.drivers, sessionType: kind,
    updatedAt: direct.timestamps?.received_at ?? null };
}

export function raceTraceSelectionKey(contextKey, options) {
  if (!contextKey) return null;
  const reference = String(options.reference_driver ?? '').trim();
  const selected = [...new Set((Array.isArray(options.selected) ? options.selected : [])
    .map(value => String(value).trim()).filter(value => value !== reference))].sort();
  // Revision, group focus and display range never change the comparison anchor.
  return JSON.stringify([contextKey, reference, selected, options.anchor_lap ?? 0]);
}

function observationIdentity(context, direct) {
  if (!text(context?.token) || !text(context.source_epoch)
    || !Number.isSafeInteger(context.delay_epoch) || context.delay_epoch < 0
    || context.entry_id !== direct.entry_id || context.source !== direct.source
    || context.session_id !== direct.context.session_id || context.delay_seconds !== direct.context.delay_seconds) return null;
  return JSON.stringify([context.token, context.entry_id, context.source, context.session_id,
    context.source_epoch, context.delay_epoch, context.delay_seconds]);
}

function observedCursor(cursor) {
  return Number.isSafeInteger(cursor?.sequence) && cursor.sequence > 0
    && Number.isSafeInteger(cursor.source_time_ms) && cursor.source_time_ms >= 0
    && ['utc', 'replay_offset'].includes(cursor.time_domain);
}

function observedBefore(cursor, boundary) {
  return observedCursor(cursor) && observedCursor(boundary) && cursor.time_domain === boundary.time_domain
    && cursor.sequence <= boundary.sequence && cursor.source_time_ms <= boundary.source_time_ms;
}

// Analysis revisions and publication/replay clocks cannot establish the timing
// frame the chart has consumed. Keep the base chart independent of this contract.
export function raceTraceMarkerSource(entry, analysisResource, connected = true) {
  const empty = (status, reason) => ({ status, reason, events: [] });
  const base = raceTraceSource(entry, connected);
  if (base.status !== 'ready') return empty('pending', base.reason);
  const direct = entry.card_data.driver_positions.data;
  const observation = direct.payload.attributes.race_trace_observation;
  const analysis = analysisResource?.data, snapshot = analysis?.race_trace_markers;
  if (analysisResource?.status !== 'ready') return empty('pending', 'waiting_for_analysis');
  if (analysis?.protocol_version !== 1 || observation?.version !== 1 || snapshot?.version !== 1) return empty('unavailable', 'unsupported_marker_contract');
  if (analysis.status !== 'ready' || observation.status !== 'ready' || snapshot.status !== 'ready') return empty('pending', 'waiting_for_observation');
  const identity = observationIdentity(observation.context, direct);
  if (!identity || observationIdentity(snapshot.context, direct) !== identity) return empty('pending', 'waiting_for_marker_context');
  const boundary = observation.timing_as_of;
  if (boundary?.time_domain !== (direct.source === 'replay' ? 'replay_offset' : 'utc')
    || !observedBefore(snapshot.as_of, boundary)) return empty('pending', 'waiting_for_timing_observation');
  if (!Array.isArray(snapshot.events) || snapshot.events.length > 500) return empty('unavailable', 'invalid_events');
  const invalid = new Set(), events = [];
  for (const event of snapshot.events) {
    const id = text(event?.event_id);
    if (!id) continue;
    if (event.context_token !== observation.context.token || !observedBefore(event.observation_cursor, snapshot.as_of)) {
      invalid.add(id); continue;
    }
    if (event.kind === 'pit') events.push(event);
    else {
      const anchors = event.reference_anchors;
      events.push({ ...event, reference_anchors: Object.fromEntries(Object.entries(
        anchors && typeof anchors === 'object' && !Array.isArray(anchors) ? anchors : {},
      ).map(([driver, anchor]) => [driver, observedBefore(anchor?.observation_cursor, event.observation_cursor) ? anchor : null])) });
    }
  }
  // A correction whose provenance is unsafe also vetoes all older revisions.
  return { status: 'ready', reason: null, contextKey: identity, asOf: snapshot.as_of,
    events: events.filter(event => !invalid.has(text(event.event_id))) };
}
