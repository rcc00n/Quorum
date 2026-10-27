const assert=require('node:assert/strict');
module.exports=async({page,browser,root})=>{
 await page.getByRole('link',{name:'Sources',exact:true}).click();await page.waitForURL('**/sources');
 await page.getByRole('heading',{name:'Source spectrum',level:1,exact:true}).waitFor();
 const day=await page.evaluate(()=>new Date().toLocaleDateString('en-CA'));
 const response=await page.request.get(`${root}/api/feed/?date=${day}`);assert.equal(response.status(),200);
 const data=await response.json();assert.equal(await page.locator('.source-row').count(),data.sources.length);
 for(const [i,source] of data.sources.entries())assert.ok((await page.locator('.source-row').nth(i).innerText()).includes(source.name));
 for(const width of [1440,768,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);}
 const visitor=await browser.newPage();try{
  await visitor.goto(root+'/sources');await visitor.waitForURL('**/login');
  assert.equal(await visitor.locator('.source-row').count(),0);
  assert.equal((await visitor.request.get(root+'/api/feed/')).status(),401);
 }finally{await visitor.close()}
 console.log('PASS: Sources navigation → authenticated registry map; exact source list/3 widths; anonymous route redirects and API denies');
};
