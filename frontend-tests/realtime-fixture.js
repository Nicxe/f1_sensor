/** Deterministic HA websocket boundary: real cards receive complete product payloads. */
const copy = (value) => structuredClone(value);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve=yes; reject=no; });
  return {promise, resolve, reject};
};
const analysisSnapshot = (session = 'race-A') => ({
  protocol_version:1, status:'ready', provider:'replay', session_id:`1260:9852:${session}`,
  session_name:`Italian Grand Prix ${session}`, session_status:'Started', phase:'live',
  replay:{session_id:session,state:'playing',position_ms:1200000,duration_ms:5400000,paused:false},
  drivers:[{driver_number:4,tla:'NOR',name:'Lando Norris',team_name:'McLaren'}, {driver_number:81,tla:'PIA',name:'Oscar Piastri',team_name:'McLaren'}],
  timing:[{driver_number:4,position:1,gap_to_leader:null,interval_to_ahead:null},{driver_number:81,position:2,gap_to_leader:'+0.700',interval_to_ahead:'+0.700'}],
  timeline:{count:2,events:[
    {event_id:'start',category:'session',title:'Race started',driver_numbers:[],confidence:1,severity:'info'},
    {event_id:'pit',category:'pit_stop',title:'Norris completed pit stop',lap_number:20,driver_numbers:[4],confidence:0.95,severity:'info'},
  ]},
  strategy:{status:'ready',coverage:{raw_laps:40,clean_laps:34,observed_compounds:['MEDIUM','HARD']},
    stints:[{driver_number:4,driver_name:'NOR',compound:'MEDIUM',first_lap:1,last_lap:20,adjusted_median_clean_pace:82.123,median_clean_pace:82.3,degradation_seconds_per_lap:0.02,sample_count:17,raw_sample_count:20,excluded_laps:3,confidence_label:'High confidence'}],
    compound_comparison:[{compound:'MEDIUM',median_clean_pace:82.3,delta_to_fastest:0,sample_count:17},{compound:'HARD',median_clean_pace:82.5,delta_to_fastest:0.2,sample_count:17}],
    teammate_comparisons:[],undercut_overcut_outcomes:[],compound_crossover_indications:[]},
  position_exchange_count:1,position_exchange_retained_count:1,
  position_exchanges:[{kind:'position_exchange',driver_numbers:[4,81],confidence:0.85,gaining_driver:4,positions_before:{4:2,81:1},positions_after:{4:1,81:2},supporting_signals:['stable_positions']}],
  battles:{active:[{kind:'battle',driver_numbers:[4,81],gap_seconds:0.7,confidence:0.9,supporting_signals:['consecutive_close_gaps']}],history:[]},
  capabilities:{telemetry_compare:'ready',observed_streams:['SessionInfo','TimingData','RaceControlMessages','TimingAppData'],availability:{is_live:true,reason:'replay'},connection:'connected'},
});
const trackSnapshot = (session='race-A') => ({
  protocol_version:2,type:'snapshot',sequence:1,geometry_revision:0,status:'no_geometry',
  snapshot:{entry_id:'entry-A',status:'no_geometry',source:'replay',session:{key:session,name:`Italian Grand Prix ${session}`},track:null,drivers:[],updated_at:'2026-09-06T13:20:00Z'},
});
const telemetry = (session, selections) => ({
  protocol_version:1,provider:'replay',session_id:session,
  series:selections.map(({driver_number,lap_number})=>({driver_number,lap_number,sample_count:5,
    samples:[0,1,2,3,4].map(index=>({distance:index*500,time_s:index*5,speed:100+index*50,throttle:100,brake:0,gear:3+index,delta_s:0})),
    summary:{top_speed:300,distance:2000}})),
  limits:{max_selections:4,max_points_per_lap:500,cache_entries:8},
});

class RealtimeConnection extends EventTarget {
  constructor(){super();this.records=[];this.telemetryRequests=[];this.session='race-A';this.deferSubscriptions=false;this.deferTelemetry=false;this.offline=false;this.error=null;this.unsubscribed=0;this.autoResubscriptions=0;}
  async subscribeMessage(callback,message,options={}){
    if(this.offline) throw {code:'connection_lost',message:'Connection lost'};
    if(this.error) throw this.error;
    const record={callback,message,options,active:true,gate:this.deferSubscriptions?deferred():null};
    this.records.push(record);
    if(!record.gate) this.sendSnapshot(record);
    const unsubscribe=()=>{if(record.active){record.active=false;this.unsubscribed++;}};
    if(record.gate) await record.gate.promise;
    return unsubscribe;
  }
  subscribeEvents(){return Promise.resolve(()=>{});}
  sendSnapshot(record){
    if(record.message.type==='f1_sensor/analysis/subscribe') record.callback(analysisSnapshot(this.session));
    else if(record.message.type==='f1_sensor/track_map/subscribe') record.callback(trackSnapshot(this.session));
  }
  async callWS(message){
    if(message.type==='f1_sensor/analysis/telemetry_compare') {
      const record={session:this.session,selections:copy(message.selections),gate:this.deferTelemetry?deferred():null};
      this.telemetryRequests.push(record);
      return record.gate ? record.gate.promise : telemetry(record.session,record.selections);
    }
    if(message.type==='f1_sensor/entity_map') return [];
    return {};
  }
  closeEntry(reason='entry_unloaded') {
    for(const record of this.records.filter(item=>item.active)) record.callback({protocol_version:record.message.protocol_version||1,type:'snapshot',status:'closed',retryable:true,reason,snapshot:null});
  }
  loadSession(session){this.session=session;for(const record of this.records.filter(item=>item.active)) this.sendSnapshot(record);}
  settleSubscriptions(){this.deferSubscriptions=false;for(const record of this.records){if(record.gate){record.gate.resolve();record.gate=null;}}}
  settleTelemetry(index,error=false){const record=this.telemetryRequests[index];if(error) record.gate.reject(new Error('Old telemetry unavailable'));else record.gate.resolve(telemetry(record.session,record.selections));}
  disconnect(){this.offline=true;this.dispatchEvent(new Event('disconnected'));}
  reconnect(){this.offline=false;for(const record of this.records.filter(item=>item.active && item.options.resubscribe!==false)){this.autoResubscriptions++;this.subscribeMessage(record.callback,record.message,record.options);}this.dispatchEvent(new Event('ready'));}
  get active(){return this.records.filter(record=>record.active).length;}
}
window.mountF1Realtime = async ({language='en-GB',map=true,deferSubscriptions=false}={}) => {
  const container=document.querySelector('#mount');
  container.replaceChildren();
  container.className='';
  localStorage.removeItem('f1-sensor-dashboard-context-v1');
  window.__f1SensorDashboardContextStore?.update({entry_id:null,session_id:null,driver_number:null,spoiler_mode:false,gap_mode:'ahead'});
  const connection=new RealtimeConnection();
  connection.deferSubscriptions=deferSubscriptions;
  window.realtime=connection;
  for(const type of ['f1-weekend-hub-card',...(map?['f1-track-map-card']:[])]) {
    const host=document.createElement(type);
    host.setConfig({type:`custom:${type}`,entry_id:'entry-A',throttle_ms:100,no_spoiler_entity:'input_boolean.f1_no_spoiler_mode'});
    host.hass={...window.makeHass(language),connection,callWS:message=>connection.callWS(message)};
    container.append(host);
    await host.updateComplete;
  }
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
};
