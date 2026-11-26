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
