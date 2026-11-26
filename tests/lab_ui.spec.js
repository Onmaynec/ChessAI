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

test('chart range and raw CSV, report detail',async({page})=>{
 const fixture={runs:[{id:'r1',name:'r1'}],selected:'r1',process:{active:false},state:{status:'completed',iteration:40},metadata:{},metrics:Array.from({length:40},(_,i)=>({iteration:i+1,train:{value_mse:i===12?null:i/40}})),games:[],log:[],file_warnings:[]};
 await page.route('**/api/overview*',r=>r.fulfill({json:fixture}));
 await page.route('**/api/analysis*',r=>r.fulfill({json:{series:[],evaluations:[{filename:'eval_fixture.json',candidate:'latest.pt',reference:'best.pt',suite:'holdout',statistics:{wins:2,draws:2,losses:1,unfinished:3}}]}}));
 await page.goto(root);await expect(page.locator('#main-chart svg')).toBeVisible();
 await page.locator('#chart-range').selectOption('25');await expect(page.locator('#chart-window')).toContainText('#16–40');
 await page.locator('#chart-smooth').check();await expect(page.locator('#main-chart svg path')).toHaveCount(2);
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#chart-download').click()]);expect(download.suggestedFilename()).toContain('window.csv');
 await page.locator('[data-screen=evaluation]').click();await expect(page.locator('#evaluation-detail .eval-score strong')).toHaveText('60%');await expect(page.locator('#evaluation-detail')).toContainText('best.pt');
});

test('configuration draft survives closing and reloading, default KL is valid',async({page})=>{
 await page.goto(root);await expect(page.locator('#open-config')).toBeEnabled();await page.locator('#open-config').click();
 await page.locator('#c-iterations').fill('123');await page.keyboard.press('Escape');
 await page.reload();await expect(page.locator('#open-config')).toBeEnabled();await page.locator('#open-config').click();
 await expect(page.locator('#c-iterations')).toHaveValue('123');
 expect(await page.locator('#c-kl').evaluate(el=>el.checkValidity())).toBeTruthy();
 await page.locator('#draft-reset').click();await expect(page.locator('#c-iterations')).toHaveValue('10');
});
test('command palette supports keyboard selection and native Escape',async({page})=>{
 await page.goto(root);await page.keyboard.press('Control+k');await page.locator('#command-search').fill('модели');await page.keyboard.press('Enter');await expect(page.locator('#screen-models')).toBeVisible();
 await page.keyboard.press('Control+k');await page.keyboard.press('Escape');await expect(page.locator('#command-dialog')).not.toBeVisible();
});
test('replay uses saved FEN, rotates coordinates and plays without backend writes',async({page})=>{
 const fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
 const after='rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
 await page.route('**/api/overview*',r=>r.fulfill({json:{runs:[{id:'r1',name:'r1'}],selected:'r1',process:{active:false},state:{},metrics:[],games:[{game_id:1,iteration:1,result:'*',plies:1}],log:[],file_warnings:[]}}));
 await page.route('**/api/game/1?*',r=>r.fulfill({json:{game_id:1,iteration:1,result:'*',plies:1,moves:['e2e4'],fens:[fen,after]}}));
 await page.goto(root);await page.locator('#recent-games .view-game').click();
 await expect(page.locator('#replay-board .square').first()).toHaveAttribute('title','a8');
 await page.locator('#replay-flip').click();await expect(page.locator('#replay-board .square').first()).toHaveAttribute('title','h1');
 await page.locator('#replay-play').click();await expect(page.locator('#replay-step')).toHaveText('1 / 1');
 await expect(page.locator('#replay-board .last')).toHaveCount(2);await page.keyboard.press('Escape');await expect(page.locator('#game-overlay')).not.toBeVisible();
});
