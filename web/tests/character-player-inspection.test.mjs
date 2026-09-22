import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
test('inspection scopes messages to exact candidate and uses applied slot poses without editing source',()=>{
 let receive,draws=0,cleared=0;const parent={postMessage(){}},window={addEventListener:(_,fn)=>receive=fn};
 vm.runInNewContext(readFileSync(new URL('../character-player-inspection.js',import.meta.url),'utf8'),{window,parent,location:{origin:'http://local'}});
 const renderer={camera:{setViewport(){},position:{},update(){}},skeletonDebugRenderer:{},drawSkeletonDebug(){}};
 const source={artifact_sha256:'a',info:{width:400,height:600,left:0,bottom:0},skeleton:{slots:[{name:'eye'},{name:'body'}]}};
 const inspect=window.createCharacterInspection(source,renderer,()=>draws++);
 const message={type:'audit-focus',artifact:'a',regions:['eye'],bone:'head',isolated:true};
 receive({source:parent,origin:'http://evil',data:message});
 receive({source:parent,origin:'http://local',data:{...message,artifact:'old'}});assert.equal(draws,0);
 receive({source:parent,origin:'http://local',data:message});assert.equal(draws,1);
 const skeleton={slots:['eye','body'].map(name=>({data:{name},appliedPose:{setAttachment(value){assert.equal(value,null);cleared++;}}})),getBoundsRect:()=>({x:10,y:20,width:30,height:40})};
 inspect.prepare(skeleton);assert.equal(cleared,1);assert.equal(source.skeleton.slots.length,2);
 receive({source:parent,origin:'http://local',data:{...message,isolated:false}});inspect.prepare(skeleton);assert.equal(cleared,1);
 assert.equal(inspect.setRegions(['missing'],'hide'),false);
 assert.equal(inspect.setRegions(['eye'],'hide'),true);inspect.prepare(skeleton);assert.equal(cleared,2);
 assert.equal(window.characterInspectionState.hidden,true);
 assert.equal(inspect.setRegions(['eye'],'full'),true);inspect.prepare(skeleton);assert.equal(cleared,2);
 assert.equal(window.characterInspectionState.regions.length,0);
 // Local isolation must preserve the full-character camera for same-frame comparison.
 skeleton.getBoundsRect=()=>{throw Error('local isolation need not measure bounds');};
 assert.equal(inspect.setRegions(['eye'],'isolate'),true);
 inspect.prepare(skeleton);assert.equal(cleared,3);
});

test('triangle overlay follows current runtime vertices and rejects invalid indices',()=>{
 const window={addEventListener(){}},parent={postMessage(){}};
 vm.runInNewContext(readFileSync(new URL('../character-player-inspection.js',import.meta.url),'utf8'),
   {window,parent,location:{origin:'http://local'},Float32Array});
 const lines=[];const renderer={line:(...v)=>lines.push(v)};
 const context={skeleton:{skins:[{attachments:{leg:{leg:{triangles:[0,1,2]}}}}]}};
 const inspect=window.createCharacterInspection(context,renderer,()=>{});
 assert.equal(inspect.setTriangle('leg',-1),false);
 assert.equal(inspect.setTriangle('leg',1),false);
 assert.equal(inspect.setTriangle('missing',0),false);
 assert.equal(inspect.setTriangle('leg',0),true);
 const attachment={triangles:[0,1,2],worldVerticesLength:6,
   computeWorldVertices(_s,_slot,_start,_count,out){out.set([10,20,30,20,10,40]);}};
 inspect.draw({findSlot:()=>({appliedPose:{attachment}})});
 assert.equal(lines.length,3);assert.deepEqual(lines[0].slice(0,4),[10,20,30,20]);
 assert.equal(window.characterTriangleInspection.index,0);
 inspect.setTriangle(null);inspect.draw({});assert.equal(window.characterTriangleInspection,null);
});
