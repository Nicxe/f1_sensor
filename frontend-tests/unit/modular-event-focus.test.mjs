import assert from 'node:assert/strict';
import test from 'node:test';
import { eventFocusContext, resolveEventFocus } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/event-focus.js';

const cursor = sequence => ({ sequence, source_time_ms: sequence * 1000, time_domain: 'utc' });
const context = { entry_id: 'entry', source: 'live', session_id: '123', source_epoch: 'epoch', delay_epoch: 0, delay_seconds: 50, token: 'token' };
const observation = sequence => ({ version: 1, status: 'ready', context, timing_as_of: cursor(sequence) });
const direct = { protocol_version: 1, entry_id: 'entry', dataset: 'driver_positions', source: 'live', generation: 'generation', revision: 1, status: 'ready', context: { session_id: '123', replay_generation: 0, delay_seconds: 50 }, payload: { attributes: { race_trace_observation: observation(10) } } };
const session = { ...direct, dataset: 'session_context', payload: { attributes: { no_spoiler: false } } };
const entry = { entry_id: 'entry', card_data: { session_context: { status: 'ready', data: session }, driver_positions: { status: 'ready', data: direct } } };
const event = { event_id: 'event', revision: 1, session_id: 'meeting:123:Race', title: 'CAR 18 LAP 14 DELETED', driver_numbers: [18], lap_number: 14, occurred_at: '1970-01-01T00:00:08Z', focus_observation: observation(9) };
const snapshot = { protocol_version: 1, status: 'ready', session_id: 'meeting:123:Race', race_trace_markers: { version: 1, status: 'ready', context, events: [] }, timeline: { events: [event] } };
const resource = { status: 'ready', data: snapshot };

test('focus retains only a validated event and its original context', () => {
  const source = eventFocusContext(entry, resource, true);
  assert.equal(source.status, 'ready');
  const result = resolveEventFocus(source, { contextKey: source.contextKey, eventId: 'event' });
  assert.equal(result.status, 'ready'); assert.equal(result.event.lap_number, 14); assert.deepEqual(result.event.driver_numbers, [18]);
});
test('future, stale, unknown or wrong-context data cannot be selected', () => {
  const source = eventFocusContext(entry, resource, true);
  assert.notEqual(resolveEventFocus(source, { contextKey: 'old', eventId: 'event' }).status, 'ready');
  assert.notEqual(resolveEventFocus(source, { contextKey: source.contextKey, eventId: 'missing' }).status, 'ready');
  const future = { ...snapshot, timeline: { events: [{ ...event, focus_observation: observation(11) }] } };
  assert.notEqual(resolveEventFocus(eventFocusContext(entry, { status: 'ready', data: future }, true), { contextKey: source.contextKey, eventId: 'event' }).status, 'ready');
  const blocked = { ...entry, card_data: { ...entry.card_data, session_context: { status: 'ready', data: { ...session, payload: { attributes: { no_spoiler: true } } } } } };
  assert.notEqual(eventFocusContext(blocked, resource, true).status, 'ready');
  assert.notEqual(eventFocusContext(entry, resource, false).status, 'ready');
});

test('conflicting same-revision events and malformed context are rejected', () => {
  const source = eventFocusContext(entry, resource, true);
  const conflict = { ...snapshot, timeline: { events: [event, { ...event, lap_number: 15 }] } };
  assert.notEqual(resolveEventFocus(eventFocusContext(entry, { status: 'ready', data: conflict }), { contextKey: source.contextKey, eventId: 'event' }).status, 'ready');
  const malformed = { ...direct, context: { session_id: '123', delay_seconds: 50 } };
  const badEntry = { ...entry, card_data: { ...entry.card_data, driver_positions: { status: 'ready', data: malformed }, session_context: { status: 'ready', data: { ...session, context: malformed.context } } } };
  assert.notEqual(eventFocusContext(badEntry, resource).status, 'ready');
});

