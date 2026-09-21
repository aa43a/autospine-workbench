// Read-only navigation over recorded samples, never interpolation or acceptance.
export function groupDepthFailures(failures){
  const groups=new Map();let invalid=0;
  for(const row of failures){
    if(!Number.isFinite(row.time)||row.time<0){invalid++;continue;}
    const pair=Array.isArray(row.pair)?row.pair.filter(v=>typeof v==='string'):[];
    const reason=typeof row.reason_code==='string'?row.reason_code:'unknown';
    const key=JSON.stringify([pair,reason]);
    if(!groups.has(key))groups.set(key,{pair,reason,times:[]});
    groups.get(key).times.push(row.time);
  }
  for(const group of groups.values())group.times.sort((a,b)=>a-b);
  return {groups:[...groups.values()],invalid};
}

export function appendDepthTimeline(panel,job,readiness,onSeek){
  const button=document.createElement('button');button.textContent='展开完整遮挡失败采样';
  const body=document.createElement('section');body.setAttribute('aria-live','polite');
  button.onclick=async()=>{
    button.disabled=true;body.textContent='正在读取原始遮挡记录…';
    try{
      const base=`/api/motions/${job.job_id}/view/`;
      const response=await fetch(base+'motion-depth.json',{cache:'no-store'});
      const report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(!readiness.skeleton_sha256||report.skeleton_sha256!==readiness.skeleton_sha256)
        throw Error('候选骨架证据已变化，请重新检查');
      if(!Array.isArray(report.order?.failures))throw Error('此报告未提供完整顺序失败记录');
      const {groups,invalid}=groupDepthFailures(report.order.failures);
      body.replaceChildren();
      const note=document.createElement('p');
      note.textContent=`原始报告 ${report.order.failures.length} 条失败记录，${groups.length} 组部件关系；无有效时间 ${invalid} 条。仅定位已有失败采样，首末时间之间不代表连续失败或完整验证。`;
      body.append(note);
      for(const group of groups){
        const section=document.createElement('details'),title=document.createElement('summary');
        const first=group.times[0],last=group.times.at(-1);
        title.textContent=`${group.pair.join(' ↔ ')||'未指定部件'} · ${group.reason} · ${group.times.length} 条 · ${first.toFixed(3)}–${last.toFixed(3)} 秒`;
        const slider=document.createElement('input');slider.type='range';slider.min='0';
        slider.max=String(group.times.length-1);slider.step='1';slider.value='0';
        slider.setAttribute('aria-label','遮挡失败采样序号');
        const label=document.createElement('span'),link=document.createElement('a');
        link.textContent='定位此采样';
        const update=()=>{
          const index=Number(slider.value),time=group.times[index];
          label.textContent=` ${index+1}/${group.times.length} · ${time.toFixed(3)} 秒 `;
          link.href=base+`player.html?time=${encodeURIComponent(time)}`;
          if(onSeek)link.onclick=event=>{event.preventDefault();onSeek(time);};
          else{link.target='_blank';link.rel='noopener';}
        };
        slider.oninput=update;update();section.append(title,slider,label,link);body.append(section);
      }
    }catch(error){body.textContent='无法读取完整定位：'+error.message;}
    finally{button.disabled=false;}
  };
  panel.append(button,body);
}
