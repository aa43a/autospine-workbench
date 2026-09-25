// Related experiments are read-only; their decisions never update the baseline.
export function appendRelatedCandidates(parent, job) {
  const button=document.createElement('button');button.textContent='查看已关联改进候选';
  const panel=document.createElement('section');panel.hidden=true;panel.setAttribute('aria-live','polite');
  const base=`/api/motions/${job.job_id}/view/`;
  button.onclick=async()=>{
    button.disabled=true;panel.hidden=false;panel.textContent='正在核对关联候选…';
    try {
      const response=await fetch(base+'related-candidates.json',{cache:'no-store'});
      if(!response.ok)throw Error('当前服务尚不能读取关联候选，或来源已变化；原候选保持不变。');
      const report=await response.json();
      if(report.baseline_sha256!==job.result.artifact_sha256)throw Error('原任务候选已变化，请刷新后重新查看。');
      if(!Array.isArray(report.rows)||report.rows.length>24)throw Error('关联清单无效');
      panel.replaceChildren();
      if(!report.rows.length)panel.textContent='此任务尚无已核验的改进候选。';
      for(const row of report.rows){
        if(!/^[a-f0-9]{64}$/.test(row.registration_sha256)||!/^[a-f0-9]{64}$/.test(row.candidate_sha256))throw Error('候选身份无效');
        const detail=document.createElement('details'),summary=document.createElement('summary');
        summary.textContent=`改进候选 ${row.candidate_sha256.slice(0,10)} · 对照播放与下载`;
        const note=document.createElement('p');
        note.textContent=`目标 Spine ${row.target_version}；实际 Runtime ${row.runtime_version}，${row.sampled_frames} 个已有采样。与原任务共享动作和角色来源，策略及结果不同；不替换原任务。`;
        const visual=document.createElement('p');
        visual.textContent=row.visual ? `本候选阶段记录：${row.visual.user_response||row.visual.decision}。范围：${row.visual.scope}。保留异常：${(row.visual.retained_exceptions||[]).join('、')||'见记录'}。` : '本候选尚无阶段视觉记录。';
        const path=base+'related-candidates/'+row.registration_sha256+'/';
        const play=document.createElement('button');play.textContent='加载改进候选时间轴';
        play.onclick=()=>{const frame=document.createElement('iframe');frame.title='关联改进候选时间轴';frame.src=path+'player.html';frame.style.cssText='width:100%;height:65vh;border:0';play.replaceWith(frame);};
        const download=document.createElement('a');download.textContent='下载此候选（含异常与来源记录）';download.href=path+'candidate.zip';download.download='motion-related-'+row.candidate_sha256.slice(0,10)+'.zip';
        const evidence=document.createElement('a');evidence.textContent='查看关联依据';evidence.href=path+'report.json';evidence.target='_blank';evidence.rel='noopener';
        detail.append(summary,note,visual,play,download,document.createTextNode(' · '),evidence);panel.append(detail);
      }
    }catch(error){panel.textContent=error.message;}
    finally{button.disabled=false;}
  };
  parent.append(button,panel);
}
