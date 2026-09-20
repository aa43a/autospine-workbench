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
});
