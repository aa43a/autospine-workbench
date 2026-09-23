export function appendRepairFeasibility(parent,job,row,onSeek) {
  const button=document.createElement('button');button.textContent='检查局部修复限制';
  const status=document.createElement('p');status.setAttribute('aria-live','polite');
  button.onclick=async()=>{
    button.disabled=true;status.textContent='正在检查固定顶点约束…';
    try {
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/repair-feasibility.json`,{cache:'no-store'});
      const report=await response.json();if(!response.ok)throw Error(report.reason_code||'检查失败');
      if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选已变化');
      const record=report.rows.find(r=>r.slot===row.slot&&r.animation===row.animation);
      if(!record)throw Error('未找到当前附件检查记录');
      if(record.status==='fixed_vertex_counterexample') {
        status.textContent=`当前策略固定单骨顶点：${record.counterexample_count} 个三角形在 ${record.failed_times} 个采样时刻超限，局部修正无法使它们全部达标。其中 ${record.single_bone_triangles} 个三角形整体随单骨变换。可构建部分改善候选，但需要进一步检查投影、绑定区域或姿态表达；这不证明必须补图。`;
        const link=document.createElement('a');link.textContent=` 定位限制 ${record.worst.time.toFixed(3)} 秒`;
        link.href=`/api/motions/${encodeURIComponent(job.job_id)}/view/player.html?time=${record.worst.time}`;
        if(onSeek)link.onclick=e=>{e.preventDefault();onSeek(record.worst.time);};
        status.append(link);
        const shape=record.worst.shape_evidence;
        if(shape?.reference_kind==='single_bone_affine'&&shape.bone_compensated) {
          const text=document.createElement('p');
          text.textContent=`该定位三角形：实际面积比 ${shape.actual.signed_area_ratio.toFixed(3)}；扣除单骨整体变换后的面积比 ${shape.bone_compensated.signed_area_ratio.toFixed(3)}。后者用于区分整体缩短与额外局部变形，不改变几何门槛，也不代表视觉通过。`;
          status.append(text);
        }
      } else status.textContent=record.status==='no_fixed_vertex_counterexample'
        ?'当前采样未发现全固定三角形的面积反例；不代表位移预算、接缝、插值或完整修复一定可行。'
        :'当前附件不支持这项约束检查，不能推定可修复。';
    }catch(error){status.textContent='无法检查：'+error.message;}
    finally{button.disabled=false;}
  };
  parent.append(button,status);
}
