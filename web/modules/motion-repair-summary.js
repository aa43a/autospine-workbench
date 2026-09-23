export async function appendRepairSummary(panel,job) {
  if(!job.result?.repair_profile)return;
  const section=document.createElement('section');panel.append(section);
  section.textContent='正在读取局部修正对照…';
  try {
    const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/repair-summary.json`,{cache:'no-store'});
    const report=await response.json();
    if(!response.ok||report.artifact_sha256!==job.result.artifact_sha256)throw Error('修正结果身份不匹配');
    section.replaceChildren();const title=document.createElement('h4');title.textContent='局部修正前后';section.append(title);
    for(const [label,geometry] of [['原候选',report.before],['修正候选',report.after]]) {
      const row=geometry.records.find(r=>r.slot===report.slot);const p=document.createElement('p');
      p.textContent=row?`${label} · ${report.slot}：最小面积比 ${row.min_area_ratio.toFixed(3)}，最大边长比 ${row.max_edge_stretch.toFixed(3)}，翻转采样 ${row.inversion_samples}，检查 ${row.sample_count} 帧。`:`${label}：缺少附件检查记录。`;
      section.append(p);
    }
    const note=document.createElement('p');note.textContent='新候选保留原检查时刻并增加修正关键点与中点；采样数可能不同，失败次数不能直接当作错误率比较。骨骼与其他附件保持不变，遮挡和视觉尚未重新接受。';
    const link=document.createElement('a');link.textContent='查看原候选';link.href='/motions.html#'+encodeURIComponent(report.parent_job_id);
    section.append(note,link);
  }catch(error){section.textContent='无法读取修正对照：'+error.message;}
}
