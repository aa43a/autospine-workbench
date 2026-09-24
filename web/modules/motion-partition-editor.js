import {brushTriangles} from './mesh-brush.js';
const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
export function partitionEditor(parent,job,row,{textureOnly=false,orderOnly=false}={}) {
  const box=el('fieldset'),open=el('button','在原纹理上划分区域'),canvas=el('canvas');
  canvas.setAttribute('aria-label','区域三角形选择画布');canvas.style.cssText='max-width:100%;touch-action:none;background:#29333e';
  const bone=el('select');bone.setAttribute('aria-label','区域目标骨骼');
  if(textureOnly||orderOnly){bone.hidden=true;bone.style.display='none';}
  const reference=el('select'),side=el('select');reference.setAttribute('aria-label','遮挡参考附件');side.setAttribute('aria-label','区域绘制顺序');
  for(const [value,label] of [['before','位于参考附件后方'],['after','位于参考附件前方']]){const o=el('option',label);o.value=value;side.append(o);}
  reference.hidden=side.hidden=!orderOnly;
  const radius=el('input');radius.type='range';radius.min=2;radius.max=80;radius.value=12;radius.setAttribute('aria-label','区域笔刷半径');
  const erase=el('input');erase.type='checkbox';erase.setAttribute('aria-label','取消区域选择');
  const clear=el('button','清空区域'),status=el('p','尚未载入区域。');
  box.append(el('legend',orderOnly?'区域前后顺序草稿':'区域划分草稿'),open,bone,reference,side,radius,el('span','取消选择'),erase,clear,status,canvas);parent.append(box);
  let mesh=null,image=null,selected=new Set(),saved=null,generation=0,previous=null,pointer=null;
  const draw=()=>{
    if(!mesh||!image)return;
    const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);
    for(let i=0;i<mesh.triangles.length;i+=3){ctx.beginPath();
      for(let k=0;k<3;k++){const v=mesh.triangles[i+k],x=mesh.uvs[v*2]*canvas.width,y=mesh.uvs[v*2+1]*canvas.height;k?ctx.lineTo(x,y):ctx.moveTo(x,y);}
      ctx.closePath();if(selected.has(i/3)){ctx.fillStyle='#ffbb0070';ctx.fill();}
      ctx.strokeStyle=selected.has(i/3)?'#ffd050':'#7faabb60';ctx.stroke();
    }
    status.textContent=textureOnly?`已选择 ${selected.size} 个三角形。仅指定换图区域，保留原权重和变形；尚未应用。`:`已选择 ${selected.size} 个三角形。保存后可构建独立分区候选；所选区域刚性随目标骨骼，边界可能分离，需重新检查。`;
    if(orderOnly)status.textContent=`已选择 ${selected.size} 个三角形。整段动作使用此顺序，保留原权重与变形；不自动追踪前后穿越，需检查遮挡与材质边界。`;
  };
  const restore=()=>{selected=new Set(saved?.triangles||[]);if(saved){bone.value=saved.bone;reference.value=saved.reference_slot;side.value=saved.side||'before';}draw();};
  open.onclick=async()=>{const ticket=++generation;open.disabled=true;
    try{
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/partition-mesh.json`,{cache:'no-store'});
      const report=await response.json();if(!response.ok)throw Error(report.reason_code||'区域载入失败');
      if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选已变化');
      const found=report.rows.find(r=>r.slot===row.slot);if(!found)throw Error('未找到可编辑网格');
      const img=new Image();img.src=row.texture;await img.decode();if(ticket!==generation)return;
      mesh=found;image=img;bone.replaceChildren();
      for(const name of report.bones){const o=el('option',name);o.value=name;bone.append(o);}
      reference.replaceChildren();for(const name of report.slots||[]){if(name===row.slot)continue;const o=el('option',name);o.value=name;reference.append(o);}
      canvas.width=Math.min(800,image.naturalWidth);canvas.height=Math.round(canvas.width*image.naturalHeight/image.naturalWidth);
      if(saved&&saved.mesh_sha256!==mesh.mesh_sha256)throw Error('已保存分区的网格已变化');restore();
    }catch(e){if(ticket===generation){mesh=null;status.textContent=e.message;}}
    finally{if(ticket===generation)open.disabled=false;}
  };
  const paint=e=>{if(!mesh||!image)return;
    const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left)*canvas.width/r.width,y=(e.clientY-r.top)*canvas.height/r.height;
    const point=[x,y];
    for(const index of brushTriangles(mesh,canvas.width,canvas.height,previous||point,point,Number(radius.value)))
      erase.checked?selected.delete(index):selected.add(index);
    previous=point;draw();
  };
  canvas.onpointerdown=e=>{if(e.button!==0)return;pointer=e.pointerId;previous=null;canvas.setPointerCapture(e.pointerId);paint(e);};
  canvas.onpointermove=e=>{if(e.pointerId===pointer&&e.buttons===1)paint(e);};
  const stop=()=>{pointer=null;previous=null;};
  canvas.onpointerup=canvas.onpointercancel=canvas.onlostpointercapture=stop;
  clear.onclick=()=>{stop();selected.clear();draw();};
  return {show:value=>{stop();box.hidden=!value;},restore:value=>{stop();generation++;open.disabled=false;saved=value||null;restore();},
    value:()=>{if(!mesh||!selected.size)throw Error('请先载入网格并选择区域');
      if(orderOnly&&!reference.value)throw Error('请选择参考附件');
      return {mesh_sha256:mesh.mesh_sha256,triangles:[...selected].sort((a,b)=>a-b),...(orderOnly?{reference_slot:reference.value,side:side.value}:textureOnly?{}:{bone:bone.value})};}};
}
