const reasons={
  limb_transverse_source_projection_required:'当前候选缺少实际源姿态投影，请先生成对应的动作候选。',
  motion_transverse_leg_required:'当前工作台入口只验证过腿部，所选部件不是同侧腿骨驱动的区域。',
  limb_transverse_single_limb_required:'该部件跨越不同骨链，需要先检查归属。',
  motion_transverse_bind_changed:'当前角色绑定已变化，请重新生成动作候选。',
  motion_transverse_reference_changed:'姿态参考与当前候选不一致，请重新生成候选。',
  motion_transverse_source_missing:'候选缺少姿态或接触来源，暂时不能修正。',
  motion_transverse_slot_missing:'当前候选没有所选部件的网格与初始姿态参考。',
  limb_transverse_linear_required:'当前动作含非线性关键帧，尚不支持此修正。',
  limb_transverse_dense_deform_required:'当前局部变形格式尚不支持此修正。',
  limb_transverse_timeline_unsupported:'当前动作包含附件切换或不支持的变形轨道。',
  motion_transverse_already_applied:'此部件已补偿过斜切，请回到修正前的候选调整。',
  motion_corrective_slot_already_processed:'此部件已在前序候选中修正，请回到修正前的版本调整。',
  motion_repair_nested_execution_unsupported:'当前修正路线不支持继续处理，或同一部件已经修正。',
};

export function transversePreflight(parent,job,row) {
  const panel=document.createElement('p');panel.setAttribute('role','status');parent.append(panel);
  let generation=0,ready=false;
  return {
    ready:()=>ready,
    async show(visible){
      const ticket=++generation;ready=false;panel.hidden=!visible;if(!visible)return;
      panel.textContent='正在核对腿部绑定和实际源姿态…';
      try{
        const path=[job.job_id,'view','transverse-repair',row.slot,row.animation+'.json'].map(encodeURIComponent).join('/');
        const response=await fetch('/api/motions/'+path,{cache:'no-store'}),report=await response.json();
        if(ticket!==generation)return;
        if(!response.ok)throw Error('无法读取适用条件，请重新加载。');
        if(report.artifact_sha256!==job.result.artifact_sha256||report.slot!==row.slot||report.animation!==row.animation)
          throw Error('候选或部件已变化，请刷新任务。');
        if(!report.available){panel.textContent='当前不能执行腿部斜切修正：'+(reasons[report.reason_code]||report.reason_code||'缺少必要证据。');return;}
        ready=true;
        panel.textContent=`可为此腿部区域生成实验候选（${report.scope.vertex_count} 个顶点）。保留骨骼运动、贴图和原权重，先补偿斜切，再修正关节；作用于整段动作。预检不保证修复成功，结果仍需检查几何、遮挡和实际画面。`;
      }catch(error){if(ticket===generation)panel.textContent=error.message;}
    }
  };
}

export function transverseSummary(report) {
  const labels={min_area_ratio:'最小面积比',max_area_ratio:'最大面积比',max_edge_stretch:'最大边长比',
    inversion_samples:'翻转采样',failing_frame_count:'失败帧数'};
  const lines=[`腿部斜切修正：修正前后均检查 ${report.sample_count} 个相同时刻，斜切补偿最大位移 ${report.maximum_displacement_px.toFixed(3)} px。`,
    `当前部件：${report.geometry_passed?'限定几何采样通过':'仍有几何超限'}；整角色：${report.whole_character_passed?'限定几何采样通过':'仍有几何超限'}。播放与视觉需要独立验收。`];
  const failures=report.metrics.failing_frame_count;
  lines.push(`此部件失败帧数：${failures.before} → ${failures.after}；前后使用相同时间采样。`);
  if(report.regressions.length)lines.push('存在指标回退：'+report.regressions.map(k=>labels[k]||k).join('、')+'。保留原候选，不自动采用。');
  if(report.fixed_area_blocker){
    const b=report.fixed_area_blocker;
    lines.push(`固定区域仍无法满足面积约束：${b.triangles} 个三角形、${b.observations} 条超限记录。本结果保留为诊断候选，原几何门槛继续生效。`);
  }
  lines.push('补偿不会还原缺失的侧背面，也不会消除真实投影造成的缩短。');
  return lines;
}
