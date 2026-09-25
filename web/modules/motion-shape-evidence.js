// Diagnostic evidence stays separate from the candidate's acceptance gates.
export function shapeNextStep(value) {
  const residual=value?.bone_compensated;
  if(!value||value.status==='unavailable')return '缺少形状对照，不能据此选择改绑或投影修复。';
  if(value.reference_kind!=='single_bone_affine')return '多骨区域尚不能分离投影缩放与权重混合；先对照同帧源姿态及移除 deform 的结果，不直接归因为绑骨错误。';
  if(!residual||![residual.minimum_stretch,residual.maximum_stretch,residual.signed_area_ratio].every(Number.isFinite))
    return '骨骼补偿不可用，先检查退化骨骼及源姿态，不能按局部形状正常处理。';
  if(residual.signed_area_ratio<=0)return '扣除骨骼变换后仍有翻转，优先检查该区域的局部形状和 deform。';
  if(Math.abs(residual.minimum_stretch-1)<=1e-6&&Math.abs(residual.maximum_stretch-1)<=1e-6)
    return '数值容差内未测到骨骼变换之外的额外拉伸。先检查驱动骨缩放、源姿态投影和可用视角；仅凭面积失败不足以要求重新绑骨。仍需检查形状、接缝和视觉，原失败保留。';
  return '扣除骨骼变换后仍有局部形状变化；先比较原动作与 deform 对照，再确定是否调整局部几何。不能仅凭此项认定权重错误。';
}
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
  lines.push(shapeNextStep(value));
  return lines.join(' ');
}
