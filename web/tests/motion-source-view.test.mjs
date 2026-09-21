import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
const code=await readFile(new URL('../modules/motion-source-player.js',import.meta.url),'utf8');
const {createSourcePlayer}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('view changes preserve time and input, and restore identical drawing',()=>{
  const strokes=[],ctx={clearRect(){strokes.length=0;},beginPath(){},moveTo(...v){strokes.push(v);},lineTo(...v){strokes.push(v);},stroke(){},arc(){},fill(){}};
  const slider={value:0},button={},label={},times=[];
  const player=createSourcePlayer({width:400,height:500,getContext:()=>ctx},slider,button,label,t=>times.push(t));
  const data={view:'front',parents:[null,0],frames:[{time:0,frame:0,joints:[[0,0,0],[1,1,2]]},{time:2,frame:1,joints:[[0,0,0],[2,1,-1]]}]};
  const original=JSON.stringify(data);player.load(data);player.seek(1);
  const front=JSON.stringify(strokes);player.setView('side');
  assert.notEqual(JSON.stringify(strokes),front);assert.equal(slider.value,1);
  player.setView(null);assert.equal(JSON.stringify(strokes),front);
  assert.equal(JSON.stringify(data),original);assert.deepEqual(times,[0,1,1,1]);
  assert.throws(()=>player.setView('invalid'),/source_view_invalid/);
});