test('event focus is opt-in and old configurations remain compatible', async () => {
  const { normalizeConfig } = await import('../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js');
  const old = normalizeConfig({ modules: [{ type: 'timeline' }] });
  assert.equal(old.modules[0].options.event_focus, false);
  const enabled = normalizeConfig({ context: { scope: 'group', group: 'F1', share: ['focus', 'event_focus'] }, modules: [{ type: 'timeline', options: { event_focus: true } }] });
  assert.equal(enabled.modules[0].options.event_focus, true);
  assert.ok(enabled.context.share.includes('event_focus'));
});

test('batched events with future, missing or unverified event times cannot be inspected', () => {
  for (const occurred_at of ['1970-01-01T00:00:12Z', null, 'invalid']) {
    const candidate = { ...snapshot, timeline: { events: [{ ...event, occurred_at }] } };
    const source = eventFocusContext(entry, { status: 'ready', data: candidate });
    assert.notEqual(resolveEventFocus(source, { contextKey: source.contextKey, eventId: 'event' }).status, 'ready');
  }
});

test('a single observed track-status marker may be selected without a fabricated event time', () => {
  const marker = { event_id: 'track', revision: 1, context_token: context.token, observation_cursor: cursor(9), source: 'TrackStatus' };
  const trackEvent = { ...event, event_id: 'track', category: 'track_status', kind: 'track_status_changed', occurred_at: null,
    focus_observation: { ...observation(9), event_time_basis: 'single_frame' }, race_trace_marker: marker };
  const candidate = { ...snapshot, race_trace_markers: { ...snapshot.race_trace_markers, events: [marker] }, timeline: { events: [trackEvent] } };
  const source = eventFocusContext(entry, { status: 'ready', data: candidate });
  const selection = { contextKey: source.contextKey, eventId: 'track' };
  assert.equal(resolveEventFocus(source, selection).status, 'ready');
  marker.context_token = 'other';
  assert.notEqual(resolveEventFocus(source, selection).status, 'ready');
});


test('a timezone-free timestamp is accepted only when explicitly sourced from the UTC field', () => {
  const timed = { ...event, occurred_at: '1970-01-01T00:00:08', focus_observation: { ...observation(9), event_time_basis: 'utc_field' } };
  const candidate = { ...snapshot, timeline: { events: [timed] } };
  const source = eventFocusContext(entry, { status: 'ready', data: candidate });
  const selection = { contextKey: source.contextKey, eventId: 'event' };
  assert.equal(resolveEventFocus(source, selection).status, 'ready');
  delete timed.focus_observation.event_time_basis;
  assert.notEqual(resolveEventFocus(source, selection).status, 'ready');
});

test('replay focus accepts an observed single-frame marker but never assumes a batched message offset', () => {
  const replayContext = { ...context, source: 'replay' };
  const replayCursor = sequence => ({ sequence, source_time_ms: sequence * 1000, time_domain: 'replay_offset' });
  const replayObs = sequence => ({ version: 1, status: 'ready', context: replayContext, timing_as_of: replayCursor(sequence) });
  const replayDirect = { ...direct, source: 'replay', payload: { attributes: { race_trace_observation: replayObs(10) } } };
  const replaySession = { ...session, source: 'replay' };
  const replayEntry = { ...entry, card_data: { session_context: { status: 'ready', data: replaySession }, driver_positions: { status: 'ready', data: replayDirect } } };
  const marker = { event_id: 'track', revision: 1, context_token: replayContext.token, observation_cursor: replayCursor(9), source: 'TrackStatus' };
  const trackEvent = { ...event, event_id: 'track', category: 'track_status', kind: 'track_status_changed', occurred_at: null,
    focus_observation: { ...replayObs(9), event_time_basis: 'single_frame' } };
  const data = { ...snapshot, race_trace_markers: { ...snapshot.race_trace_markers, context: replayContext, events: [marker] },
    timeline: { events: [trackEvent, { ...event, focus_observation: replayObs(9) }] } };
  const source = eventFocusContext(replayEntry, { status: 'ready', data });
  assert.equal(resolveEventFocus(source, { contextKey: source.contextKey, eventId: 'track' }).status, 'ready');
  assert.notEqual(resolveEventFocus(source, { contextKey: source.contextKey, eventId: 'event' }).status, 'ready');
});
