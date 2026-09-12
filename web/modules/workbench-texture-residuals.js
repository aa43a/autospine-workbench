"use strict";
const REASONS={outside_mesh:"网格外侧",ambiguous_mesh_support:"多个网格覆盖，归属不唯一",
  full_pixel_coverage_required:"整个像素尚未被单个三角形覆盖",
  uv_alignment_required:"纹理坐标尚未对齐",target_alpha_collision:"目标已有不透明像素",
  non_edge_alpha_requires_review:"透明度超过自动归并范围"};

export function residualMessages(job,layer){
  if(job?.status!=="needs_review"||job.texture_trial?.authority!=="none")return [];
  const ids=new Set((layer.regions||[]).map(r=>r.region_id));
  return (job.texture_trial.regions||[]).filter(r=>r.layer_id===layer.layer_id&&ids.has(r.region_id)).map(r=>{
    const reasons=Object.entries(r.blocking_counts||{}).filter(([,v])=>v>0)
      .map(([k,v])=>`${REASONS[k]||k} ${v} 像素`).join("；");
    return `${r.region_id}：已归并 ${r.transferred_pixels} 像素，保留 ${r.remaining_pixels} 像素。${reasons}${r.remaining_pixels===0?"像素已转移，区域绑定及视觉确认仍需复核。":"不会自动排除剩余像素。"}`;
  });
}
