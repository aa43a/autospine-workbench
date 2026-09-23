import {partitionEditor} from './motion-partition-editor.js';
export function materialMapping(parent,job,row) {
  const panel=document.createElement('fieldset');
  panel.innerHTML='<legend>素材区域与动作时段</legend><button type="button">加载回交版本和映射</button><select aria-label="选择回交素材版本"></select><label>开始时间（秒）<input type="number" min="0" step="0.001" aria-label="素材开始时间"></label><label>结束时间（秒）<input type="number" min="0" step="0.001" aria-label="素材结束时间"></label><button type="button">保存区域与时段</button><button type="button">撤销当前素材映射</button><p role="status">选择回交版本，圈选原纹理区域，填写生效时段。保存后等待构建，不改变当前动画。</p>';
  panel.style.cssText='min-width:0;grid-column:1/-1;width:100%;box-sizing:border-box';parent.append(panel);
  const [load,save,withdraw]=panel.querySelectorAll('button'),select=panel.querySelector('select'),[start,end]=panel.querySelectorAll('input'),status=panel.querySelector('p');
  for(const control of panel.querySelectorAll('input,select'))control.style.cssText='max-width:100%;min-width:0;box-sizing:border-box';
  const region=partitionEditor(panel,job,row,{textureOnly:true});let draft=null,state=null,generation=0;
  save.disabled=withdraw.disabled=true;
  const url=`/api/motions/${encodeURIComponent(job.job_id)}/material-mapping`;
  const restore=()=>{
    const latest=state?.history.filter(r=>r.material_bundle_sha256===select.value).at(-1);
    const mapping=latest?.action==='map'?latest.mapping:null;region.restore(mapping);
    start.value=mapping?.interval[0]??'';end.value=mapping?.interval[1]??'';
    save.disabled=!select.value;withdraw.disabled=!mapping;
    status.textContent=mapping?`已恢复 ${mapping.triangles.length} 个三角形，${mapping.interval[0]}–${mapping.interval[1]} 秒；尚未应用。`:'尚无有效映射；圈选区域并填写时间。';
  };
  select.onchange=restore;
  load.onclick=async()=>{
    const token=++generation;panel.disabled=true;
    try{
      const responses=await Promise.all([fetch(`/api/motions/${encodeURIComponent(job.job_id)}/material-return`,{cache:'no-store'}),fetch(url,{cache:'no-store'})]);
      const values=await Promise.all(responses.map(r=>r.json()));if(responses.some(r=>!r.ok))throw Error('无法加载回交记录');
      if(token!==generation)return;
      state=values[1];select.replaceChildren();
      for(const [i,r] of values[0].returns.filter(r=>r.draft_revision===draft&&r.slot===row.slot&&r.animation===row.animation).entries()){
        const option=document.createElement('option');option.value=r.material_bundle_sha256;option.textContent=`版本 ${i+1} · ${r.texture_sha256.slice(0,8)}${r.unchanged_source?'（未修改原图）':''}`;select.append(option);
      }restore();
    }catch(e){status.textContent=e.message;}finally{if(token===generation)panel.disabled=false;}
  };
  const submit=async action=>{
    if(!state||!select.value)return;const token=++generation;panel.disabled=true;
    try{
      const body={action,expected_revision:state.revision,material_bundle_sha256:select.value};
      if(action==='map'){
        if(start.value===''||end.value==='')throw Error('请填写开始和结束时间');
        Object.assign(body,region.value(),{interval:[Number(start.value),Number(end.value)]});
      }
      const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)});
      const value=await response.json();if(!response.ok)throw Error(value.reason_code||'保存失败');
      if(token!==generation)return;state=value;restore();
    }catch(e){status.textContent=e.message;}finally{if(token===generation)panel.disabled=false;}
  };
  save.onclick=()=>submit('map');withdraw.onclick=()=>submit('withdraw');
  return revision=>{generation++;draft=revision;state=null;panel.disabled=false;select.replaceChildren();region.restore(null);start.value=end.value='';save.disabled=withdraw.disabled=true;panel.hidden=!revision;panel.style.display=revision?'':'none';};
}
