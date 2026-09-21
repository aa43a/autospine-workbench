const labels={depth_margin_ambiguity:'深度接近，暂不能判定前后',missing_depth_support:'缺少深度依据',mixed_front_back_support:'同一区域存在前后支持',uniform_back_proxy:'模型支持后侧',uniform_front_proxy:'模型支持前侧',no_visible_overlap:'没有可见重叠'};
export function appendLocalDepthDetails(panel,job,base){
  const button=document.createElement('button');button.textContent='查看局部深度补充检查';
  const content=document.createElement('section');content.setAttribute('aria-live','polite');
  button.onclick=async()=>{
    button.disabled=true;content.textContent='读取补充证据…';
    try{
      const response=await fetch(base+'local-depth-status.json',{cache:'no-store'}),report=await response.json();
      if(!response.ok||report.artifact_sha256!==job.result.artifact_sha256)throw Error('证据不可用或候选已变化');
      content.replaceChildren();
      const note=document.createElement('p');note.textContent='补充检查不改变当前候选或阶段验收。深度模型结论不等于画面错误。';content.append(note);
      if(!report.reports.length)content.append(document.createTextNode('此候选尚无局部深度补充检查。'));
      for(const evidence of report.reports){
        if(evidence.failure){const error=document.createElement('p');error.textContent='补充检查未完成：'+evidence.failure;content.append(error);continue;}
        const details=document.createElement('details'),summary=document.createElement('summary');
        summary.textContent=`${evidence.spatial_sampling==='barycentric_pixel_intervals'?'逐像素检查':'三角形范围检查'} · ${evidence.interpolation==='source_samples_only'?'源动作帧':'帧间插值模型'}`;details.append(summary);
        for(const pair of evidence.causes.pairs){
          const p=document.createElement('p');p.textContent=pair.pair.join(' / ')+'：'+Object.entries(pair.reasons).map(([k,v])=>`${labels[k]||(k.startsWith('unmeasured:')?'未测：'+k.slice(11):k)} ${v} 项`).join('；');details.append(p);
        }
        for(const row of evidence.records){
          const p=document.createElement('p'),a=document.createElement('a');p.textContent=row.pair.join(' / ')+(row.reason_code?' · 未测 '+row.reason_code:'')+' ';
          a.textContent=`定位 ${row.time.toFixed(3)} 秒`;a.href=base+`player.html?time=${row.time}`;a.target='_blank';a.rel='noopener';p.append(a);details.append(p);
        }
        if(evidence.records_truncated)details.append(document.createTextNode('异常与未测记录各显示最多 20 条定位，以上分类统计覆盖完整记录。'));
        content.append(details);
      }
    }catch(error){content.textContent='无法读取：'+error.message;}
    finally{button.disabled=false;}
  };panel.append(button,content);
}
