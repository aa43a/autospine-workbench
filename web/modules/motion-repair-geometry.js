// Keep each animation/attachment separate: a passing setup mesh says nothing
// about the variant which becomes active later in the same slot.
export function geometryLines(label, geometry, slot) {
  const rows=(geometry?.records||[]).filter(row=>row.slot===slot);
  if(!rows.length)return [`${label}：缺少附件检查记录。`];
  return rows.map(row=>{
    const identity=[slot,row.attachment,row.animation].filter(Boolean).join(' / ');
    const status=row.passed===true?'限定采样通过':row.passed===false?'需处理':'状态未提供';
    return `${label} · ${identity} · ${status}：最小面积比 ${row.min_area_ratio.toFixed(3)}，最大边长比 ${row.max_edge_stretch.toFixed(3)}，翻转采样 ${row.inversion_samples}，检查 ${row.sample_count} 帧。`;
  });
}
