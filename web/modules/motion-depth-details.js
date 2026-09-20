const states={needs_changes:'有待处理的遮挡关系',evidence_incomplete:'遮挡检查尚未完成',
  sampled_candidate:'已生成限定采样通过的排序候选',sampled_no_change:'限定采样通过，保留原顺序',not_evaluated:'尚无可用遮挡结论'};
const categories={depth_conflict:'前后关系冲突',resource_limit:'计算限制，尚未测完',unsupported_check:'当前检查不支持'};

export function appendDepthDetails(item,job) {
  const button=document.createElement('button'); button.textContent='在此查看遮挡状态';
  const panel=document.createElement('section'); panel.hidden=true; panel.setAttribute('aria-live','polite');
  const base=`/api/motions/${job.job_id}/view/`;
  button.onclick=async()=>{
    button.disabled=true; panel.hidden=false; panel.textContent='正在读取当前候选的遮挡证据…';
    try {
      const response=await fetch(base+'depth-status.json',{cache:'no-store'});
      const report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'读取失败');
      if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选版本已变化，请刷新任务');
      panel.replaceChildren();
      const title=document.createElement('h4'); title.textContent=states[report.status]||'状态未知'; panel.append(title);
      const counts=document.createElement('p');
      counts.textContent=Object.entries(report.failure_record_counts).map(([key,value])=>`${categories[key]||key}：${value} 条`).join('；')||'没有已记录的排序失败；需结合采样状态判断。';
      panel.append(counts);
      if(report.has_incomplete_checks){
        const pending=document.createElement('p');
        pending.textContent='仍有未完成或不支持的检查，不能据此判定遮挡正确。'; panel.append(pending);
      }
      const label=document.createElement('label'); label.textContent='显示记录：';
      const select=document.createElement('select');
      for(const [value,text] of Object.entries({all:'全部',...categories})){
        const option=document.createElement('option'); option.value=value; option.textContent=text; select.append(option);
      }
      label.append(select); panel.append(label);
      const list=document.createElement('div'); panel.append(list);
      function show(){
        list.replaceChildren();
        const rows=report.records.filter(r=>select.value==='all'||r.category===select.value);
        for(const row of rows.slice(0,20)){
          const p=document.createElement('p');
          p.textContent=`${categories[row.category]||row.category}${row.pair?.length?' · '+row.pair.join(' / '):''} `;
          const link=document.createElement('a'); link.textContent=`定位 ${row.time.toFixed(3)} 秒`;
          link.href=base+`player.html?time=${row.time}`; link.target='_blank'; link.rel='noopener'; p.append(link); list.append(p);
        }
        if(!rows.length)list.textContent='此类别没有已记录项。';
        if(rows.length>20||report.records_truncated){const note=document.createElement('p');note.textContent='当前仅显示部分记录，完整内容见遮挡报告。';list.append(note);}
      }
      select.onchange=show; show();
      const note=document.createElement('p');
      note.textContent='以上为诊断记录数，不是错误率。可使用任务卡片的“比较该角色的已有视角候选”寻找替代视角；阶段验收记录保持不变。';panel.append(note);
    }catch(error){panel.textContent='无法检查：'+error.message;}
    finally{button.disabled=false;}
  };
  item.append(button,panel);
}
