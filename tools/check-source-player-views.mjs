import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const code = await fs.readFile(new URL('../web/modules/motion-source-player.js', import.meta.url), 'utf8');
const {createSourcePlayer} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const arcs = [];
const ctx = {clearRect(){arcs.length=0;},beginPath(){},moveTo(){},lineTo(){},stroke(){},fill(){},
  arc(x,y){arcs.push([x,y]);}};
const slider = {}, button = {}, label = {};
const player = createSourcePlayer({width:400,height:400,getContext:()=>ctx}, slider, button, label);
const data = {view:'side',parents:[null,0,0],frames:[
  {time:0,frame:0,joints:[[0,0,0],[1,1,0],[0,2,1]]},
  {time:1,frame:1,joints:[[0,0,0],[1,1,0],[0,2,1]]}]};
player.load(data);player.seek(.7);
for (const yaw of [-90,-45,0,45,90]) {
  player.setView(yaw);
  const angle=yaw*Math.PI/180;
  // Vertical extent fixes the scale at 160 px: camera rotation must not distort it.
  assert.ok(Math.abs(arcs[1][0]-arcs[0][0]-160*Math.cos(angle))<1e-9);
  assert.ok(Math.abs(arcs[2][0]-arcs[0][0]+160*Math.sin(angle))<1e-9);
  assert.equal(slider.value,.7);
}
player.setView('front');const front=structuredClone(arcs);
player.setView(0);assert.deepEqual(arcs,front); // numeric zero must override source side view
player.setView('side');const side=structuredClone(arcs);
player.setView(90);assert.deepEqual(arcs,side);
for (const value of [NaN,Infinity,-91,91,'45',{}])assert.throws(()=>player.setView(value),/source_view_invalid/);
assert.deepEqual(data.frames[0].joints,[[0,0,0],[1,1,0],[0,2,1]]);
console.log('Source view projection, timeline preservation and validation passed');
