import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {card} from './card-module.mjs';
const cases=JSON.parse(readFileSync(new URL('./practice-cases.json',import.meta.url)));
const run=name=>{
  const data=cases[`test_practice_card_${name}`];
  const host=card('f1-practice-timing-card',{title:'Free Practice',show_team_logo:false,team_logo_style:'color',session_entity:'sensor.f1_current_session',session_status_entity:'sensor.f1_session_status',positions_entity:'sensor.f1_driver_positions'});
  host.hass.states={'sensor.f1_current_session':data.session_state,'sensor.f1_session_status':data.session_status_state,'sensor.f1_driver_positions':{state:'ready',attributes:{}}};
  return {host,data,rows:host._buildRows(data.position_drivers||[],data.tyres_drivers||[],data.driver_list||[])};
};
test('suspended practice retains visibility and its last session label',()=>{
  const {host,data}=run('stays_visible_for_suspended_practice_last_label');assert.equal(host._isPracticeSession(data.session_state,data.session_status_state),true);assert.equal(host._buildTitle(data.session_state),'Free Practice 2');
});
test('practice title uses the reported session number',()=>{
  const {host,data}=run('prefers_session_number_for_title');assert.equal(host._buildTitle(data.session_state),'Free Practice 3');
});
test('usable driver attributes survive an unknown position state',()=>{
  const {host,data,rows}=run('uses_driver_attributes_when_position_state_unknown');assert.equal(host._hasUsableDriversEntity({state:'unknown',attributes:{drivers:data.position_drivers}}),true);assert.equal(rows[0].tla,'ANT');
});
test('practice derives ordering, pit status, fastest laps and tyres from history',()=>{
  const {rows}=run('derives_laps_and_status_from_driver_history');
  assert.deepEqual(Array.from(rows,r=>r.tla),['SAI','RUS','COL']);
  const expected=[{position:1,last_lap:'1:20.900',best_lap:'1:20.900',is_fastest:false},{position:2,status_label:'PIT',status_key:'pit-in',last_lap:'1:20.750',best_lap:'1:20.750',is_fastest:true,compound_short:'M',tyre_age:13},{position:22,last_lap:null,best_lap:null,is_fastest:false}];
  for(let i=0;i<rows.length;i++)for(const [key,value]of Object.entries(expected[i]))assert.equal(rows[i][key],value,`${i}:${key}`);
});
test('sector values preserve overall, personal and ordinary timing distinctions',()=>{
  const {rows:[row]}=run('exposes_current_sector_values_and_timing_classes');
  for(const [index,time,style] of [[1,26.123,'overall-fastest'],[2,31.456,'personal-fastest'],[3,28.789,'timed']]) {
    assert.ok(Math.abs(row[`sector_${index}`]-time)<0.000001);assert.equal(row[`sector_${index}_class`],style);
  }
});
