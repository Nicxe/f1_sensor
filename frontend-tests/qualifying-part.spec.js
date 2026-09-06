const {test, expect} = require('@playwright/test');
const observed = require('./unit/qualifying-part-events.json');

for (const [width, layout] of [[360,'narrow'], [700,'medium'], [1450,'wide']]) {
  test(`qualifying ${layout} labels each time with its actual Q part`, async ({page}) => {
    await page.setViewportSize({width, height:1000});
    await page.goto('/frontend-tests/fixture.html');
    await page.waitForFunction(() => typeof window.makeHass === 'function');
    await page.evaluate(async () => { await customElements.whenDefined('f1-qualifying-timing-card'); });
    await page.evaluate(async (observed) => {
      const host = document.createElement('f1-qualifying-timing-card');
      const base = window.makeHass();
      host.setConfig({type:'custom:f1-qualifying-timing-card', positions_entity:'sensor.positions', session_entity:'sensor.session', session_status_entity:'sensor.status', show_team_logo:false, show_delta:false});
      window.updateQualifyingPartFixture = async (part, time=null) => {
        const drivers = observed.drivers.map(driver => ({...driver,
          q2_time:part === 1 ? null : driver.q2_time,
          q2_position:part === 1 ? null : driver.q2_position,
          ...(driver.racing_number === '16' && part >= 2 ? {q2_time:part === 2 ? time : '1:23.500', q2_position:time || part === 3 ? 4 : null} : {}),
          ...(driver.racing_number === '16' && part === 3 ? {q3_time:time, q3_position:time ? 2 : null} : {}),
        }));
        host.hass = {...base, states:{...base.states,
          'sensor.positions':{state:'3',attributes:{current_qualifying_part:part, drivers}},
          'sensor.session':{state:'Qualifying',attributes:{name:'Qualifying',type:'Qualifying',session_part:part,meeting_key:1293}},
          'sensor.status':{state:'live',attributes:{}},
        }};
        await host.updateComplete;
      };
      document.querySelector('#mount').append(host);
      await window.updateQualifyingPartFixture(1);
    }, observed);
    const host = page.locator('f1-qualifying-timing-card');
    await expect(host.locator('.qt-card')).toHaveAttribute('data-layout', layout);
    const leclerc = host.locator('.qt-row:not(.header)').filter({hasText:'LEC'});
    const tsunoda = host.locator('.qt-row:not(.header)').filter({hasText:'TSU'});
    const lap = (row, part) => row.locator('.qt-lap').nth(layout === 'wide' ? part : 1);
    await expect(lap(leclerc,1)).toHaveText('1:22.902');
    await page.evaluate(() => window.updateQualifyingPartFixture(2));
    await expect(host.locator('.qt-q-badge')).toHaveText('Q2');
    await expect(lap(leclerc,2)).toHaveText('--:--.---');
    await expect(lap(tsunoda,2)).toHaveText('--:--.---');
    if (layout === 'wide') await expect(lap(leclerc,1)).toHaveText('1:22.902');
    await page.evaluate(() => window.updateQualifyingPartFixture(2,'1:23.500'));
    await expect(lap(leclerc,2)).toHaveText('1:23.500');
    await page.evaluate(() => window.updateQualifyingPartFixture(3));
    await expect(host.locator('.qt-q-badge')).toHaveText('Q3');
    await expect(lap(leclerc,3)).toHaveText('--:--.---');
    await page.evaluate(() => window.updateQualifyingPartFixture(3,'1:24.500'));
    await expect(lap(leclerc,3)).toHaveText('1:24.500');
    if (layout === 'wide') {
      await expect(lap(leclerc,1)).toHaveText('1:22.902');
      await expect(lap(leclerc,2)).toHaveText('1:23.500');
    }
  });
}
