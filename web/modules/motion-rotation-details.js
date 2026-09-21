// Keep continuous turns visible; diagnostics never rewrite a reviewed animation.
const labels={angle_branch_crossing:'角度跨界，连续展开可保留方向',
  projection_direction_unreliable:'投影方向接近消失，不能可靠推断转向',
  half_turn_direction_ambiguous:'相邻采样相差半圈，转向不确定'};

export function appendRotationDetails(item,job){
  const button=document.createElement('button');button.textContent='在此检查旋转与绕圈';
  const panel=document.createElement('section');panel.hidden=true;panel.setAttribute('aria-live','polite');
  const base=`/api/motions/${job.job_id}/view/`;
  button.onclick=async()=>{
    button.disabled=true;panel.hidden=false;panel.textContent='正在核对源方向与实际导出旋转…';
    try{
      const response=await fetch(base+'rotation-status.json',{cache:'no-store'});
      const report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选版本已变化，请刷新任务');
      panel.replaceChildren();
      const note=document.createElement('p');
      note.textContent='超过 360° 不自动视为错误。以下区分源方向跨界与重定向后的额外绕圈；不能据此判断手掌正反面或轴向扭转。动画未修改。';panel.append(note);
      for(const row of report.target.records){
        const detail=document.createElement('details');const title=document.createElement('summary');
        title.textContent=`${row.bone} · ${row.extra_turn_suspected?'疑似新增绕圈':'未发现新增整圈'} · 与源传递最大差 ${row.maximum_transfer_difference_deg.toFixed(2)}°`;
        detail.append(title);
        const events=[...row.source_events.map(e=>({time:e.time,text:labels[e.reason]||e.reason})),
          ...row.large_key_intervals.map(e=>({time:e.start_time,text:`局部关键帧转动 ${e.delta_deg.toFixed(1)}°；源传递 ${e.source_delta_deg.toFixed(1)}°`}))];
        if(row.maximum_transfer_difference_deg>1e-6)events.unshift({time:row.maximum_difference_time,
          text:'最大传递差异；接触修正也可能有意改变局部角度'});
        for(const event of events.slice(0,30)){
          const p=document.createElement('p');p.textContent=event.text+' · ';
          const link=document.createElement('a');link.textContent=`定位 ${event.time.toFixed(3)} 秒`;
          link.href=base+`player.html?time=${event.time}`;link.target='_blank';link.rel='noopener';p.append(link);detail.append(p);
        }
        if(events.length>30){const p=document.createElement('p');p.textContent=`显示前 30 / ${events.length} 条记录`;detail.append(p);}
        panel.append(detail);
      }
      const raw=document.createElement('a');raw.textContent='完整旋转诊断';raw.href=base+'rotation-status.json';raw.target='_blank';raw.rel='noopener';panel.append(raw);
    }catch(error){panel.textContent='无法检查：'+error.message;}
    finally{button.disabled=false;}
  };
  item.append(button,panel);
}
