const {test,expect}=require('@playwright/test');
const AxeBuilder=require('@axe-core/playwright').default;
const open=async(page,options={})=>{
  await page.goto('/frontend-tests/fixture.html');
  await page.waitForFunction(()=>typeof window.mountF1Realtime==='function');
  await page.evaluate(options=>window.mountF1Realtime(options),options);
};
const status=page=>page.evaluate(()=>({
  analysis:document.querySelector('f1-weekend-hub-card')._snapshot?.replay?.session_id,
  map:document.querySelector('f1-track-map-card')?._snapshot?.session?.key,
  active:window.realtime.active,total:window.realtime.records.length,
}));

for(const reason of ['entry_unloaded','options_reload']) {
  test(`open cards recover from ${reason} without remounting`,async({page})=>{
    await page.clock.install();
    await open(page);
    await expect.poll(()=>status(page)).toMatchObject({analysis:'race-A',map:'race-A',active:2});
    await page.evaluate(reason=>{window.realtime.closeEntry(reason);window.realtime.session='race-B';},reason);
    await expect.poll(()=>status(page)).toMatchObject({active:0});
    await page.clock.fastForward(1100);
    await expect.poll(()=>status(page)).toMatchObject({analysis:'race-B',map:'race-B',active:2,total:4});
  });
}
test('connection offline/online rebinds cards and late subscriptions release after unmount',async({page})=>{
  await open(page);
  await page.evaluate(()=>window.realtime.disconnect());
  await expect.poll(()=>status(page)).toMatchObject({active:0});
  await page.evaluate(()=>{window.realtime.session='race-B';window.realtime.reconnect();});
  await expect.poll(()=>status(page)).toMatchObject({analysis:'race-B',map:'race-B',active:2});
  await page.evaluate(()=>window.mountF1Realtime({deferSubscriptions:true}));
  await page.evaluate(()=>{document.querySelector('#mount').replaceChildren();window.realtime.settleSubscriptions();});
  await expect.poll(()=>page.evaluate(()=>window.realtime.active)).toBe(0);
});
test('terminal reload before subscribe resolution discards old callbacks and retries once',async({page})=>{
  await page.clock.install();
  await open(page,{deferSubscriptions:true});
  await page.evaluate(()=>{window.realtime.closeEntry();window.realtime.settleSubscriptions();window.realtime.session='race-B';});
  await page.clock.fastForward(1100);
  await expect.poll(()=>status(page)).toMatchObject({analysis:'race-B',map:'race-B',active:2,total:4});
  await page.evaluate(()=>{for(const record of window.realtime.records.slice(0,2)) record.callback({status:'ready',replay:{session_id:'obsolete'}});});
  await expect.poll(()=>status(page)).toMatchObject({analysis:'race-B',map:'race-B',active:2});
});

