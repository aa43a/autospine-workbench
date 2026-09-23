import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const [base,job]=process.argv.slice(2);
const browser=await chromium.launch({channel:'chrome',headless:true,
 args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const url=`${base}/api/motions/${job}/view/player.html`;
 for(const invalid of [false,true]){
  await page.goto(url+'?time=1.5&mode=isolate&region='+ (invalid?'missing-region':'layer-003')+'&region=layer-006');
  await page.waitForFunction(()=>window.characterPlayerReady||window.characterPlayerError,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>window.characterPlayerError),undefined);
  const state=await page.evaluate(()=>({time:window.characterPlayerState.time,...window.characterInspectionState}));
  assert.equal(state.time,1.5);assert.equal(state.isolated,!invalid);
  assert.deepEqual(state.regions,invalid?[]:['layer-003','layer-006']);
  if(!invalid){
    assert.equal(await page.locator('#inspect-a').inputValue(),'layer-003');
    assert.equal(await page.locator('#inspect-b').inputValue(),'layer-006');
    await page.locator('#inspect-clear').click();
    assert.deepEqual(await page.evaluate(()=>window.characterInspectionState.regions),[]);
    assert.equal(await page.evaluate(()=>window.characterPlayerState.time),1.5);
  }
 }
 assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,job,checks:'exact_time_valid_pair_restore_and_invalid_pair'}));
}finally{await browser.close();}
