const errors={motion_contact_plan_unavailable:'该衣料范围版本不存在，请先保存草稿',motion_contact_plan_changed:'草稿已被替代或撤销，请重新加载',motion_contact_mesh_changed:'关联网格已变化，请重新标注',motion_contact_active_attachment_unsupported:'该时刻启用了另一个附件，当前草稿不能用于它'};
export function contactPreflight(parent,job) {
  const button=document.createElement('button'),status=document.createElement('p');
  button.textContent='检查已保存衣料范围的约束';status.setAttribute('role','status');parent.append(button,status);
  let revision=null,digest=null,generation=0;
  button.onclick=async()=>{
    if(!revision)return;const ticket=++generation;button.disabled=true;status.textContent='正在检查该异常时刻的共享顶点和参考映射…';
    try {
      const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/view/contact-scope/${revision}.json`,{cache:'no-store'});
      const report=await response.json();if(!response.ok)throw Error(errors[report.reason_code]||'检查失败，请重新加载当前草稿');if(ticket!==generation)return;
      if(report.artifact_sha256!==job.result.artifact_sha256||report.draft_sha256!==digest)throw Error('候选或草稿已变化，请重新加载');
      const text=document.createElement('p');text.textContent=`${report.time.toFixed(3)} 秒：${report.fixed_targets.length} 个固定区顶点有几何对应，${report.conflicts.length} 个共享顶点运动冲突，${report.unsupported_vertices.length} 个顶点缺少参考覆盖，${report.ambiguous_vertices.length} 个对应存在歧义。未标注 ${report.unknown_triangles.length} 个三角形保持原运动。`;status.replaceChildren(text);
      if(report.conflicts.length){const p=document.createElement('p');p.textContent='固定区要求移动、相邻保留区要求不动的顶点：'+report.conflicts.map(r=>`${r.vertex}（${r.required_displacement_px.toFixed(2)} px）`).join('、')+'。需检查分区边界，不能直接覆盖保留区。';status.append(p);}
      const note=document.createElement('p');note.textContent=report.reasons.includes('sliding_constraints_not_implemented')?'滑动区约束尚未接入执行器；没有将它替换为固定或自由运动。':report.reasons.length?'上述约束仍需处理，未执行修复。':'此时未发现冲突也不证明整段可修复。';status.append(note);
      const limit=document.createElement('p');limit.textContent='本项仅检查当前异常时刻的几何对应，不验证纹理接触、整段动作、Runtime 或视觉质量，未执行修复。';status.append(limit);
    }catch(error){if(ticket===generation)status.textContent='无法检查：'+error.message;}
    finally{if(ticket===generation)button.disabled=false;}
  };
  return (row,sha)=>{generation++;revision=row?.revision??null;digest=sha??null;button.hidden=status.hidden=!revision;button.disabled=false;status.textContent='';};
}