for(const profile of [{width:360,language:'sv-SE'},{width:700,language:'en-GB'},{width:1050,language:'zz-ZZ'}]) {
  test(`populated five views support keyboard, touch and axe at ${profile.width} ${profile.language}`,async({page},testInfo)=>{
    await page.setViewportSize({width:profile.width,height:1000});
    await open(page,{language:profile.language,map:false});
    const host=page.locator('f1-weekend-hub-card');
    for(const [index,view]of ['overview','timeline','strategy','telemetry','battles'].entries()) {
      const tab=host.locator('.wh-tab').nth(index);
      await tab.focus();
      await page.keyboard.press('Enter');
      await expect.poll(()=>page.evaluate(()=>document.querySelector('f1-weekend-hub-card')._activeView)).toBe(view);
      if(view==='telemetry') {
        await host.locator('.wh-telemetry-form .wh-button').tap();
        await host.locator('.wh-actions .wh-button').tap();
        await expect(host.locator('.wh-chart path')).toHaveCount(1);
        await expect(host.locator('.wh-chart')).toBeVisible();
      }
      if(view==='strategy') await expect(host.locator('.wh-content')).toContainText('82.123');
      if(view==='timeline') await expect(host.locator('.wh-event')).toHaveCount(2);
      if(view==='battles') await expect(host.locator('.wh-battle')).toHaveCount(2);
      const result=await new AxeBuilder({page}).include('f1-weekend-hub-card').analyze();
      expect(result.violations.filter(({impact})=>['serious','critical'].includes(impact))).toEqual([]);
      const overflow=await host.evaluate(element=>element.getBoundingClientRect().width>document.documentElement.clientWidth);
      expect(overflow).toBe(false);
      const image=testInfo.outputPath(`${view}-${profile.width}-${profile.language}.png`);
      await host.screenshot({path:image});
      await testInfo.attach(view,{path:image,contentType:'image/png'});
    }
    // The separate spoiler overlay remains in force with populated products.
    await host.locator('.wh-context .wh-button').tap();
    await expect(host.locator('.wh-spoiler')).toBeVisible();
    await expect(host.locator('.wh-battle')).toHaveCount(0);
    await host.locator('.wh-spoiler .wh-button').tap();
    await expect(host.locator('.wh-battle')).toHaveCount(2);
  });
}

test('late telemetry success/error/finally cannot cross session, selection or unmount boundaries',async({page})=>{
  await open(page,{map:false});
  const host=page.locator('f1-weekend-hub-card');
  await host.locator('.wh-tab').nth(3).tap();
  await page.evaluate(()=>{window.realtime.deferTelemetry=true;});
  await host.locator('.wh-telemetry-form .wh-button').tap();
  await host.locator('.wh-actions .wh-button').tap();
  await page.evaluate(()=>window.realtime.loadSession('race-B'));
  await host.locator('.wh-telemetry-form .wh-button').tap();
  await host.locator('.wh-actions .wh-button').tap();
  await page.evaluate(()=>window.realtime.settleTelemetry(0));
  await expect.poll(()=>host.evaluate(element=>({loading:element._telemetryLoading,telemetry:element._telemetry,error:element._telemetryError}))).toEqual({loading:true,telemetry:null,error:null});
  await page.evaluate(()=>window.realtime.settleTelemetry(1));
  await expect.poll(()=>host.evaluate(element=>element._telemetry?.session_id)).toBe('race-B');
  await host.locator('.wh-telemetry-form input').fill('2');
  await host.locator('.wh-telemetry-form .wh-button').tap();
  await host.locator('.wh-actions .wh-button').tap();
  await host.locator('.wh-telemetry-form input').fill('3');
  await host.locator('.wh-telemetry-form .wh-button').tap();
  await host.locator('.wh-actions .wh-button').tap();
  await page.evaluate(()=>window.realtime.settleTelemetry(2,true));
  await expect.poll(()=>host.evaluate(element=>({loading:element._telemetryLoading,error:element._telemetryError}))).toEqual({loading:true,error:null});
  await page.evaluate(()=>{window.detachedHub=document.querySelector('f1-weekend-hub-card');window.detachedHub.remove();window.realtime.settleTelemetry(3,true);});
  await expect.poll(()=>page.evaluate(()=>({loading:window.detachedHub._telemetryLoading,telemetry:window.detachedHub._telemetry,error:window.detachedHub._telemetryError}))).toEqual({loading:false,telemetry:null,error:null});
});


test('cards own reconnect without HA automatic re-subscription of pending requests',async({page})=>{
  await open(page,{deferSubscriptions:true});
  await page.evaluate(()=>{window.realtime.disconnect();window.realtime.deferSubscriptions=false;window.realtime.session='race-B';window.realtime.reconnect();window.realtime.settleSubscriptions();});
  await expect.poll(()=>status(page)).toMatchObject({analysis:'race-B',map:'race-B',active:2,total:4});
  expect(await page.evaluate(()=>window.realtime.autoResubscriptions)).toBe(0);
});
