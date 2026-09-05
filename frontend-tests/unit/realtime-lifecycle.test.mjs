import test from 'node:test';
import assert from 'node:assert/strict';
import {card, browserWindow} from './card-module.mjs';

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
const snapshot = (session = 'race-A') => ({
  protocol_version: 1, status: 'ready', session_id: session, phase: 'live',
  drivers: [], capabilities: {telemetry_compare: 'ready'}, timeline: {events: []},
});
const hub = () => {
  const host = card('f1-weekend-hub-card');
  host.isConnected = true;
  host.setConfig({entry_id:'entry-A'});
  host._receiveSnapshot(snapshot());
  return host;
};
const fakeTimers = () => {
  const timers = new Map();
  const oldSet = browserWindow.setTimeout, oldClear = browserWindow.clearTimeout;
  let id = 0;
  browserWindow.setTimeout = (callback, delay) => {timers.set(++id, {callback, delay}); return id;};
  browserWindow.clearTimeout = (key) => timers.delete(key);
  return {timers, restore(){browserWindow.setTimeout=oldSet;browserWindow.clearTimeout=oldClear;}};
};
for (const type of ['f1-weekend-hub-card', 'f1-track-map-card']) {
  test(`${type} closes and retries a reload, including a late subscribe response`, async () => {
    const clock = fakeTimers();
    const host = card(type);
    host.isConnected = true;
    host.setConfig({entry_id:'entry-A'});
    if (type.includes('track-map')) {
      host._scheduleDraw=()=>{};
      host._scheduleStaleTransition=()=>{};
    }
    let emit, unsubscribed=0;
    const pending=deferred();
    host.hass.connection={subscribeMessage:(callback)=>{emit=callback;return pending.promise;}};
    try {
      const subscribing=host._ensureSubscription();
      emit({protocol_version:1,status:'closed',retryable:true,reason:'entry_unloaded',snapshot:null});
      pending.resolve(()=>{unsubscribed++;});
      await subscribing;
      assert.equal(unsubscribed,1, 'late subscription is detached');
      assert.equal(clock.timers.size,1, 'one bounded retry is owned');
      assert.equal(host._snapshot,null, 'old data is cleared');
      assert.equal(type.includes('track-map') ? host._unsubscribeTrackMap : host._unsubscribeAnalysis,null);
      host.isConnected=false;
      host._teardownSubscription();
      assert.equal(clock.timers.size,0);
    } finally {host._teardownSubscription();clock.restore();}
  });
  test(`${type} does not churn pending requests or retry permanent errors on hass updates`, async () => {
    const clock=fakeTimers();
    const host=card(type);
    host.isConnected=true;
    host.setConfig({entry_id:'entry-A'});
    const pending=deferred();
    let attempts=0;
    host.hass.connection={subscribeMessage:()=>{attempts++;return pending.promise;}};
    try {
      const first=host._ensureSubscription();
      const duplicate=host._ensureSubscription();
      const pendingAttempts=attempts;
      pending.reject({code:'unauthorized',message:'Access denied'});
      await Promise.all([first,duplicate]);
      assert.equal(pendingAttempts,1);
      for(let update=0;update<3;update++) await host._ensureSubscription();
      assert.equal(attempts,1);
      assert.equal(clock.timers.size,0);
    } finally {host._teardownSubscription();clock.restore();}
  });
}

