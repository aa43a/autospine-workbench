import {appendLocalDepthDetails} from './motion-local-depth-details.js';
const states={needs_changes:'有待处理的遮挡关系',evidence_incomplete:'遮挡检查尚未完成',
  sampled_candidate:'已生成限定采样通过的排序候选',sampled_no_change:'限定采样通过，保留原顺序',not_evaluated:'尚无可用遮挡结论'};
const categories={depth_conflict:'前后关系冲突',resource_limit:'计算限制，尚未测完',unsupported_check:'当前检查不支持'};
const evidenceLabels={missing_depth_support:'缺少深度支持',opposing_model_support:'模型同时存在前后支持',
  interval_margin_uncertain:'深度区间尚不能区分前后',uniform_model_support:'模型支持单一方向，需结合整段约束',
  inconsistent_model_evidence:'模型证据不一致'};

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
      appendLocalDepthDetails(panel,job,base);
      const title=document.createElement('h4'); title.textContent=states[report.status]||'状态未知'; panel.append(title);
      const counts=document.createElement('p');
      counts.textContent=Object.entries(report.failure_record_counts).map(([key,value])=>`${categories[key]||key}：${value} 条`).join('；')||'没有已记录的排序失败；需结合采样状态判断。';
      panel.append(counts);
      if(report.superseded_legacy_overlap_samples){
        const recovered=document.createElement('p');
        recovered.textContent=`${report.superseded_legacy_overlap_samples} 个早期未测位置已有同位置区域检查，当前列表采用后续证据；历史报告保留，完成检查不等于前后关系通过。`;
        panel.append(recovered);
      }
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
        const rows=select.value!=='all'&&report.records_by_category
          ?report.records_by_category[select.value]||[]
          :report.records.filter(r=>select.value==='all'||r.category===select.value);
        for(const row of rows.slice(0,20)){
          const p=document.createElement('p');
          p.textContent=`${categories[row.category]||row.category}${row.pair?.length?' · '+row.pair.join(' / '):''} `;
          if(row.category==='resource_limit')p.append(document.createTextNode(
            `${row.reason_code==='depth_overlap_pixel_budget'?'像素计算预算不足':row.reason_code}；此处未测量，不计作画面错误。 `));
          if(row.model_evidence){
            p.append(document.createTextNode(`（${evidenceLabels[row.model_evidence.kind]||'模型证据待解释'}；不等于已观察到画面错误） `));
          }
          const link=document.createElement('a'); link.textContent=`定位 ${row.time.toFixed(3)} 秒`;
          link.href=base+`player.html?time=${row.time}`; link.target='_blank'; link.rel='noopener'; p.append(link); list.append(p);
        }
        if(!rows.length)list.textContent='此类别没有已记录项。';
        const truncated=select.value==='all'?report.records_truncated:report.category_records_truncated?.[select.value];
        if(rows.length>20||truncated){const note=document.createElement('p');note.textContent='当前仅显示部分记录，完整内容见遮挡报告。';list.append(note);}
      }
      select.onchange=show; show();
      const note=document.createElement('p');
      note.textContent='以上为诊断记录数，不是画面错误数或错误率。排序检查每个时刻遇到首个阻塞即停止，因此列表不代表全部冲突；未测细项另行保留。可使用“比较该角色的已有视角候选”寻找替代视角；阶段验收记录保持不变。';panel.append(note);
    }catch(error){panel.textContent='无法检查：'+error.message;}
    finally{button.disabled=false;}
  };
  item.append(button,panel);
}
