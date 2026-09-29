import {normalizeLayerEdits} from './motion-layer-transform.js';
import {applyRigEditOperations,layerEditImpactText} from './rig-edit-operations.js';
const fields=['dx','dy','rotation','scaleX','scaleY'];
const defaults=slot=>({slot,dx:0,dy:0,rotation:0,scaleX:1,scaleY:1});
export function createLayerEditor({live,beforeChange=()=>{},changed=()=>{},pause=()=>{}}){
  const $=id=>document.getElementById(id),list=$('motion-layer-list'),canvas=$('character-canvas');
  const mode=$('layer-edit-mode'),status=$('layer-status'),form=$('layer-transform-form');
  let layers=[],selected=null,edits=normalizeLayerEdits(null),drag=null;
  const ids=()=>layers.map(row=>row.slot);
  const order=()=>edits.draw_order.length?[...edits.draw_order]:ids();
  const row=()=>edits.transforms.find(item=>item.slot===selected)??defaults(selected);
  function message(text){status.textContent=text;}
  function render(){
    const names=new Map(layers.map(item=>[item.slot,item]));
    list.replaceChildren(...order().reverse().map(slot=>{const option=document.createElement('option');
      option.value=slot;option.textContent=(names.get(slot)?.label??slot)+(edits.transforms.some(item=>item.slot===slot)?' · 已校正':'');
      option.selected=slot===selected;return option;}));
    list.disabled=!layers.length;
    const current=names.get(selected),editable=Boolean(current?.supported),value=row();
    $('layer-selection').textContent=current?`${current.label??current.slot}${editable?' · 可移动、旋转与缩放':' · 此附件暂不支持位置校正，可调整顺序'}`:'选择角色后，在列表或画布中点选图层。';
    fields.forEach(key=>{const input=$('layer-'+key);input.value=value[key];input.disabled=!editable;});
    $('layer-apply').disabled=!editable;$('layer-reset-selected').disabled=!edits.transforms.some(item=>item.slot===selected);
    $('layer-reset-all').disabled=!edits.transforms.length&&!edits.draw_order.length;
    const index=order().indexOf(selected);
    for(const name of ['front','forward'])$('layer-'+name).disabled=index<0||index===layers.length-1;
    for(const name of ['back','backward'])$('layer-'+name).disabled=index<=0;
    canvas.classList.toggle('layer-edit-active',mode.checked&&Boolean(layers.length));
    live.selectLayer(mode.checked?selected:null);
  }
  function execute(operations,{record=true}={}){
    const result=applyRigEditOperations(edits,operations,{layers:layers.length?layers:null});
    if(!result.ok){const diagnostic=result.diagnostics[0];
      if(layers.some(item=>item.slot===diagnostic.slot)){selected=diagnostic.slot;mode.checked=true;render();}
      message(`${diagnostic.message} · ${diagnostic.path}。${diagnostic.hint}`);return false;}
    const valid=result.value;
    if(JSON.stringify(valid)===JSON.stringify(edits))return false;
    if(record)beforeChange();
    live.layerEdits(valid);edits=valid;render();changed();
    message(layerEditImpactText(edits));return true;
  }
  const apply=(next,options)=>execute([{op:'replace',value:next}],options);
  function transform(value,record=true){
    const {slot,...values}=value;return execute([{op:'transform',slot,values}],{record});
  }
  list.addEventListener('change',()=>{selected=list.value;mode.checked=true;render();});
  mode.addEventListener('change',render);
  function applyForm(event){
    event?.preventDefault();if(!form.reportValidity()||!selected)return;
    try{const value={slot:selected};fields.forEach(key=>value[key]=Number($('layer-'+key).value));transform(value);}
    catch(error){message(error.message);}
  }
  form.addEventListener('submit',applyForm);
  fields.forEach(key=>$('layer-'+key).addEventListener('change',applyForm));
  function reorder(direction){
    const next=order(),index=next.indexOf(selected);if(index<0)return;
    const target=direction==='front'?next.length-1:direction==='back'?0:index+(direction==='forward'?1:-1);
    if(target<0||target>=next.length||target===index)return;
    next.splice(index,1);next.splice(target,0,selected);
    execute([{op:'order',slots:JSON.stringify(next)===JSON.stringify(ids())?[]:next}]);
  }
  for(const name of ['front','forward','backward','back'])$('layer-'+name).addEventListener('click',()=>{try{reorder(name);}catch(error){message(error.message);}});
  $('layer-reset-selected').addEventListener('click',()=>{if(selected)transform(defaults(selected));});
  $('layer-reset-all').addEventListener('click',()=>apply(normalizeLayerEdits(null)));
  canvas.addEventListener('pointerdown',event=>{
    if(!mode.checked||event.button!==0)return;
    const picked=live.pickLayer(event.clientX,event.clientY);if(!picked)return;
    selected=picked;render();
    if(!layers.find(item=>item.slot===selected)?.supported)return;
    pause();drag={id:event.pointerId,x:event.clientX,y:event.clientY,start:{...row()},recorded:false};
    canvas.setPointerCapture(event.pointerId);canvas.classList.add('layer-dragging');event.preventDefault();
  });
  canvas.addEventListener('pointermove',event=>{
    if(!drag||event.pointerId!==drag.id)return;
    const dx=event.clientX-drag.x,dy=event.clientY-drag.y;if(!drag.recorded&&Math.hypot(dx,dy)<2)return;
    try{const delta=live.canvasDelta(dx,dy);if(!delta)return;
      const value={...drag.start,dx:drag.start.dx+delta.x,dy:drag.start.dy+delta.y};
      if(transform(value,!drag.recorded))drag.recorded=true;
    }catch(error){message(error.message);}
  });
  function finish(event){if(drag&&event.pointerId===drag.id){drag=null;canvas.classList.remove('layer-dragging');if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);}}
  canvas.addEventListener('pointerup',finish);canvas.addEventListener('pointercancel',finish);canvas.addEventListener('lostpointercapture',finish);
  render();
  return {
    execute,
    reset(){drag=null;layers=[];selected=null;edits=normalizeLayerEdits(null);live.layerEdits(edits);render();message('尚无图层校正。');},
    loaded(labels={}){layers=live.layers().map(item=>({...item,label:labels[item.slot]??item.label??item.slot}));if(!layers.some(item=>item.slot===selected))selected=layers.at(-1)?.slot??null;
      const valid=normalizeLayerEdits(edits,ids());live.layerEdits(valid);render();},
    snapshot(){return edits.transforms.length||edits.draw_order.length?structuredClone(edits):null;},
    restore(value){const valid=normalizeLayerEdits(value,layers.length?ids():null);live.layerEdits(valid);edits=valid;render();
      message(layerEditImpactText(edits));},
  };
}
