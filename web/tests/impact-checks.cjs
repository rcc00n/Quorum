const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
module.exports=async({page,event})=>{
 const panel=page.locator('.impact-assessment').first();await panel.waitFor();
 assert.equal(await panel.getAttribute('open'),null);
 await panel.locator(':scope > summary').click();
 const rubric=event.reasoning?.rubric;
 if(rubric){
  assert.equal(await panel.locator('.impact-total-value').textContent(),String(rubric.total));
  for(const [key,max] of [['legal_force',2],['reach',3],['irreversibility',2],['confirmation',2]]){
   const row=panel.locator(`.impact-dimension[data-dimension="${key}"]`);
   assert.equal(await row.locator('dd strong').textContent(),String(rubric[key]));
   assert.equal(await row.locator('.impact-steps span').count(),max);
   assert.equal(await row.locator('.impact-steps .filled').count(),rubric[key]);
  }
 }
 const notes=panel.locator('.impact-notes');assert.equal(await notes.getAttribute('open'),null);
 await notes.locator(':scope > summary').click();
 if(event.importance)assert.equal(await panel.locator('.impact-original p').textContent(),event.importance.explanation);
 if(rubric)for(const [key,text] of Object.entries(rubric.rationale||{}))assert.equal(await panel.locator(`.impact-rationales dd[data-dimension="${key}"]`).textContent(),text);
 await notes.locator(':scope > summary').click();
 for(const width of [1440,768,390]){await page.setViewportSize({width,height:1000});assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false);
  if(process.env.QUORUM_SCREENSHOTS){fs.mkdirSync(process.env.QUORUM_SCREENSHOTS,{recursive:true});await panel.screenshot({path:path.join(process.env.QUORUM_SCREENSHOTS,`impact-${width}.png`)});}}
 await panel.locator(':scope > summary').click();await page.setViewportSize({width:1440,height:1000});
 console.log('PASS: exact supplied impact points/ranges; original rationales/notes preserved on demand; three widths');
};
