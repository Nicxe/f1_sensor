// Render the shipped card components with deterministic, illustrative data.
// The values and sample circuit below are not real race results or telemetry.
const COMPONENT_ROOT = '/custom_components/f1_sensor/www/f1-sensor-live-data-card';
for (const tag of ['ha-card', 'ha-select', 'ha-textfield', 'ha-switch', 'ha-formfield', 'ha-icon-button', 'ha-control-button']) {
  if (!customElements.get(tag)) customElements.define(tag, class extends HTMLElement {});
}
// Material Design Icons (Pictogrammers), Apache-2.0. See cards-icons-license.txt.
const iconPaths = {"mdi:weather-partly-cloudy": "M12.74,5.47C15.1,6.5 16.35,9.03 15.92,11.46C17.19,12.56 18,14.19 18,16V16.17C18.31,16.06 18.65,16 19,16A3,3 0 0,1 22,19A3,3 0 0,1 19,22H6A4,4 0 0,1 2,18A4,4 0 0,1 6,14H6.27C5,12.45 4.6,10.24 5.5,8.26C6.72,5.5 9.97,4.24 12.74,5.47M11.93,7.3C10.16,6.5 8.09,7.31 7.31,9.07C6.85,10.09 6.93,11.22 7.41,12.13C8.5,10.83 10.16,10 12,10C12.7,10 13.38,10.12 14,10.34C13.94,9.06 13.18,7.86 11.93,7.3M13.55,3.64C13,3.4 12.45,3.23 11.88,3.12L14.37,1.82L15.27,4.71C14.76,4.29 14.19,3.93 13.55,3.64M6.09,4.44C5.6,4.79 5.17,5.19 4.8,5.63L4.91,2.82L7.87,3.5C7.25,3.71 6.65,4.03 6.09,4.44M18,9.71C17.91,9.12 17.78,8.55 17.59,8L19.97,9.5L17.92,11.73C18.03,11.08 18.05,10.4 18,9.71M3.04,11.3C3.11,11.9 3.24,12.47 3.43,13L1.06,11.5L3.1,9.28C3,9.93 2.97,10.61 3.04,11.3M19,18H16V16A4,4 0 0,0 12,12A4,4 0 0,0 8,16H6A2,2 0 0,0 4,18A2,2 0 0,0 6,20H19A1,1 0 0,0 20,19A1,1 0 0,0 19,18Z", "mdi:road-variant": "M18.1,4.8C18,4.3 17.6,4 17.1,4H13L13.2,7H10.8L11,4H6.8C6.3,4 5.9,4.4 5.8,4.8L3.1,18.8C3,19.4 3.5,20 4.1,20H10L10.3,15H13.7L14,20H19.8C20.4,20 20.9,19.4 20.8,18.8L18.1,4.8M10.4,13L10.6,9H13.2L13.4,13H10.4Z", "mdi:water-percent": "M12,3.25C12,3.25 6,10 6,14C6,17.32 8.69,20 12,20A6,6 0 0,0 18,14C18,10 12,3.25 12,3.25M14.47,9.97L15.53,11.03L9.53,17.03L8.47,15.97M9.75,10A1.25,1.25 0 0,1 11,11.25A1.25,1.25 0 0,1 9.75,12.5A1.25,1.25 0 0,1 8.5,11.25A1.25,1.25 0 0,1 9.75,10M14.25,14.5A1.25,1.25 0 0,1 15.5,15.75A1.25,1.25 0 0,1 14.25,17A1.25,1.25 0 0,1 13,15.75A1.25,1.25 0 0,1 14.25,14.5Z", "mdi:weather-windy": "M4,10A1,1 0 0,1 3,9A1,1 0 0,1 4,8H12A2,2 0 0,0 14,6A2,2 0 0,0 12,4C11.45,4 10.95,4.22 10.59,4.59C10.2,5 9.56,5 9.17,4.59C8.78,4.2 8.78,3.56 9.17,3.17C9.9,2.45 10.9,2 12,2A4,4 0 0,1 16,6A4,4 0 0,1 12,10H4M19,12A1,1 0 0,0 20,11A1,1 0 0,0 19,10C18.72,10 18.47,10.11 18.29,10.29C17.9,10.68 17.27,10.68 16.88,10.29C16.5,9.9 16.5,9.27 16.88,8.88C17.42,8.34 18.17,8 19,8A3,3 0 0,1 22,11A3,3 0 0,1 19,14H5A1,1 0 0,1 4,13A1,1 0 0,1 5,12H19M18,18H4A1,1 0 0,1 3,17A1,1 0 0,1 4,16H18A3,3 0 0,1 21,19A3,3 0 0,1 18,22C17.17,22 16.42,21.66 15.88,21.12C15.5,20.73 15.5,20.1 15.88,19.71C16.27,19.32 16.9,19.32 17.29,19.71C17.47,19.89 17.72,20 18,20A1,1 0 0,0 19,19A1,1 0 0,0 18,18Z", "mdi:weather-windy-variant": "M6,6L6.69,6.06C7.32,3.72 9.46,2 12,2A5.5,5.5 0 0,1 17.5,7.5L17.42,8.45C17.88,8.16 18.42,8 19,8A3,3 0 0,1 22,11A3,3 0 0,1 19,14H6A4,4 0 0,1 2,10A4,4 0 0,1 6,6M6,8A2,2 0 0,0 4,10A2,2 0 0,0 6,12H19A1,1 0 0,0 20,11A1,1 0 0,0 19,10H15.5V7.5A3.5,3.5 0 0,0 12,4A3.5,3.5 0 0,0 8.5,7.5V8H6M18,18H4A1,1 0 0,1 3,17A1,1 0 0,1 4,16H18A3,3 0 0,1 21,19A3,3 0 0,1 18,22C17.17,22 16.42,21.66 15.88,21.12C15.5,20.73 15.5,20.1 15.88,19.71C16.27,19.32 16.9,19.32 17.29,19.71C17.47,19.89 17.72,20 18,20A1,1 0 0,0 19,19A1,1 0 0,0 18,18Z", "mdi:weather-cloudy": "M6,19A5,5 0 0,1 1,14A5,5 0 0,1 6,9C7,6.65 9.3,5 12,5C15.43,5 18.24,7.66 18.5,11.03L19,11A4,4 0 0,1 23,15A4,4 0 0,1 19,19H6M19,13H17V12A5,5 0 0,0 12,7C9.5,7 7.45,8.82 7.06,11.19C6.73,11.07 6.37,11 6,11A3,3 0 0,0 3,14A3,3 0 0,0 6,17H19A2,2 0 0,0 21,15A2,2 0 0,0 19,13Z", "mdi:gauge": "M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12C20,14.4 19,16.5 17.3,18C15.9,16.7 14,16 12,16C10,16 8.2,16.7 6.7,18C5,16.5 4,14.4 4,12A8,8 0 0,1 12,4M14,5.89C13.62,5.9 13.26,6.15 13.1,6.54L11.81,9.77L11.71,10C11,10.13 10.41,10.6 10.14,11.26C9.73,12.29 10.23,13.45 11.26,13.86C12.29,14.27 13.45,13.77 13.86,12.74C14.12,12.08 14,11.32 13.57,10.76L13.67,10.5L14.96,7.29L14.97,7.26C15.17,6.75 14.92,6.17 14.41,5.96C14.28,5.91 14.15,5.89 14,5.89M10,6A1,1 0 0,0 9,7A1,1 0 0,0 10,8A1,1 0 0,0 11,7A1,1 0 0,0 10,6M7,9A1,1 0 0,0 6,10A1,1 0 0,0 7,11A1,1 0 0,0 8,10A1,1 0 0,0 7,9M17,9A1,1 0 0,0 16,10A1,1 0 0,0 17,11A1,1 0 0,0 18,10A1,1 0 0,0 17,9Z"};
class PreviewIcon extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});}
  set icon(value){this._icon=value;this.render();}
  get icon(){return this._icon;}
  connectedCallback(){this.render();}
  render(){const d=iconPaths[this._icon||this.getAttribute('icon')];this.shadowRoot.innerHTML=d?`<style>:host{display:inline-flex;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px)}svg{width:100%;height:100%;fill:currentColor}</style><svg viewBox="0 0 24 24"><path d="${d}"/></svg>`:'';}
}
customElements.define('ha-icon',PreviewIcon);
const fixedDate = '2026-06-07T12:00:00Z';
const entityState = (state, attributes = {}) => ({ state: String(state), attributes, last_changed: fixedDate, last_updated: fixedDate });
const identities = [
  { driver_number: 4, tla: 'NOR', name: 'Lando Norris', team: 'McLaren', team_color: '#ff8700' },
  { driver_number: 16, tla: 'LEC', name: 'Charles Leclerc', team: 'Ferrari', team_color: '#e8002d' },
  { driver_number: 63, tla: 'RUS', name: 'George Russell', team: 'Mercedes', team_color: '#27f4d2' },
  { driver_number: 1, tla: 'VER', name: 'Max Verstappen', team: 'Red Bull', team_color: '#6692ff' },
  { driver_number: 81, tla: 'PIA', name: 'Oscar Piastri', team: 'McLaren', team_color: '#ffb568' },
  { driver_number: 44, tla: 'HAM', name: 'Lewis Hamilton', team: 'Ferrari', team_color: '#fa6a82' },
];
const progression = [[25,43,68,80,105,123],[18,43,58,83,98,116],[15,27,45,63,78,103],[12,27,39,54,79,94],[10,20,32,42,60,78],[8,16,26,41,51,66]];
const positions = [[2,2,1,1,1,1,2,2,1,1,1,1],[1,1,2,2,2,2,1,1,2,2,2,2],[4,4,4,3,3,3,3,3,3,3,3,3],[3,3,3,4,4,4,4,4,4,4,4,4],[6,6,5,5,5,5,5,6,6,5,5,5],[5,5,6,6,6,6,6,5,5,6,6,6]];
const lapSession = {
  key: 'race:2026:6', type: 'race', season: 2026, round: 6,
  race_name: 'Sample Grand Prix', status: 'available', total_laps: 12, driver_count: 6,
  labels: Array.from({length:12},(_,i)=>`L${i+1}`),
  drivers: identities.map((driver,index)=>({ driver_id: driver.tla.toLowerCase(), code: driver.tla, name: driver.name, color: driver.team_color, constructor_name: driver.team, positions: positions[index], grid: positions[index][0], finish_position: index+1, status:'Finished' })),
};
const state = {
  'sensor.f1_current_session': entityState('Race', {meeting_name:'Sample Grand Prix', session_name:'Race', session_type:'Race'}),
  'sensor.f1_session_status': entityState('live'),
  'sensor.f1_driver_list': entityState(6, {drivers: identities}),
  'sensor.f1_driver_positions': entityState('available', {drivers: Object.fromEntries(identities.map((d,i)=>[d.driver_number,{position:i+1, racing_number:String(d.driver_number), tla:d.tla}]))}),
  'sensor.f1_race_lap_count': entityState(24, {total_laps:57}),
  'sensor.f1_track_status': entityState('CLEAR'),
  'sensor.f1_next_race': entityState('2026-06-07T14:00:00Z', {race_name:'Sample Grand Prix', circuit_name:'Sample circuit', circuit_locality:'Circuit location', race_start_utc:'2026-06-07T14:00:00Z'}),
  'sensor.f1_weather': entityState(24, {unit_of_measurement:'°C',current_temperature:24,current_weather_code:2,current_humidity:54,current_wind_speed:3.2,current_precipitation_probability:15,current_cloud_cover:35,race_temperature:26,race_weather_code:2,race_wind_speed:4.1,race_wind_gusts:6,race_wind_from_direction_degrees:225,race_precipitation:0.2,race_precipitation_probability:20,race_cloud_cover:40,race_humidity:51}),
  'sensor.f1_track_weather': entityState(25, {unit_of_measurement:'°C',air_temperature:25,track_temperature:39,rainfall:0,humidity:53,pressure:1014,wind_speed:3.5,wind_from_direction_degrees:210}),
  'sensor.f1_driver_points_progression': entityState('available',{season:2026,rounds:Array.from({length:6},(_,i)=>({round:i+1,label:`R${i+1}`,race_name:`Sample round ${i+1}`})),drivers:identities.map((d,i)=>({code:d.tla,name:d.name,team_name:d.team,color:d.team_color,values:progression[i]}))}),
  'sensor.f1_lap_position_progression': entityState('available',{sessions:[{...lapSession,drivers:undefined}]}),
  'switch.f1_no_spoiler_mode': entityState('off'),
  'input_boolean.f1_no_spoiler_mode': entityState('off'),
};
// Illustrative circuit geometry, intentionally not named after a real circuit.
const trackPoints = [[0,0],[190,0],[205,20],[195,50],[135,80],[120,105],[160,140],[220,165],[275,150],[320,100],[310,45],[360,10],[400,40],[415,140],[390,205],[330,230],[225,225],[170,195],[90,200],[40,165],[15,100],[0,0]];
const trackSnapshot = {
  source:'replay',status:'active',replay_state:'paused',stale:false,
  session:{key:'sample-race',meeting_name:'Sample Grand Prix',session_name:'Race'},
  track:{points:trackPoints,bounds:{min_x:0,max_x:415,min_y:0,max_y:230}},
  drivers:identities.map((d,i)=>({racing_number:String(d.driver_number),tla:d.tla,team_color:d.team_color,x:trackPoints[i*3+1][0],y:trackPoints[i*3+1][1],stale:false})),
};
const analysis = {
  status:'ready',provider:'replay',phase:'live',session_id:'sample-race',session_name:'Sample Grand Prix · Race',session_status:'Lap 24 of 57',drivers:identities,
  timing:identities.map((d,i)=>({driver_number:d.driver_number,position:i+1,gap_to_leader:i?`+${(i*2.7).toFixed(1)}`:'LEADER',interval_to_ahead:i?'+2.7':'LEADER'})),
  capabilities:{telemetry_compare:'ready',observed_streams:['TimingData','RaceControl','Weather','TimingAppData']},
  strategy:{status:'ready',stints:[{},{},{},{}],coverage:{clean_laps:82,raw_laps:94,observed_compounds:['SOFT','MEDIUM']}},
  battles:{active:[{driver_numbers:[4,16]}]},position_exchange_count:7,
  timeline:{events:[{title:'Race started',category:'session',lap_number:1,confidence:1},{title:'Pit stop recorded',category:'pit',lap_number:18,confidence:1},{title:'Battle for the lead',category:'battle',lap_number:23,confidence:0.9},{title:'Track clear',category:'race_control',lap_number:24,confidence:1}]},
};
const baseHass = () => ({
  states:state, locale:{language:'en-GB',time_format:'24',time_zone:'Europe/Stockholm'},language:'en-GB',
  config:{time_zone:'Europe/Stockholm',unit_system:{temperature:'°C',wind_speed:'m/s',pressure:'hPa'}},
  themes:{darkMode:true},user:{is_admin:true,name:'Documentation preview'},
  connection:{
    subscribeMessage:async(callback,message)=>{if(message.type.includes('/analysis/'))callback(analysis);if(message.type.includes('/track_map/'))callback({status:'active',snapshot:trackSnapshot});return ()=>{};},
    subscribeEvents:async()=>()=>{},
  },
  callWS:async(message)=>{
    if(message.type==='f1_sensor/entities')return [];
    if(message.type==='f1_sensor/lap_position/session')return {status:'available',session:lapSession};
    if(message.type.includes('/analysis/'))return analysis;
    if(message.type.includes('/track_map/'))return {status:'active',snapshot:trackSnapshot};
    return {};
  },
  callService:async()=>undefined,
  formatEntityState:e=>e?.state??'unknown',formatEntityAttributeValue:(e,k)=>e?.attributes?.[k]??'unknown',formatEntityAttributeName:(_e,k)=>k,
  formatNumber:(v,o)=>new Intl.NumberFormat('en-GB',o).format(v),localize:k=>k,
});
await import(`${COMPONENT_ROOT}/register.js?v=docs-preview`);
window.renderDocsCard = async(slug)=>{
  const cards={
    'weekend-hub':{type:'f1-weekend-hub-card',config:{entry_id:'docs-preview'}},
    'race-weather':{type:'f1-weather-card',config:{}},
    'season-progression':{type:'f1-season-progression-card',config:{show_future_rounds:false}},
    'lap-position-progression':{type:'f1-lap-position-progression-card',config:{}},
    'track-map':{type:'f1-track-map-card',config:{entry_id:'docs-preview',interpolation_ms:0}},
  };
  const spec=cards[slug];if(!spec)throw new Error(`No render fixture for ${slug}`);
  document.querySelector('#mount').replaceChildren();
  const element=document.createElement(spec.type);
  element.setConfig({type:`custom:${spec.type}`,theme_mode:'dark',font_style:'balanced',...spec.config});
  element.hass=baseHass();document.querySelector('#mount').append(element);
  await element.updateComplete;
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  await element.updateComplete;
  return spec.type;
};
