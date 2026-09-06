import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {card} from './card-module.mjs';
const cases=JSON.parse(readFileSync(new URL('./next-race-cases.json',import.meta.url)));
const plain=value=>JSON.parse(JSON.stringify(value));
const space=value=>value.replace(/[\u202f\u00a0]/g,' ');
function probe(p){
  const c=card('f1-next-race-card',p.config||{});if(p.hass)c.hass=p.hass;
  switch(p.action){
    case 'sections':return plain(c._resolveVisibleSections());
    case 'summary':return plain(c._resolveWeekendSummary(c._buildSessionItems(p.nextRace||{}),c._resolveTimelineState(c._buildSessionItems(p.nextRace||{}),p.currentSession||null,p.sessionStatus||null)));
    case 'round':return plain(c._getRoundSummary(p.nextRace||{}));
    case 'summary_cells':return plain(c._getSummaryCells(p.nextRace||{},p.currentSession||null,p.sessionStatus||null,p.countdown||null));
    case 'secondary':return plain(c._resolveSecondaryPanelState(p.sections||{},p.weather||null));
    case 'history_ribbon':return plain(c._getHistoryRibbonItems(p.nextRace||{}));
    case 'format_time':return space(c._formatTime(new Date(p.value),p.timeZone||'UTC'));
    case 'weekend_panel':return space(c._renderWeekendPanel(p.nextRace||{},p.currentSession||null,p.sessionStatus||null,p.layoutMode||'wide'));
    default:throw new Error(`Unsupported probe ${p.action}`);
  }
}
const checks={
  visibility_defaults_enable_all_sections:r=>assert.ok(Object.values(r).every(Boolean)),
  visibility_respects_disabled_sections:r=>assert.deepEqual(r,{header:false,countdown:true,overview:false,schedule:false,map:true,weather:true,history:false}),
  weekend_summary_prefers_live_session:r=>{assert.equal(r.label,'Live session');assert.equal(r.value,'Qualifying');assert.equal(r.chip,'Live');},
  weekend_summary_uses_next_upcoming_session:r=>{assert.equal(r.label,'Next session');assert.equal(r.value,'FP1');assert.equal(r.chip,'Next');},
  round_summary_prioritizes_round_and_season:r=>assert.deepEqual(r,{value:'Round 7',detail:'Season 2026'}),
  summary_cells_use_compact_four_cell_matrix:r=>{assert.deepEqual(r.map(i=>i.key),['weekend','race_start','countdown','round']);assert.equal(r[0].label,'Next session');assert.equal(r[0].chip,null);assert.equal(r[1].detail,null);},
  secondary_panel_hides_when_both_parts_are_absent:r=>assert.deepEqual(r,{showMap:false,showWeather:false,showPanel:false}),
  secondary_panel_keeps_map_when_weather_is_missing:r=>assert.deepEqual(r,{showMap:true,showWeather:false,showPanel:true}),
  history_ribbon_omits_empty_state:r=>assert.deepEqual(r,[]),
  time_format_follows_ha_12_hour_setting:r=>assert.equal(r,'06:30 PM'),
  time_format_follows_ha_24_hour_setting:r=>assert.equal(r,'18:30'),
  language_time_format_uses_locale_default:(r,index)=>assert.equal(r,index===0?'06:30 PM':'18:30'),
  schedule_formats_user_and_track_times_from_ha_locale:r=>{assert.ok(r.includes('06:30 PM'));assert.ok(r.includes('02:30 PM'));},
  schedule_places_next_chip_in_right_status_column:r=>{assert.match(r,/nr-schedule-cell status/);assert.ok(r.indexOf('nr-schedule-session-name">FP1</span>')<r.indexOf('nr-schedule-cell time">'));assert.ok(r.indexOf('nr-schedule-cell date compact">')<r.indexOf('>Next</span>'));},
  narrow_schedule_uses_full_width_rows:r=>{assert.match(r,/nr-schedule-row narrow/);assert.match(r,/nr-schedule-row-date/);assert.ok(r.indexOf('Sprint')<r.indexOf('nr-schedule-inline-times',r.indexOf('Sprint')));assert.ok(r.indexOf('nr-schedule-row-status',r.indexOf('FP1'))<r.indexOf('nr-schedule-row-bottom',r.indexOf('FP1')));},
  schedule_hides_track_column_when_disabled:r=>{assert.match(r,/nr-schedule-head track-hidden/);assert.ok(!r.includes('>Track</span>'));},
};
for(const [name,check] of Object.entries(checks))test(name.replaceAll('_',' '),()=>cases[name].forEach((p,index)=>check(probe(p),index)));
