/* Render actual bundled cards with illustrative data; retain existing screenshots
 * for cards that already have a suitable image. See cards-provenance.md. */
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('@playwright/test');
const root = path.resolve(__dirname, '..');
const destinations = path.join(root, 'static/img/cards');
const rendered = ['weekend-hub', 'race-weather', 'season-progression', 'lap-position-progression', 'track-map'];
const retained = {
  'live-session':'live_session','next-race':'next_race','season-calendar':'season_calendar','race-control':'race_control','fia-documents':'fia_documents','qualifying-timing':'qualifying_timing','practice-timing':'practice_timing','race-lap':'race_lap','starting-grid':'starting_grid','results':'last_race_results','tyre-statistics':'tyres','pit-stops':'pitstops','driver-lap-times':'lap_times','investigations':'investigations','track-limits':'track_limits','championship-drivers':'prediction_drivers','championship-teams':'prediction_teams','replay-control':'replay_control',
};
const types = {'.js':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'};
const only = process.argv.find(arg=>arg.startsWith('--only='))?.slice(7).split(',');
const chosen = only || [...rendered,...Object.keys(retained)];
for (const slug of chosen) if(!rendered.includes(slug)&&!retained[slug])throw new Error(`Unknown card: ${slug}`);
const server = http.createServer(async(request,response)=>{
  const relative = decodeURIComponent(new URL(request.url,'http://localhost').pathname).replace(/^\/+/, '');
  const filename=path.resolve(root,relative);
  if(!filename.startsWith(root+path.sep)){response.writeHead(403).end();return;}
  try{const bytes=await fs.readFile(filename);response.writeHead(200,{'Content-Type':types[path.extname(filename)]||'application/octet-stream','Cache-Control':'no-store'}).end(bytes);}
  catch(error){response.writeHead(error.code==='ENOENT'?404:500).end('Not found');}
});
(async()=>{
  let browser;
  try{
    await fs.mkdir(destinations,{recursive:true});
    await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
    const origin=`http://127.0.0.1:${server.address().port}`;
    if(chosen.some(slug=>rendered.includes(slug)))browser=await chromium.launch();
    for(let batch=0;batch<chosen.length;batch+=3){
      console.log(`Preview batch ${Math.floor(batch/3)+1}: ${chosen.slice(batch,batch+3).join(', ')}`);
      for(const slug of chosen.slice(batch,batch+3)){
        const target=path.join(destinations,`${slug}.png`);
        if(retained[slug]){
          await fs.copyFile(path.join(root,'static/img',`placeholder_card_${retained[slug]}.png`),target);
          console.log(`${slug}: retained existing screenshot`);continue;
        }
        const page=await browser.newPage({viewport:{width:960,height:900},deviceScaleFactor:1,colorScheme:'dark',reducedMotion:'reduce'});
        const errors=[];page.on('pageerror',error=>errors.push(error.message));
        // Screenshots never fetch driver images, telemetry or other remote resources.
        await page.route('**/*',route=>route.request().url().startsWith(origin)||route.request().url().startsWith('data:')?route.continue():route.abort());
        await page.addInitScript(()=>{
          const RealDate=Date; const fixed=RealDate.parse('2026-06-07T12:00:00Z');
          window.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[fixed]));}static now(){return fixed;}};
        });
        await page.goto(`${origin}/docs-tests/cards-preview.html`);
        await page.waitForFunction(()=>typeof window.renderDocsCard==='function');
        const type=await page.evaluate(slug=>window.renderDocsCard(slug),slug);
        await page.locator(type).locator('ha-card').waitFor();
        await page.evaluate(()=>document.fonts.ready);
        await page.waitForTimeout(250);
        const content=await page.locator(type).innerText();
        if(/Connecting Weekend Hub|No progression data|No lap position data|Loading lap position data|Waiting for track map data/.test(content))throw new Error(`${slug}: preview has no usable data: ${content}`);
        if(errors.length)throw new Error(`${slug}: ${errors.join('; ')}`);
        await page.locator('#mount').screenshot({path:target,animations:'disabled'});
        console.log(`${slug}: captured actual component (${type})`);
        await page.close();
      }
    }
  }finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
