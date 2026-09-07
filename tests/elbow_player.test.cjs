const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('player advances 30 fps, skips duplicate endpoint and pauses',()=>{
  const elements={data:{textContent:'[]'},frame:{value:15},wire:{},position:{},cards:{},play:{}};
  let callback;
  const context={document:{getElementById:id=>elements[id]},requestAnimationFrame:fn=>{callback=fn;}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/autospine_workbench/benchmark/elbow_bake_player.js'),'utf8'),context);
  elements.play.onclick();callback(100);callback(600);
  assert.equal(Number(elements.frame.value),30);
  callback(2100);assert.equal(Number(elements.frame.value),15);
  elements.play.onclick();callback(5000);assert.equal(Number(elements.frame.value),15);
  elements.play.onclick();callback(6000);callback(6500);assert.equal(Number(elements.frame.value),30);
});