test('telemetry from an old session cannot change new data, loading or errors', async () => {
  for (const outcome of ['success','error']) {
    const host=hub(), old=deferred(), current=deferred();
    host._telemetrySelections=[{driver_number:4,lap_number:10}];
    let calls=0;
    host.hass.callWS=()=>++calls===1?old.promise:current.promise;
    const first=host._compareTelemetry();
    host._receiveSnapshot(snapshot('race-B'));
    host._telemetrySelections=[{driver_number:81,lap_number:12}];
    const second=host._compareTelemetry();
    assert.equal(calls,2,'new session may compare without waiting for old response');
    if(outcome==='success') old.resolve({session_id:'race-A',series:[]});
    else old.reject(new Error('old error'));
    await first;
    assert.equal(host._telemetry,null);
    assert.equal(host._telemetryLoading,true,'old finally must not release current loading');
    assert.equal(host._telemetryError,null);
    current.resolve({session_id:'race-B',series:[]});
    await second;
    assert.equal(host._telemetry.session_id,'race-B');
    assert.equal(host._telemetryLoading,false);
  }
});
test('already displayed telemetry clears on session or entry change', async () => {
  const host=hub();
  host._telemetry={session_id:'race-A',series:[]};
  host._receiveSnapshot(snapshot('race-B'));
  assert.equal(host._telemetry,null);
  host._telemetry={session_id:'race-B',series:[]};
  host.setConfig({entry_id:'entry-B'});
  assert.equal(host._telemetry,null);
  assert.equal(host._snapshot,null);
});
test('selection changes and unmount invalidate pending telemetry including late errors', async () => {
  const host=hub(), old=deferred(), current=deferred();
  host._telemetrySelections=[{driver_number:4,lap_number:10}];
  host.hass.callWS=()=>old.promise;
  const first=host._compareTelemetry();
  host._telemetryLap=11;
  host._addTelemetrySelection(4);
  assert.equal(host._telemetryLoading,false);
  host.hass.callWS=()=>current.promise;
  const second=host._compareTelemetry();
  old.resolve({session_id:'race-A',series:[]});
  await first;
  assert.equal(host._telemetryLoading,true);
  host.isConnected=false;
  host.disconnectedCallback();
  current.reject(new Error('late error after disconnect'));
  await second;
  assert.equal(host._telemetry,null);
  assert.equal(host._telemetryError,null);
  assert.equal(host._telemetryLoading,false);
});

for (const type of ['f1-weekend-hub-card','f1-track-map-card']) {
  test(`${type} retries transient failures with capped backoff and resets on ready`, async () => {
    const clock=fakeTimers(), host=card(type), connection=new EventTarget();
    host.isConnected=true;
    host.setConfig({entry_id:'entry-A'});
    let attempts=0;
    connection.subscribeMessage=async()=>{attempts++;throw {code:'not_loaded',message:'Entry is reloading'};};
    host.hass.connection=connection;
    try {
      await host._ensureSubscription();
      for (const expected of [1000,2000,4000,8000,16000,30000,30000]) {
        assert.equal(clock.timers.size,1);
        const [id,{callback,delay}]=[...clock.timers][0];
        assert.equal(delay,expected);
        const before=attempts;
        await host._ensureSubscription();
        assert.equal(attempts,before,'HA state changes do not bypass backoff');
        clock.timers.delete(id);
        callback();
        await new Promise(setImmediate);
      }
      connection.dispatchEvent(new Event('disconnected'));
      assert.equal(clock.timers.size,0);
      const before=attempts;
      await host._ensureSubscription();
      assert.equal(attempts,before,'wait for connection ready while offline');
      connection.subscribeMessage=async()=>()=>{};
      connection.dispatchEvent(new Event('ready'));
      await new Promise(setImmediate);
      assert.equal(host._subscriptionRetryAttempt,0);
    } finally {host._teardownSubscription();host._unwatchSubscriptionConnection();clock.restore();}
  });
}
test('telemetry verifies loaded replay identity even when analysis SessionInfo has a different format', async () => {
  const host=hub();
  host._receiveSnapshot({...snapshot('1260:9852:Race'),replay:{session_id:'2026-italian-race'}});
  host._telemetrySelections=[{driver_number:4,lap_number:10}];
  host.hass.callWS=async()=>({session_id:'old-loaded-replay',series:[]});
  await host._compareTelemetry();
  assert.equal(host._telemetry,null);
  assert.equal(host._telemetryLoading,false);
  host.hass.callWS=async()=>({session_id:'2026-italian-race',series:[]});
  await host._compareTelemetry();
  assert.equal(host._telemetry.session_id,'2026-italian-race');
  host._receiveSnapshot({...snapshot('1260:9852:Race'),replay:{session_id:'new-loaded-replay'}});
  assert.equal(host._telemetry,null,'loaded replay change clears already displayed curves');
});
