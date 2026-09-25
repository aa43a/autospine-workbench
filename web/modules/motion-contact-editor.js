import {brushTriangles} from './mesh-brush.js';
const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
const names={fixed:'固定连接区',sliding:'沿边滑动约束区',occlusion:'覆盖区（可相对滑动）',transition:'可变形过渡区',free:'保留原运动区'};
const colors={fixed:'#fa777799',sliding:'#67caff99',occlusion:'#c59aff99',transition:'#e6b85399',free:'#7cdb9999'};
export function contactEditor(parent,job,row) {
  const box=node('fieldset'),open=node('button','载入衣料连接画布'),reference=node('select'),kind=node('select');
  reference.setAttribute('aria-label','衣料连接参考附件');kind.setAttribute('aria-label','衣料区域类型');
  for(const [value,label] of Object.entries({...names,unknown:'清除标注，保留未知'})){const o=node('option',label);o.value=value;kind.append(o);}
  const radius=node('input');radius.type='range';radius.min=2;radius.max=80;radius.value=12;radius.setAttribute('aria-label','衣料区域笔刷半径');
  const canvas=node('canvas');canvas.setAttribute('aria-label','衣料连接区域画布');canvas.style.cssText='max-width:100%;touch-action:none;background:#29333e';
  const status=node('p','未标注区域保持未知。');status.setAttribute('role','status');
  box.append(node('legend','衣料连接与活动范围'),node('p','在原纹理上刷选区域，再保存处理草稿。红色：固定连接；蓝色：沿边滑动约束；紫色：被参考附件覆盖、可相对滑动，例如披肩下方的袖布，保留原运动，不锁定材料点或限制沿边移动；黄色：可变形过渡区；绿色：保留原运动。旧蓝色标注不会自动改成紫色。未标注区域保持未知；覆盖区与保留区的共享顶点仍保留原运动。此处只记录意图，尚未修复动画或验收遮挡效果。'),open,reference,kind,radius,status,canvas);parent.append(box);
  let mesh=null,image=null,saved=null,labels=new Map(),ticket=0,pointer=null,previous=null;
  const stop=()=>{pointer=null;previous=null;};
  const draw=()=>{
    if(!mesh||!image)return;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);
    for(let i=0;i<mesh.triangles.length;i+=3){ctx.beginPath();for(let k=0;k<3;k++){const v=mesh.triangles[i+k],x=mesh.uvs[2*v]*canvas.width,y=mesh.uvs[2*v+1]*canvas.height;k?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.closePath();if(labels.has(i/3)){ctx.fillStyle=colors[labels.get(i/3)];ctx.fill();}ctx.strokeStyle='#8eb3c760';ctx.stroke();}
    status.textContent=Object.keys(names).map(k=>`${names[k]} ${[...labels.values()].filter(v=>v===k).length}`).join(' · ')+` · 未知 ${mesh.triangles.length/3-labels.size}；尚未应用。`;
  };
  const restore=()=>{labels=new Map();for(const [k,ids] of Object.entries(saved?.regions||{}))for(const i of ids)labels.set(i,k);if(saved)reference.value=saved.reference_slot;draw();};
  open.onclick=async()=>{const generation=++ticket;open.disabled=true;status.textContent='正在加载…';
    try{const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/partition-mesh.json`,{cache:'no-store'});const report=await response.json();if(!response.ok)throw Error(report.reason_code||'加载失败');if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选已变化');
      const found=report.rows.find(r=>r.slot===row.slot);if(!found)throw Error('当前附件无可编辑网格');if(saved&&saved.mesh_sha256!==found.mesh_sha256)throw Error('已保存的网格已过期');
      const img=new Image();img.src=row.texture;await img.decode();if(generation!==ticket)return;
      mesh=found;image=img;reference.replaceChildren();const empty=node('option','选择实际连接或遮挡参考附件');empty.value='';reference.append(empty);
      for(const r of report.rows){if(r.slot===row.slot)continue;const o=node('option',r.slot);o.value=r.slot;reference.append(o);}
      canvas.width=Math.min(800,img.naturalWidth);canvas.height=Math.round(canvas.width*img.naturalHeight/img.naturalWidth);restore();
    }catch(e){if(generation===ticket){mesh=null;status.textContent=e.message;}}finally{if(generation===ticket)open.disabled=false;}
  };
  const paint=e=>{if(!mesh||!image)return;const r=canvas.getBoundingClientRect(),p=[(e.clientX-r.left)*canvas.width/r.width,(e.clientY-r.top)*canvas.height/r.height];
    for(const i of brushTriangles(mesh,canvas.width,canvas.height,previous||p,p,Number(radius.value)))kind.value==='unknown'?labels.delete(i):labels.set(i,kind.value);previous=p;draw();};
  canvas.onpointerdown=e=>{if(e.button!==0)return;pointer=e.pointerId;previous=null;canvas.setPointerCapture(pointer);paint(e);};
  canvas.onpointermove=e=>{if(e.pointerId===pointer&&e.buttons===1)paint(e);};canvas.onpointerup=canvas.onpointercancel=canvas.onlostpointercapture=stop;
  return {show:value=>{stop();box.hidden=!value;},restore:value=>{stop();ticket++;open.disabled=false;saved=value||null;restore();},
    value:()=>{if(!mesh||!labels.size||!reference.value)throw Error('请载入画布、标注区域并选择参考附件');
      return {mesh_sha256:mesh.mesh_sha256,reference_slot:reference.value,regions:Object.fromEntries(Object.keys(names).map(k=>[k,[...labels].filter(([,v])=>v===k).map(([i])=>i).sort((a,b)=>a-b)]))};}};
}
