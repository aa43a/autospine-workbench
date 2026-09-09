import test from 'node:test';
import assert from 'node:assert/strict';
import {sampleMeshTrack, advanceMeshClock, mountMeshTimeline} from '../modules/component-mesh-timeline.js';

test('vertex timeline interpolates, clamps and preserves input',()=>{
  const frames=[[[0,0],[2,4]],[[4,8],[6,12]]], before=structuredClone(frames);
  assert.deepEqual(sampleMeshTrack(frames,.25),[[1,2],[3,6]]);
  assert.deepEqual(sampleMeshTrack(frames,-1),frames[0]);
  assert.deepEqual(sampleMeshTrack(frames,99),frames[1]);
  assert.deepEqual(frames,before);
});

test('playback reflects at endpoints without jumping to a different joint',()=>{
  assert.deepEqual(advanceMeshClock(7.9,1,.2),{position:7.9,direction:-1});
  const result=advanceMeshClock(.1,-1,.2);
  assert.ok(Math.abs(result.position-.1)<1e-12);assert.equal(result.direction,1);
});

test('play, scrub and reset control the frame loop',()=>{
  const control=()=>({value:'',textContent:'',events:{},addEventListener(name,fn){this.events[name]=fn;}});
  const controls=Object.fromEntries(['data-time','data-play','data-reset','data-speed','data-time-label'].map(k=>[k,control()]));
  controls['data-speed'].value='1';
  const toolbar={querySelector:s=>controls[s.slice(1,-1)]};
  const doc={createElement:()=>toolbar,querySelector:()=>({before(){}}),querySelectorAll:()=>[],addEventListener(){}};
  let frame=null,canceled=0;
  const clock={requestAnimationFrame(fn){frame=fn;return 1;},cancelAnimationFrame(){canceled++;}};
  mountMeshTimeline(doc,[],clock);
  assert.equal(controls['data-time'].value,'4');
  controls['data-play'].events.click();assert.equal(controls['data-play'].textContent,'暂停');
  frame(1000);frame(1100);assert.equal(controls['data-time'].value,'4.1');
  controls['data-time'].value='2.5';controls['data-time'].events.input();
  assert.equal(controls['data-play'].textContent,'播放');assert.equal(canceled,1);
  controls['data-reset'].events.click();assert.equal(controls['data-time'].value,'4');
});
