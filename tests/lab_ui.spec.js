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

test('automatic reconnect without reloading',async({page})=>{
 let calls=0;await page.route('**/api/overview*',r=>++calls===1?r.abort():r.fulfill({json:{runs:[],selected:null,process:{active:false},state:null,metadata:null,metrics:[],games:[],log:[],file_warnings:[]}}));
 await page.goto(root);await expect(page.locator('#sync-label')).toContainText('Нет связи');await expect(page.locator('#open-config')).toBeDisabled();
 await expect(page.locator('#sync-label')).toContainText('Локальные данные',{timeout:15000});await expect(page.locator('#open-config')).toBeEnabled();
});

test('unchanged polling retains recent row',async({page})=>{
 const fixture={runs:[{id:'r1',name:'r1'}],selected:'r1',process:{active:true,run:'r1'},state:{status:'running'},metrics:[],games:[{game_id:1,iteration:1,result:'*',plies:1}],log:[],file_warnings:[]};
 await page.route('**/api/overview*',r=>r.fulfill({json:fixture}));await page.goto(root);
 const button=page.locator('#recent-games .view-game');await expect(button).toBeVisible();await button.evaluate(el=>el.dataset.identityProbe='keep');
 const response=page.waitForResponse(r=>r.url().includes('/api/overview'));await page.locator('#reload').click();await response;
 await expect(button).toHaveAttribute('data-identity-probe','keep');
});

// Actual application HTML/CSS/JS served by FastAPI, synthetic responses only.
test('all nine sections: desktop and mobile, empty and populated',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const sections=['overview','runs','games','analysis','evaluation','models','agents','system','guide'];
 let populated=false;
 const metrics=Array.from({length:32},(_,i)=>({iteration:i+1,train:{value_mse:.8-i*.01,policy_loss:-.03,entropy:1.2},games_per_s:1.2,plies_per_s:120}));
 await page.route('**/api/overview*',r=>r.fulfill({json:{runs:populated?[{id:'fixture_qa',name:'fixture_qa'}]:[],selected:populated?'fixture_qa':null,process:{active:false},state:populated?{status:'completed',iteration:32,counters:{games:128,finished:96,unfinished:32,white_wins:40,black_wins:36,draws:20}}:null,metadata:{},metrics:populated?metrics:[],games:[],log:populated?['[fixture] iteration complete']:[],file_warnings:[]}}));
 await page.route('**/api/games?*',r=>r.fulfill({json:{games:[]}}));
 await page.route('**/api/analysis?*',r=>r.fulfill({json:{series:metrics.map(m=>({iteration:m.iteration,value_mse:m.train.value_mse,finish_rate:75,approx_kl:.02,clip_fraction:.1,performance:{total_iteration_s:12,average_inference_batch:8}})),series_total:32,totals:{games:128,finished:96,samples:2000},arena:{},evaluations:[],checkpoint:{exists:true,size_bytes:1000000},warnings:[]}}));
 for(const state of ['empty','populated']){
  populated=state==='populated';await page.goto(root);await expect(page.locator('#sync-label')).toContainText('Локальные данные');
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:900});
   for(const screen of sections){
    await page.locator('[data-screen='+screen+']').click();await expect(page.locator('#screen-'+screen)).toBeVisible();
    await expect(page.locator('#heading-'+screen)).toBeVisible();await expect(page.locator('[data-screen='+screen+']')).toHaveAttribute('aria-current','page');
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);
    await page.screenshot({path:'test-results/final/'+state+'-'+width+'-'+screen+'.png',fullPage:true,animations:'disabled'});
   }
  }
 }
 expect(errors).toEqual([]);
});

test('model registry preserves main features and filters archive',async({page})=>{
 let calls=0;await page.route('**/api/models',r=>{calls++;return r.fulfill({json:{schema:'model_catalog_v1',models:[{name:'ChessNet Core',label:'ChessNet Core · r-1234567890',status:'active',selectable:true,role:'PPO',architecture:'64×6 CNN',revision:'r-1234567890',sha256:'1234567890',id:'runs/test/checkpoints/latest.pt',path:'runs/test/checkpoints/latest.pt'},{name:'ChessNet Historical',status:'archive',selectable:false,revision:'r-9876543210',id:'runs/test/checkpoints/old.pt'}]}})});
 await page.goto(root);await page.locator('[data-screen=models]').click();await expect(page.locator('#models-list .catalog-card')).toHaveCount(1);
 await expect(page.locator('#best-status')).toBeVisible();await expect(page.locator('#models-list')).toContainText('r-1234567890');
 await page.locator('#models-archive').check();await expect(page.locator('#models-list .catalog-card')).toHaveCount(2);
 await page.locator('#models-search').fill('Historical');await expect(page.locator('#models-list .catalog-card')).toHaveCount(1);
 await expect(page.locator('#models-list')).toContainText('ChessNet Historical');await page.locator('#models-refresh').click();await expect.poll(()=>calls).toBe(2);
 await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth)).toBe(390);
 await page.screenshot({path:'test-results/final/models-registry-mobile.png',fullPage:true});
});
