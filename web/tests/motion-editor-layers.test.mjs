import test from 'node:test';
import assert from 'node:assert/strict';
import {createLayerEditor} from '../modules/motion-editor-layers.js';
class Element{
  constructor(){this.listeners={};this.value='';this.checked=false;this.children=[];this.classList={toggle(){},add(){},remove(){}};}
  addEventListener(name,fn){this.listeners[name]=fn;}
  replaceChildren(...items){this.children=items;}
  reportValidity(){return true;}
  setPointerCapture(){} hasPointerCapture(){return false;}
  emit(name,extra={}){this.listeners[name]?.({preventDefault(){},...extra});}
}
function setup(){
  const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  globalThis.document={getElementById:get,createElement:()=>new Element()};
  const writes=[],history=[];let editor;
  const live={layers:()=>[{slot:'back',label:'背部',supported:true},{slot:'front',label:'前部',supported:true}],
    layerEdits:value=>writes.push(structuredClone(value)),selectLayer(){},pickLayer:()=> 'back',canvasDelta:(x,y)=>({x:x/2,y:-y/2})};
  let paused=0,changed=0;editor=createLayerEditor({live,beforeChange:()=>history.push(editor.snapshot()),pause:()=>paused++,changed:()=>changed++});
  editor.loaded();return {editor,get,writes,history,counts:()=>({paused,changed})};
}
test('layer edits preserve whole order, transform state, restore and reject unknown slots atomically',()=>{
  const {editor,get,writes,history}=setup();assert.equal(editor.snapshot(),null);
  get('motion-layer-list').value='back';get('motion-layer-list').emit('change');
  get('layer-front').emit('click');assert.deepEqual(editor.snapshot().draw_order,['front','back']);assert.deepEqual(history,[null]);
  get('layer-dx').value='24';get('layer-rotation').value='45';get('layer-transform-form').emit('submit');
  const saved=editor.snapshot();assert.equal(saved.transforms[0].dx,24);assert.equal(saved.transforms[0].rotation,45);
  get('layer-reset-selected').emit('click');assert.equal(editor.snapshot().transforms.length,0);assert.deepEqual(editor.snapshot().draw_order,['front','back']);
  editor.restore(saved);const count=writes.length;
  assert.throws(()=>editor.restore({...saved,draw_order:['missing','front']}));assert.equal(writes.length,count);assert.deepEqual(editor.snapshot(),saved);
  get('layer-reset-all').emit('click');assert.equal(editor.snapshot(),null);editor.restore(saved);assert.deepEqual(editor.snapshot(),saved);
});
test('drag has one undo snapshot, uses world delta, pauses and applies entire-clip correction',()=>{
  const {editor,get,history,counts}=setup();get('layer-edit-mode').checked=true;
  const canvas=get('character-canvas');canvas.emit('pointerdown',{button:0,pointerId:1,clientX:10,clientY:10});
  canvas.emit('pointermove',{pointerId:1,clientX:30,clientY:20});canvas.emit('pointermove',{pointerId:1,clientX:50,clientY:30});
  canvas.emit('pointerup',{pointerId:1});assert.equal(history.length,1);assert.equal(counts().paused,1);
  assert.deepEqual(editor.snapshot().transforms,[{slot:'back',dx:20,dy:-10,rotation:0,scaleX:1,scaleY:1}]);
  canvas.emit('pointermove',{pointerId:1,clientX:100,clientY:100});assert.equal(editor.snapshot().transforms[0].dx,20);
  editor.reset();assert.equal(editor.snapshot(),null);
});
test('editor batch failure preserves history and preview and selects offending layer',()=>{
  const {editor,get,writes,history}=setup(),count=writes.length;
  assert.equal(editor.execute([{op:'transform',slot:'front',values:{dx:10}},
    {op:'transform',slot:'back',values:{scaleY:0}}]),false);
  assert.equal(writes.length,count);assert.equal(history.length,0);assert.equal(editor.snapshot(),null);
  assert.match(get('layer-status').textContent,/back\/scaleY/);
  assert.match(get('layer-selection').textContent,/背部/);
  assert.equal(editor.execute([{op:'transform',slot:'front',values:{dx:10}},
    {op:'order',slots:['front','back']}]),true);
  assert.equal(history.length,1);assert.match(get('layer-status').textContent,/完整检查/);
});
test('comparison changes only the preview and restoring edits exits comparison',()=>{
  const {editor,get,writes,history}=setup();
  editor.execute([{op:'transform',slot:'back',values:{dx:5}}]);const saved=editor.snapshot();
  get('layer-compare-original').checked=true;get('layer-compare-original').emit('change');
  assert.deepEqual(writes.at(-1).transforms,[]);assert.deepEqual(editor.snapshot(),saved);assert.equal(history.length,1);
  get('layer-compare-original').checked=false;get('layer-compare-original').emit('change');
  assert.deepEqual(writes.at(-1),saved);
  get('layer-compare-original').checked=true;editor.restore(saved);
  assert.equal(get('layer-compare-original').checked,false);assert.deepEqual(writes.at(-1),saved);
});
