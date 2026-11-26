// Optional UI smoke tests, run against a local dashboard with npx playwright test tests/lab_ui.spec.js.
// All API calls are intercepted; no production training action is executed.
const {test,expect}=require('@playwright/test');
const root=process.env.LAB_URL||'http://127.0.0.1:8765';
test.beforeEach(async({page})=>{
 await page.route('**/api/**',async route=>{
  const p=new URL(route.request().url()).pathname;
  if(route.request().method()!=='GET')return route.fulfill({status:409,json:{detail:'Fixture: writes disabled'}});
  if(p==='/api/health')return route.fulfill({json:{engine_ready:true}});
  if(p==='/api/overview')return route.fulfill({json:{runs:[],selected:null,process:{active:false},state:null,metadata:null,metrics:[],games:[],log:[],file_warnings:[]}});
  return route.fulfill({json:{}});
 });
});
test('empty state, navigation, command dialog, no fabricated metric',async({page})=>{
 await page.goto(root);
 await expect(page.locator('#m-games')).toHaveText('—');
 await page.locator('[data-screen=evaluation]').click();
 await expect(page.locator('#screen-evaluation')).toBeVisible();
 await page.keyboard.press('Control+k');
 await expect(page.locator('#command-dialog')).toBeVisible();
 await page.locator('#command-search').fill('Модели');
 await page.locator('#command-results button').click();
 await expect(page.locator('#screen-models')).toBeVisible();
});
test('mobile layout and advanced config',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto(root);
 await page.locator('#open-config').click();
 await expect(page.locator('#config-overlay')).toBeVisible();
 await page.locator('.advanced-config summary').click();
 await expect(page.locator('#c-workers')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('disconnect is distinguished from training state',async({page})=>{
 await page.route('**/api/overview',route=>route.abort());
 await page.goto(root);
 await expect(page.locator('#sync-label')).toContainText('Нет связи');
 await expect(page.locator('#open-config')).toBeDisabled();
});

// Visual Excellence regression matrix against the actual application, using isolated synthetic GET responses.
test('responsive populated overview and evaluation layout',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const fixture={runs:[{id:'fixture_visual_001',name:'fixture_visual_001'}],selected:'fixture_visual_001',process:{active:true,run:'fixture_visual_001'},state:{status:'running',phase:'selfplay',iteration:64,target_iteration:100,device:'cuda',counters:{games:1024,finished:896,unfinished:128,white_wins:384,black_wins:352,draws:160,plies:184320,samples:161280}},metadata:{parameters:1482720,config:{iterations:100}},metrics:Array.from({length:64},(_,i)=>({iteration:i+1,train:{value_mse:.94-i*.003,policy_loss:.02,entropy:1.1},games_per_s:.83,plies_per_s:148.9})),games:[],log:[],file_warnings:[]};
 await page.route('**/api/overview*',route=>route.fulfill({json:fixture}));
 await page.goto(root);await expect(page.locator('#run-title')).toHaveText('fixture_visual_001');
 await expect(page.locator('#main-chart svg')).toBeVisible();
 for(const [width,height] of [[1920,1080],[1366,768],[1280,720],[1024,768],[768,1024],[390,844],[320,720]]){
   await page.setViewportSize({width,height});
   await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
   await page.screenshot({path:'test-results/lab-overview-'+width+'.png',fullPage:true});
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.locator('[data-screen=evaluation]').click();await expect(page.locator('#screen-evaluation .research-grid')).toBeVisible();
 await page.screenshot({path:'test-results/lab-evaluation.png',fullPage:true});
 expect(errors).toEqual([]);
});
