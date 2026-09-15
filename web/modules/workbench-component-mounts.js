export function createComponentMounts(document, hooks) {
  const node=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
  const element=node('section'),title=node('h3','同层部件分别绑定'),status=node('p'),controls=node('div');
  const region=node('select'),load=node('button','显示区域与骨架'),save=node('button','确认映射并保存'),undo=node('button','撤销分区绑定');
  region.setAttribute('aria-label','选择待分区源区域');
  const canvas=node('canvas'),rows=node('div');canvas.setAttribute('style','max-width:100%;height:auto');
  const timeline=node('a','查看分区绑定整角色时间轴');timeline.target='_blank';timeline.rel='noopener';timeline.className='button button-secondary';
  canvas.setAttribute('aria-label','先点选蓝色区域，再点骨骼。也可使用下方区域和骨骼选择。');
  for(const b of [load,save,undo]){b.type='button';b.className='button button-secondary';}
  controls.className='automation-actions';controls.append(region,load,save,undo);
  element.append(title,node('p','选择区域后点骨骼进行绑定。初始位置仅为几何建议；保存后重建，保留原纹理和零散像素。'),controls,status,timeline,canvas,rows);
  let key=null,job=null,history=null,endpoint='',disabled=true,busy=false,epoch=0,plan=null,selected=null,choices={},images=null;
  let view={left:0,top:0,scale:1};
  function draw(){
    if(!images||!plan)return;
    const points=plan.bones.map(b=>b.point),xs=[0,plan.width,...points.map(p=>p[0])],ys=[0,plan.height,...points.map(p=>p[1])];
    view.left=Math.min(...xs)-20;view.top=Math.min(...ys)-20;
    view.scale=Math.min(1,1100/(Math.max(...xs)-view.left+20),1100/(Math.max(...ys)-view.top+20));
    canvas.width=Math.ceil((Math.max(...xs)-view.left+20)*view.scale);canvas.height=Math.ceil((Math.max(...ys)-view.top+20)*view.scale);
    const ctx=canvas.getContext('2d');ctx.fillStyle='#253342';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.save();ctx.scale(view.scale,view.scale);ctx.translate(-view.left,-view.top);ctx.drawImage(images.source,0,0);
    for(const part of plan.parts){ctx.globalAlpha=part.component_id===selected?1:.25;ctx.drawImage(images.parts[part.component_id],...part.bbox.slice(0,2));}
    ctx.globalAlpha=1;const bones=Object.fromEntries(plan.bones.map(b=>[b.name,b]));
    for(const bone of plan.bones){
      const parent=bones[bone.parent];ctx.strokeStyle='#71d6fb';ctx.lineWidth=1/view.scale;
      if(parent){ctx.beginPath();ctx.moveTo(...parent.point);ctx.lineTo(...bone.point);ctx.stroke();}
      ctx.fillStyle=choices[selected]===bone.name?'#ffd166':'#71d6fb';ctx.beginPath();ctx.arc(...bone.point,4/view.scale,0,Math.PI*2);ctx.fill();
      ctx.font=`${11/view.scale}px sans-serif`;ctx.fillText(bone.name,bone.point[0]+6/view.scale,bone.point[1]);
    }
    ctx.restore();
  }
  function renderRows(){
    rows.replaceChildren();
    for(const part of plan?.parts||[]){
      const row=node('div'),pick=node('button',`${part.component_id} · ${part.visible_pixels} 像素`),parent=node('select');
      row.className='automation-actions';pick.className='button button-secondary';
      pick.type='button';pick.disabled=disabled||busy;pick.setAttribute('aria-pressed',String(selected===part.component_id));
      pick.onclick=()=>{selected=part.component_id;draw();renderRows();};
      parent.setAttribute('aria-label',`${part.component_id} 的父骨骼`);
      if(plan.requires_parent_review){const empty=node('option',`待选择（距离建议：${part.proposed_parent}）`);empty.value='';parent.append(empty);}
      for(const bone of plan.allowed_parents){const option=node('option',bone);option.value=bone;parent.append(option);}
      parent.value=choices[part.component_id];parent.disabled=disabled||busy;
      parent.onchange=()=>{choices[part.component_id]=parent.value;selected=part.component_id;draw();render();};
      row.append(pick,parent);rows.append(row);
    }
  }
  function render(){
    const active=Boolean(history?.active);
    load.disabled=disabled||busy||active||job?.status!=='needs_review'||!region.value;region.disabled=disabled||busy||active;
    save.disabled=disabled||busy||active||!plan?.parts.length||!images||plan.parts.some(p=>!plan.allowed_parents.includes(choices[p.component_id]));
    undo.hidden=!active;undo.disabled=disabled||busy;
    canvas.hidden=!plan||active;rows.hidden=!plan||active;
    timeline.hidden=disabled||!job?.runtime?.files?.['mount/index.html'];
    if(timeline.hidden)timeline.removeAttribute('href');else timeline.setAttribute('href',`${endpoint}/jobs/${job.job_id}/view/mount/index.html`);
    if(active)status.textContent=`已保存 ${Object.keys(history.review.decision.parents).length} 个部件映射。${['pending','running'].includes(job?.status)?'整角色正在构建，完成后可查看时间轴。':job?.component_mounts?.review_sha256===history.head_sha256?'当前候选已应用，可查看时间轴。':'请重建整角色候选以应用。'}`;
    renderRows();
  }
  async function prepare(){
    if(load.disabled)return;
    const token=++epoch,sourceJob=job,base=endpoint;busy=true;status.textContent='正在解析可见区域与骨架…';render();
    try{
      const value=await hooks.apiRequest(`${base}/component-mount-plan`,{method:'POST',headers:{'X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify({job_id:sourceJob.job_id,region_id:region.value})});
      if(token!==epoch)return;
      if(value.schema!=='autospine.component-mount-canvas/v1'||value.authority!=='none'||value.job_id!==sourceJob.job_id||value.source_bundle_sha256!==sourceJob.artifact_sha256)throw Error('source');
      const image=src=>new Promise((resolve,reject)=>{const img=document.createElement('img');img.onload=()=>resolve(img);img.onerror=reject;img.src=src;});
      const source=await image(value.image),parts={};
      for(const part of value.parts)parts[part.component_id]=await image(part.mask);
      if(token!==epoch)return;
      plan=value;images={source,parts};choices=Object.fromEntries(value.parts.map(p=>[p.component_id,value.requires_parent_review?'':p.proposed_parent]));selected=value.parts[0]?.component_id;
      status.textContent=`${value.parts.length} 个可绑定区域；${value.residual_pixels} 个零散像素独立保留。请检查每个区域的父骨骼。`;draw();
      if(value.requires_parent_review)status.textContent+=' 衣层包含多个独立部件，距离建议未选用；请选择实际归属，裙摆不应仅因距离近而绑定腿骨。';
    }catch(e){if(token===epoch)status.textContent='当前区域无法准备分区绑定，请检查来源或刷新重试。';}
    finally{if(token===epoch){busy=false;render();}}
  }
  canvas.onclick=event=>{
    if(disabled||busy||!plan||!images)return;
    const box=canvas.getBoundingClientRect();
    const x=(event.clientX-box.left)*canvas.width/box.width/view.scale+view.left,y=(event.clientY-box.top)*canvas.height/box.height/view.scale+view.top;
    const nearest=plan.bones.map(b=>({b,d:Math.hypot(b.point[0]-x,b.point[1]-y)})).sort((a,b)=>a.d-b.d)[0];
    if(selected&&nearest?.d<=9/view.scale){choices[selected]=nearest.b.name;draw();render();return;}
    for(const part of plan.parts){
      const [l,t,r,b]=part.bbox;if(x<l||x>=r||y<t||y>=b)continue;
      const mask=node('canvas');mask.width=r-l;mask.height=b-t;const ctx=mask.getContext('2d');ctx.drawImage(images.parts[part.component_id],0,0);
      if(ctx.getImageData(Math.floor(x-l),Math.floor(y-t),1,1).data[3]){selected=part.component_id;draw();renderRows();return;}
    }
  };
  load.onclick=()=>void prepare();
  save.onclick=()=>{if(save.disabled)return;void hooks.save({action:'replace',job_id:job.job_id,allowed_parents:plan.allowed_parents,
    decision:{schema:'autospine.component-mount-decision/v1',source_bundle_sha256:plan.source_bundle_sha256,source_region_id:plan.source_region_id,
      plan_sha256:plan.plan_sha256,decision_source:'human_confirmation',reversible:true,parents:{...choices}}});};
  undo.onclick=()=>{if(!undo.disabled)void hooks.save({action:'revoke'});};
  region.onchange=()=>{epoch++;busy=false;plan=images=null;choices={};status.textContent='点击显示区域与骨架，检查后再保存。';render();};
  return {element,sync(value,saved,base,locked){
    const next=`${base}|${value?.artifact_sha256||''}|${saved?.head_sha256||''}`;
    if(next!==key){epoch++;key=next;plan=images=null;choices={};busy=false;region.replaceChildren();
      for(const layer of value?.layers||[])for(const part of layer.regions||[])if(part.state==='static_reference'&&!part.region_id.includes('residual')){
        const option=node('option',`${layer.layer_id} · ${part.region_id}`);option.value=part.region_id;region.append(option);
      }
      region.value=region.children[0]?.value||'';status.textContent='点击显示区域与骨架，检查后再保存。';
    }
    job=value;history=saved;endpoint=base;disabled=locked;render();
    element.hidden=!saved?.active&&!region.children.length;
  },dispose(){epoch++;}};
}
