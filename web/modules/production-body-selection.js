// Only verified registrations belonging to this run's body are selectable.
export function bodySelection(panel,run,api,changed){
  const stage=run.stages.body;
  if(stage.status!=='succeeded'||!stage.job_id)return ()=>undefined;
  const section=document.createElement('section'),label=document.createElement('label');
  label.textContent='身体修复版本';
  const select=document.createElement('select');select.setAttribute('aria-label','身体修复版本');
  label.append(select);const refresh=document.createElement('button');refresh.textContent='刷新身体修复候选';
  const note=document.createElement('p'),link=document.createElement('a');link.textContent='播放所选身体版本';link.target='_blank';link.rel='noopener';
  section.append(label,refresh,note,link);panel.append(section);
  let ready=false,serial=0,rows=[];
  const base=`/api/motions/${stage.job_id}/view/`;
  const update=()=>{const row=rows.find(r=>r.selector===select.value);if(select.value&&!row){link.removeAttribute('href');note.textContent='此前修复版本已失效，请选择原身体候选或其他有效版本。';return;}
    link.href=select.value?row.player_url:base+'player.html';link.hidden=false;
    note.textContent=select.value?'将该修复版本接入联合动画。原身体候选保留；原接受记录不作为新结果验收。':'使用原身体候选；修改观察角将重新生成身体动作。';};
  select.onchange=()=>{changed();update();};
  async function load(){const version=++serial;ready=false;select.disabled=true;refresh.disabled=true;changed();
    const previous=select.options.length?select.value:(run.request.body_selection?.selector||'');
    try{const value=await api(`/api/production/${run.run_id}/body-candidates`);if(version!==serial)return;
      if(value.baseline_sha256!==stage.artifact_sha256)throw Error('身体来源版本已变化，请刷新制作任务');
      select.replaceChildren(new Option('原身体候选',''));
      rows=value.rows;
      for(const [i,row] of rows.entries())select.add(new Option(`修复候选 ${i+1} · ${row.kind==='repair_job'?'局部修复':'登记版本'} · ${row.artifact_sha256.slice(0,10)}`,row.selector));
      if(previous&&!rows.some(r=>r.selector===previous)){const missing=new Option('此前修复版本不可用',previous);missing.disabled=true;select.add(missing);}
      select.value=previous;ready=true;update();
      if(value.unavailable.length)note.append(` ${value.unavailable.length} 个版本来源检查未通过，不能采用。`);
    }catch(e){note.textContent=`无法读取修复版本：${e.message}`;link.removeAttribute('href');}
    finally{select.disabled=!ready;refresh.disabled=false;}}
  const initial=run.request.body_selection?.selector||'';
  select.add(new Option(initial?'当前所选修复版本':'原身体候选',initial));select.disabled=true;
  note.textContent='沿用当前身体版本；需要切换时点击“刷新身体修复候选”。重建前会核对来源。';
  if(initial)link.hidden=true;else link.href=base+'player.html';
  refresh.onclick=load;
  return ()=>{if(serial===0)return initial;if(!ready)throw Error('请等待身体修复版本核对完成');if(select.value&&!rows.some(r=>r.selector===select.value))throw Error('请重新选择有效的身体版本');return select.value;};
}
