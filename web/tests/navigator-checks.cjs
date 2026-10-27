const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
module.exports=async({page})=>{
 const needsReview=await page.locator('.story-review:visible').count()>0;
 const original=page.url(),dialog=page.getByRole('dialog',{name:'Go anywhere'}),input=page.getByRole('combobox',{name:'Search this edition and workspace'});
 await page.keyboard.press('Control+k');await dialog.waitFor();
 let requests=0;const count=r=>{if(/\/api\//.test(r.url()))requests++};page.on('request',count);
 await input.fill('no-such-destination-TEST');await dialog.getByText('No matching destination',{exact:false}).waitFor();
 await input.fill('graph audience');await dialog.getByRole('option').first().waitFor();
 assert.ok((await dialog.getByRole('option').first().textContent()).includes('Source map · this story'));
 if(needsReview)await dialog.getByRole('option').first().getByText('Requires editorial review',{exact:true}).waitFor();
 assert.equal(requests,0,'Searching loaded items must not request new data');page.off('request',count);
 await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('#reader-tab-map')?.getAttribute('aria-selected')==='true');
 await page.getByRole('button',{name:'Search workspace',exact:true}).click();await dialog.waitFor();
 await page.keyboard.press('ArrowDown');assert.equal(await input.getAttribute('aria-activedescendant'),'workspace-result-1');
 await page.keyboard.press('ArrowUp');assert.equal(await input.getAttribute('aria-activedescendant'),'workspace-result-0');
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await dialog.evaluate(e=>getComputedStyle(e).animationName),'none');
 for(const width of [1440,768,390]){
  await page.setViewportSize({width,height:1000});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);
  const box=await dialog.boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1);
  if(process.env.QUORUM_SCREENSHOTS){fs.mkdirSync(process.env.QUORUM_SCREENSHOTS,{recursive:true});await dialog.screenshot({path:path.join(process.env.QUORUM_SCREENSHOTS,`navigator-${width}.png`)});}
 }
 await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
 assert.equal(await page.getByRole('button',{name:'Search workspace',exact:true}).evaluate(e=>e===document.activeElement),true);
 await page.setViewportSize({width:1440,height:1000});await page.emulateMedia({reducedMotion:'no-preference'});
 await page.goto(original);await page.waitForFunction(()=>document.querySelector('#reader-tab-all')?.getAttribute('aria-selected')==='true');
 console.log('PASS: app search Ctrl-K/empty/filter/zero query requests; exact story-map jump; arrows/Escape/focus; three widths and reduced motion');
};
