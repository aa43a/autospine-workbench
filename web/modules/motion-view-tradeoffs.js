const finite=(n,min,max)=>Number.isFinite(n)&&n>=min&&n<=max;
export function viewRows(report,artifact){
  if(report?.artifact_sha256!==artifact)throw Error('候选身份变化');
  const fail=()=>{throw Error('视角比较证据不完整');};
  if(report.profile!=='candidate-source-view-tradeoffs-v1'||report.authority!=='none'||report.selected!==false||report.production_authorized!==false
    ||!Array.isArray(report.times)||report.times.length<2||report.source_samples!==report.times.length
    ||!Array.isArray(report.source_times)||report.source_times.length!==report.times.length
    ||!Array.isArray(report.candidates)||report.candidates.length<13||report.candidates.length>14)fail();
  for(const values of [report.times,report.source_times])if(values.some((t,i)=>!finite(t,0,Infinity)||(i&&t<=values[i-1])))fail();
  const seen=new Set(),roles=['arm','leg'].flatMap(limb=>['upper','lower'].flatMap(part=>['left','right'].map(side=>`humanoid.${limb}.${part}.${side}`)));
  const rows=report.candidates.map(row=>{
    if(!finite(row.yaw_degrees,-90,90)||seen.has(row.yaw_degrees)||row.current!==(row.yaw_degrees===report.current_yaw))fail();
    seen.add(row.yaw_degrees);const k=row.knees,t=row.torso;
    if(!k||k.sample_count!==report.times.length*2||!Number.isInteger(k.unmeasured_samples)||!finite(k.unmeasured_samples,0,k.sample_count)
      ||!Number.isInteger(k.samples_losing_30_degrees)||!finite(k.samples_losing_30_degrees,0,k.sample_count-k.unmeasured_samples)
      ||!finite(k.minimum_length_ratio,0,1+1e-9)||!(k.maximum_hidden_bend_deg===null||finite(k.maximum_hidden_bend_deg,0,180)))fail();
    if(k.worst===null){if(k.maximum_hidden_bend_deg!==null||k.unmeasured_samples!==k.sample_count)fail();}
    else if(!k.worst||!Number.isInteger(k.worst.frame)||!['left','right'].includes(k.worst.side)
      ||k.worst.time!==report.times[k.worst.frame]||k.worst.source_time!==report.source_times[k.worst.frame]
      ||!finite(k.worst.time,0,Infinity)||k.maximum_hidden_bend_deg===null)fail();
    if(!t||!['measured','unmeasured'].includes(t.status)||!Array.isArray(t.reasons)
      ||(t.status==='measured'?typeof t.source_supported!=='boolean':t.source_supported!==null))fail();
    if(!Array.isArray(row.records)||row.records.length!==roles.length||new Set(row.records.map(r=>r.role)).size!==roles.length)fail();
    for(const r of row.records)if(!roles.includes(r.role)||!Number.isInteger(r.collapsed_samples)||!finite(r.collapsed_samples,0,report.source_samples)
      ||!finite(r.minimum_visibility,0,1+1e-9))fail();
    return {...row,armCollapsed:row.records.filter(r=>r.role.startsWith('humanoid.arm.')).reduce((sum,r)=>sum+r.collapsed_samples,0)};
  });
  if(!seen.has(report.current_yaw)||!Array.from({length:13},(_,i)=>-90+i*15).every(y=>seen.has(y)))fail();
  return rows;
}

const node=(tag,text)=>{const el=document.createElement(tag);el.textContent=text;return el;};
export function appendViewTradeoffs(parent,base,artifact,onSeek){
  const button=node('button','比较视角对膝盖、手臂和躯干的影响'),panel=node('section','');
  panel.setAttribute('aria-label','动作视角取舍');parent.append(button,panel);
  button.onclick=async()=>{
    button.disabled=true;panel.textContent='正在核对同一动作片段…';
    try{
      const response=await fetch(base+'view-tradeoffs.json',{cache:'no-store'}),report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(report.artifact_sha256===artifact&&report.status==='unavailable'&&report.reason==='continuous_camera_has_no_single_current_yaw'){
        panel.textContent='此候选使用随时间变化的视角，不能用单一固定角度表表示。请在动作编辑页调整角度轨道并重新构建比较。';return;
      }
      const rows=viewRows(report,artifact);panel.replaceChildren();
      panel.append(node('p','比较同一动作片段在来源坐标基础上的不同观察方向。侧视可能让膝盖更清楚，却使躯干变窄；当前正面素材不因此具备侧面或背面。表中结果不会更换候选或通过验收。'));
      const table=node('table',''),head=node('tr','');
      for(const title of ['视角','最大弯曲损失','损失 ≥30° 的腿部采样','手臂强缩短采样','来源躯干','定位'])head.append(node('th',title));
      table.append(head);
      for(const row of rows){
        const tr=node('tr',''),k=row.knees;
        const values=[`${row.yaw_degrees}°${row.current?'（当前）':''}`,k.maximum_hidden_bend_deg===null?'未测':k.maximum_hidden_bend_deg.toFixed(1)+'°',
          `${k.samples_losing_30_degrees}/${k.sample_count}；未测 ${k.unmeasured_samples}`,`${row.armCollapsed}/${report.source_samples*4}`,
          row.torso.status==='unmeasured'?'无法观测':row.torso.source_supported?'范围内':'超出范围'];
        for(const value of values)tr.append(node('td',value));
        const action=node('td','');
        if(k.worst){const seek=node('button',`${k.worst.time.toFixed(3)} 秒`);seek.onclick=()=>onSeek(k.worst.time);action.append(seek);}
        else action.textContent='无可定位测量';
        tr.append(action);table.append(tr);
      }
      panel.append(table,node('p','定位按钮跳到当前候选的相同源时刻，不是所列视角的新动画。30° 和强缩短计数仅供诊断；来源躯干范围内也不证明角色形体、接触或遮挡通过。若需换视角，应另建候选复测并保留当前结果。'));
    }catch(error){panel.textContent='无法比较：'+error.message;}finally{button.disabled=false;}
  };
}
