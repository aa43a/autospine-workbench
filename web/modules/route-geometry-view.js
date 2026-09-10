// Advisory geometry: preserve source identity and never label a narrow arm sleeveless.
export function readRouteGeometry(value, context) {
  if (value === undefined) return null;
  if (value?.schema !== 'autospine.route-geometry-evidence/v1' || value.profile !== 'alpha-grid64-arm-distance-v1'
    || value.project_id !== context.projectId || value.source_sha256 !== context.resolvedSha
    || value.authority !== 'none' || value.production_authorized !== false || !Array.isArray(value.records))
    throw Error('路线几何依据与当前项目不匹配。');
  const ids = new Set();
  for (const row of value.records) {
    if (typeof row.layer_id !== 'string' || ids.has(row.layer_id)
      || !['insufficient_evidence','broad_off_axis_shape','no_broad_shape_evidence'].includes(row.classification)
      || !Array.isArray(row.reason_codes) || row.reason_codes.some(code => typeof code !== 'string'))
      throw Error('路线几何记录无效。');
    ids.add(row.layer_id);
    if (row.geometry && (!Number.isFinite(row.geometry.off_axis_ratio) || row.geometry.off_axis_ratio < 0
      || row.geometry.off_axis_ratio > 1 || !Number.isSafeInteger(row.geometry.sample_count)
      || row.geometry.sample_count < 1 || row.geometry.sample_count > 4096)) throw Error('路线采样记录无效。');
  }
  return value;
}

const REASONS = {
  character_side_unknown:'角色左右侧尚未确定', arm_joint_missing_or_nonfinite:'缺少有效肩、肘或腕关节',
  arm_segment_degenerate:'手臂骨段长度无效', arm_joints_unreviewed:'手臂关节尚未复核',
  layer_image_missing:'图层图像尚不可用', layer_image_read_failed:'图层图像读取失败',
  layer_image_invalid:'图层图像格式不支持', layer_bbox_invalid:'图层范围无效',
  layer_image_bbox_mismatch:'图层尺寸与范围不一致', alpha_sampling_empty:'未采到有效透明轮廓',
  alpha_severely_disconnected:'存在明显分离区域，需检查是否混合部件',
  alpha_separated_regions_hint:'发现分离轮廓提示', semantic_review_required:'形状不能确定服装语义',
  narrow_shape_not_sleeveless_proof:'窄轮廓不能证明无袖', route_layer_limit:'超出本次图层分析上限',
};
export function geometryText(row) {
  const label = row.classification === 'broad_off_axis_shape' ? '较宽离轴轮廓'
    : row.classification === 'no_broad_shape_evidence' ? '未发现较宽离轴轮廓' : '依据不足';
  const sample = row.geometry ? ` · 离轴采样占比 ${(row.geometry.off_axis_ratio*100).toFixed(1)}%（${row.geometry.sample_count} 点）` : '';
  return `${row.layer_id}：${label}${sample}。${row.reason_codes.map(code=>REASONS[code] || code).join('；')}。`;
}

export function createRouteGeometryView(document) {
  const details=document.createElement('details'), summary=document.createElement('summary'), list=document.createElement('ul');
  summary.textContent='查看路线判断依据'; details.append(summary,list);
  return {element:details, render(value) {
    details.hidden=!value?.records?.length;
    list.replaceChildren(...(value?.records || []).map(row=>{
      const li=document.createElement('li');li.textContent=geometryText(row);return li;
    }));
  }};
}
