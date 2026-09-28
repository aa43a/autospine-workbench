// Setup-only authoring view. Dragging never changes a saved body animation.
import {createEditorRenderer} from './motion-editor-renderer.js';

export function toLocal(matrix,point){
  const [a,b,c,d,x,y]=matrix,det=a*d-b*c;
  if(!Number.isFinite(det)||Math.abs(det)<1e-8)throw Error('锚点父骨骼坐标不可逆');
  const dx=point.x-x,dy=point.y-y;
  return [(d*dx-b*dy)/det,(-c*dx+a*dy)/det];
}
export function toWorld(matrix,point){
  const [a,b,c,d,x,y]=matrix;
  return {x:a*point[0]+b*point[1]+x,y:c*point[0]+d*point[1]+y};
}
export function createJointAnchorCanvas({container,meta,change}){
  const frame=document.createElement('div'),canvas=document.createElement('canvas'),marks=document.createElement('canvas'),note=document.createElement('p');
  frame.className='joint-anchor-viewport';Object.assign(frame.style,{position:'relative',width:'100%',maxWidth:'480px',aspectRatio:'1'});
  for(const node of [canvas,marks])Object.assign(node.style,{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',touchAction:'none'});
  marks.style.zIndex='3';marks.setAttribute('aria-label','拖动面部锚点');
  note.textContent='正在加载原始静止姿态；拖动圆点调整锚点，重建后查看动画。';
  frame.append(canvas,marks);container.append(frame,note);
  let renderer=null,disposed=false,config=null,selected=null,drag=null,bounds=null,centers=[];
  const parts=meta.inventory.face.parts.filter(part=>part.available);
  function draw(){
    if(!renderer||!bounds)return;
    renderer.selectLayer(selected);renderer.draw(0);
    marks.width=canvas.width;marks.height=canvas.height;
    const ctx=marks.getContext('2d');ctx.clearRect(0,0,marks.width,marks.height);centers=[];
    for(const part of parts){
      const matrix=renderer.boneMatrix(part.parent);if(!matrix)continue;
      const point=toWorld(matrix,config?.face?.anchors?.[part.slot]??part.anchor);
      const x=point.x-bounds.left,y=bounds.height-(point.y-bounds.bottom);
      centers.push({part,x,y});ctx.beginPath();ctx.arc(x,y,part.slot===selected?5:3,0,Math.PI*2);
      ctx.fillStyle=part.slot===selected?'#ffd159':'#55d4ff';ctx.fill();ctx.strokeStyle='#142838';ctx.lineWidth=1;ctx.stroke();
    }
  }
  function point(event){return renderer?.worldPoint(event.clientX,event.clientY);}
  marks.onpointerdown=event=>{
    if(event.button!==0||!renderer)return;const world=point(event);if(!world)return;
    const x=world.x-bounds.left,y=bounds.height-(world.y-bounds.bottom);
    const nearest=centers.map(row=>({...row,distance:Math.hypot(x-row.x,y-row.y)})).sort((a,b)=>a.distance-b.distance)[0];
    if(!nearest||nearest.distance>Math.max(bounds.width/20,8))return;
    event.preventDefault();selected=nearest.part.slot;drag={id:event.pointerId,part:nearest.part,point:null,original:structuredClone(config)};marks.setPointerCapture(event.pointerId);draw();
  };
  marks.onpointermove=event=>{
    if(!drag||event.pointerId!==drag.id)return;const world=point(event);if(!world)return;
    drag.point=toLocal(renderer.boneMatrix(drag.part.parent),world);
    if(drag.point.some(value=>!Number.isFinite(value)||Math.abs(value)>8192))return;
    const draft=structuredClone(config??{});draft.face??={};draft.face.anchors??={};draft.face.anchors[drag.part.slot]=drag.point;
    config=draft;note.textContent=`${drag.part.name} · (${drag.point.map(v=>v.toFixed(2)).join(', ')}) · 松开应用`;draw();
  };
  function finish(event,canceled){
    if(!drag||event.pointerId!==drag.id)return;const previous=drag;drag=null;
    if(marks.hasPointerCapture(event.pointerId))marks.releasePointerCapture(event.pointerId);
    if(!canceled&&previous.point){change(previous.part.slot,previous.point);note.textContent='锚点已调整。构建联合动画后，在上方时间轴检查实际效果。';}
    else {config=previous.original;draw();note.textContent='已取消本次拖动。';}
  }
  marks.onpointerup=event=>finish(event,false);marks.onpointercancel=event=>finish(event,true);
  const base=meta.preview_base??`/api/motions/${meta.parent_job_id}/view/player-assets/`;
  createEditorRenderer(canvas,base,()=>!disposed).then(value=>{
    if(!value)return;if(disposed){value.dispose();return;}renderer=value;
    if(renderer.artifact!==meta.artifact_sha256)throw Error('锚点预览与身体候选版本不一致');
    renderer.draw(0);const boxes=parts.map(part=>renderer.layerGeometry(part.slot)?.bounds).filter(Boolean);
    if(!boxes.length)throw Error('没有可显示的面部区域');
    const left=Math.min(...boxes.map(b=>b.left)),right=Math.max(...boxes.map(b=>b.right)),bottom=Math.min(...boxes.map(b=>b.bottom)),top=Math.max(...boxes.map(b=>b.top));
    const size=Math.ceil(Math.max(right-left,top-bottom)*1.7+20);
    bounds={left:(left+right-size)/2,bottom:(bottom+top-size)/2,width:size,height:size};renderer.viewport(bounds);draw();
    note.textContent='原始静止姿态。点选并拖动圆点调整面部锚点；参数修改后重新构建查看动画。';
  }).catch(error=>{if(!disposed){renderer?.dispose();renderer=null;note.textContent=`锚点画布未加载：${error.message}。仍可使用坐标输入。`;}});
  return {update(value){config=structuredClone(value);draw();},select(slot){selected=slot;draw();},
    dispose(){disposed=true;renderer?.dispose();frame.remove();note.remove();}};
}
