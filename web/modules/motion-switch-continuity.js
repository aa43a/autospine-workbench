// Numerical correspondence is deliberately separate from visible material seams.
export function switchContinuityLines(report) {
  if(!report)return ['切换连续性：此候选尚无同一时刻对照证据，不能按通过处理。'];
  const lines=(report.records||[]).map(row=>{
    const when=Number.isFinite(row.time)?`${row.time.toFixed(6)} 秒`:'未知时刻';
    const direction=row.direction==='enter'?'进入新姿态':'恢复原附件';
    if(row.geometry_status==='correspondence_required')return `${direction} · ${when}：拓扑不同，缺少可比较的顶点对应。`;
    if(!Number.isFinite(row.maximum_vertex_jump_px))return `${direction} · ${when}：缺少几何跳变测量。`;
    const value=row.maximum_vertex_jump_px;
    const amount=value>0&&value<.001?value.toExponential(2):value.toFixed(3);
    const state=row.geometry_status==='unchanged_within_tolerance'?'数值容差内连续':'存在几何跳变';
    return `${direction} · ${when}：${state}；最大位移 ${amount} px，${row.changed_vertices} 个顶点超出数值容差。`;
  });
  if(!lines.length)lines.push('切换连续性：缺少边界记录。');
  lines.push('同一时刻比较两种附件，已排除源动作自身的位移；这不是前后帧速度检查。');
  lines.push('纹理、透明边缘、遮挡及视觉连续性仍需渲染复核；几何连续不代表切换不可见。');
  return lines;
}
