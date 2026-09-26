const reasons={
  motion_garment_declaration_missing:'角色尚未生成带明确腰部归属的裙装骨链。',
  motion_garment_torso_required:'当前候选没有躯干投影数据，请先生成启用躯干投影的动作候选。',
  attachment_transport_requires_baked_torso:'当前躯干投影未实际应用，不能进行跟随修正。',
  attachment_transport_source_limits:'源躯干投影超出当前支持范围，需先处理投影异常。',
  motion_garment_slot_undeclared:'所选部件没有声明为随胸部连接的裙装。',
  motion_garment_shared_or_missing_weights:'该骨链影响了其他部件，或没有有效权重，不能单独修正。',
  motion_garment_bind_changed:'当前网格或绑定已变化，需要基于当前角色重新生成候选。',
  motion_repair_nested_execution_unsupported:'当前修正路线不支持继续处理，或同一部位已经修正；请回到合适的原候选。',
  motion_garment_already_applied:'该裙装已做过跟随补偿，不重复叠加；需要调整时请回到补偿前的候选。',
};
export function garmentPreflight(parent,job,row) {
  const panel=document.createElement('p');panel.setAttribute('role','status');parent.append(panel);
  let generation=0,ready=false;
  return {
    ready:()=>ready,
    async show(visible){
      const ticket=++generation;ready=false;panel.hidden=!visible;if(!visible)return;
      panel.textContent='正在核对裙装骨链和躯干投影…';
      try{
        const path=[job.job_id,'view','garment-follow',row.slot,row.animation+'.json'].map(encodeURIComponent).join('/');
        const response=await fetch('/api/motions/'+path,{cache:'no-store'}),report=await response.json();
        if(ticket!==generation)return;
        if(!response.ok)throw Error('无法读取适用条件，请重新加载。');
        if(report.artifact_sha256!==job.result.artifact_sha256||report.slot!==row.slot||report.animation!==row.animation)
          throw Error('候选或部件已变化，请刷新任务。');
        if(!report.available){panel.textContent='当前不能执行裙腰跟随：'+(reasons[report.reason_code]||report.reason_code||'缺少必要证据。');return;}
        ready=true;
        panel.textContent=`可为当前裙装生成跟随候选：${report.scope.roots.length} 条已声明骨链。修正作用于整段动作，只调整此裙装的局部变形；保存后可构建独立任务，重新检查几何、接触与播放。`;
      }catch(error){if(ticket===generation)panel.textContent=error.message;}
    }
  };
}

export function garmentSummary(report) {
  const lines=[`裙腰跟随：${report.roots.length} 条已声明骨链，最大根部位移 ${report.maximum_root_shift_px.toFixed(3)} px；修正前后均检查 ${report.validation_sample_count} 个相同时刻。`];
  const contact=report.waist_contact;
  lines.push(contact?.status==='measured'
    ?`腰部 ${contact.anchors} 组材料点最大分离：${contact.before.separation_px.toFixed(4)} → ${contact.after.separation_px.toFixed(4)} px。这是几何接触采样，透明裂缝和裙腿遮挡仍需查看实际画面。`
    :'腰部材料接触缺少可观测样本，尚未验证；不能将其视为通过。');
  return lines;
}
