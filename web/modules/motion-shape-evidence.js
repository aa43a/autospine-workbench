// Diagnostic evidence stays separate from the candidate's acceptance gates.
export function describeShape(value) {
  if (!value || value.status === 'unavailable') return '形状对照不可用，原几何失败继续保留。';
  const range = shape => `${shape.minimum_stretch.toFixed(3)}–${shape.maximum_stretch.toFixed(3)} 倍`;
  const lines = [`三角形主方向伸缩：当前 ${range(value.actual)}；未加修正 ${range(value.without_deform)}。`];
  lines.push('驱动骨相对原姿态的伸缩：' + value.bones.map(row => `${row.bone} ${range(row)}`).join('；') + '。');
  if (value.reference_kind === 'single_bone_affine' && value.bone_compensated) {
    lines.push(`单骨区域，扣除骨骼仿射变化后的伸缩：${range(value.bone_compensated)}。接近 1 表示网格跟随骨骼，不代表视觉通过。`);
  } else {
    lines.push('多骨区域：骨骼缩放与混合权重同时参与，投影面积仅为参考，不能据此断言是正常透视缩短或绑骨错误。');
  }
  return lines.join(' ');
}
