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
      if(report.vertex_roles?.transition?.length){const p=document.createElement('p');p.textContent=`过渡区有 ${report.transition_only_vertices.length} 个可独立调整顶点，${report.transition_preserved_vertices.length} 个共享顶点须保留原运动。过渡区求解尚未接入执行器，不会自动采用实验结果。`;status.append(p);}
      if(report.occlusion_review?.required){const p=document.createElement('p');p.textContent=`覆盖区 ${report.vertex_roles.occlusion.length} 个顶点保留原运动，不生成固定或沿边约束。材料点分离不直接算裂缝；仍需在实际画面检查袖根露出、连接及前后覆盖，本次尚未检查。`;status.append(p);}
      if(report.occlusion_review?.render_partition){const p=document.createElement('p'),part=report.occlusion_review.render_partition;p.textContent=part.status==='prepared'?`已验证可表示为 ${part.regions.length} 个独立绘制区域，${part.unclassified_triangles} 个三角形仍未标注。全部区域保留原权重、运动和绘制顺序；这里只生成内存分区，未保存新候选，也未执行遮挡修复。`:`当前覆盖区无法生成独立绘制区域：${part.reason_code}。原候选保持不变。`;status.append(p);}
      if(report.occlusion_review?.draw_order){const p=document.createElement('p');p.textContent=report.occlusion_review.draw_order.reference_can_cover_in_order?'此时参考附件画在覆盖区前方；顺序允许遮挡，但仍未证明纹理实际覆盖。':'此时参考附件画在覆盖区后方，与所标记的覆盖关系相反。请检查参考附件或该时段的绘制顺序；不会自动换序或拉动网格。';status.append(p);}
      if(report.occlusion_review?.order_timeline){const timeline=report.occlusion_review.order_timeline,details=document.createElement('details'),title=document.createElement('summary');title.textContent='整段动作的前后顺序';details.append(title);const note=document.createElement('p');note.textContent=timeline.status==='measured'?'以下区间含起点、不含终点，动作末帧单独列出。只检查绘制顺序，不表示该时段纹理相交，也不把当前覆盖标注扩展到整段。':'顺序时间表超出检查预算，未检查，不能视为通过。';details.append(note);if(timeline.status==='measured'){for(const range of timeline.intervals){const p=document.createElement('p');p.textContent=`${range.start.toFixed(6)}–${range.end.toFixed(6)} 秒：参考附件在${range.reference_can_cover_in_order?'前':'后'}方`;details.append(p);}const p=document.createElement('p');p.textContent=`末帧 ${timeline.endpoint.time.toFixed(6)} 秒：参考附件在${timeline.endpoint.reference_can_cover_in_order?'前':'后'}方`;details.append(p);}status.append(details);}
      if(report.occlusion_review?.texture_samples){const p=document.createElement('p'),a=report.occlusion_review.texture_samples,c=a.counts||{};p.textContent=a.status==='sampled'?`覆盖区中心采样：参考纹理不透明 ${c.opaque_reference||0}，部分透明 ${c.partial_reference||0}，已露出 ${c.exposed||0}，源图透明 ${c.source_transparent||0}，几何退化或对应不明 ${(c.degenerate_source||0)+(c.reference_mapping_ambiguous||0)}。每个三角形只取一个点，不是覆盖面积；还需结合前后顺序，露出不自动判错。`:'当前纹理采样不可用，不能当作覆盖通过。';status.append(p);}
      const note=document.createElement('p');note.textContent=report.reasons.includes('sliding_constraints_not_implemented')?'滑动区约束尚未接入执行器；没有将它替换为固定或自由运动。':report.reasons.length?'上述约束仍需处理，未执行修复。':'此时未发现冲突也不证明整段可修复。';status.append(note);
      const limit=document.createElement('p');limit.textContent='本项仅检查当前异常时刻的几何对应，不验证纹理接触、整段动作、Runtime 或视觉质量，未执行修复。';status.append(limit);
    }catch(error){if(ticket===generation)status.textContent='无法检查：'+error.message;}
    finally{if(ticket===generation)button.disabled=false;}
  };
  return (row,sha)=>{generation++;revision=row?.revision??null;digest=sha??null;button.hidden=status.hidden=!revision;button.disabled=false;status.textContent='';};
}
