const {test, expect} = require('@playwright/test');
const observed = require('./unit/race-control-events.json');

test('Race Control renders one row per actual source event across log and sensor updates', async ({page}) => {
  await page.goto('/frontend-tests/fixture.html');
  await page.waitForFunction(() => typeof window.mountF1Element === 'function');
  await page.evaluate(async (observed) => {
    const host = document.createElement('f1-race-control-card');
    const base = window.makeHass();
    const listeners = {};
    window.raceControlListeners = listeners;
    host.setConfig({type:'custom:f1-race-control-card',entity:'sensor.race_control',display_mode:'list'});
    host.hass = {
      ...base,
      states:{...base.states,'sensor.race_control':observed.sensor_states[0]},
      callWS:async message => message.type === 'f1_sensor/race_control_log/get' ? {items:observed.backend_items} : base.callWS(message),
      connection:{...base.connection,subscribeEvents:async (callback, type) => {listeners[type]=callback;return () => delete listeners[type];}},
    };
    document.querySelector('#mount').append(host);
    await host.updateComplete;
  }, observed);
  const host = page.locator('f1-race-control-card');
  await expect(host.locator('.rc-list-row')).toHaveCount(2);
  await page.evaluate((state) => {
    const host = document.querySelector('f1-race-control-card');
    host.hass = {...host.hass,states:{...host.hass.states,'sensor.race_control':state}};
  }, observed.sensor_states[1]);
  await expect(host.locator('.rc-list-row')).toHaveCount(2);
  await page.evaluate((item) => window.raceControlListeners.f1_sensor_race_control_event({data:{entity_id:'sensor.race_control',log_item:{...item,event_id:'later',utc:'2026-09-05T11:22:41Z',sequence:12}}}), observed.backend_items[0]);
  await expect(host.locator('.rc-list-row')).toHaveCount(3);
  await page.evaluate(() => window.raceControlListeners.f1_sensor_race_control_log_reset_event({data:{entity_id:'sensor.other'}}));
  await expect(host.locator('.rc-list-row')).toHaveCount(3);
  await page.evaluate(() => window.raceControlListeners.f1_sensor_race_control_log_reset_event({data:{entity_id:'sensor.race_control'}}));
  await expect(host.locator('.rc-list-row')).toHaveCount(0);
});

for (const [type, selector] of [
  ['f1-practice-timing-card', '.pt-row:not(.header) .pt-lap'],
  ['f1-driver-lap-times-card', '.dl-row:not(.header) [data-col-key="best_lap"]'],
  ['f1-race-lap-card', '.rl-row:not(.header) .rl-lap'],
]) {
  test(`${type} renders corrected best laps without resurrecting a deleted time`, async ({page}) => {
    await page.setViewportSize({width:360,height:900});
    await page.goto('/frontend-tests/fixture.html');
    await page.waitForFunction(() => typeof window.mountF1Element === 'function');
    await page.evaluate(async (type) => {
      const host = document.createElement(type);
      const base = window.makeHass();
      const driver = {racing_number:'3',tla:'VER',name:'Max VERSTAPPEN',current_position:'4',completed_laps:18,laps:{17:'1:41.181',18:'1:41.293'},best_lap_time:'1:23.000',best_lap_time_secs:83,best_lap_lap:8};
      const session = type === 'f1-race-lap-card' ? 'Race' : 'Practice 3';
      host.setConfig({type:`custom:${type}`,positions_entity:'sensor.positions',drivers_entity:'sensor.drivers',session_entity:'sensor.session',session_status_entity:'sensor.status',show_team_logo:false});
      window.updateBestLapFixture = async (value) => {
        driver.best_lap_time = value;
        host.hass = {...base,states:{...base.states,
          'sensor.positions':{state:'18',attributes:{drivers:[{...driver}]}},
          'sensor.drivers':{state:'1',attributes:{drivers:[{racing_number:'3',tla:'VER',name:'Max VERSTAPPEN'}]}},
          'sensor.session':{state:session,attributes:{name:session,resolved_label:session,type:type === 'f1-race-lap-card' ? 'Race' : 'Practice',number:3}},
          'sensor.status':{state:'live',attributes:{}},
        }};
        await host.updateComplete;
      };
      document.querySelector('#mount').append(host);
      await window.updateBestLapFixture('1:23.000');
    }, type);
    const host = page.locator(type);
    const values = host.locator(selector);
    const best = type === 'f1-driver-lap-times-card' ? values.first() : values.nth(1);
    await expect(best).toContainText('1:23.000');
    await page.evaluate(() => window.updateBestLapFixture('1:24.000'));
    await expect(best).toContainText('1:24.000');
    await page.evaluate(() => window.updateBestLapFixture(null));
    await expect(best).toContainText('--:--.---');
    await expect(host).toContainText('1:41.293');
  });
}
