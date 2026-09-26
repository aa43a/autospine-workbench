// Explain a diagnostic's next check without declaring a visible rendering defect.
const explanations={
  visible_depth_straddle:['前后深度尚不能整层确定','先隔离该配对并查看局部深度依据；这条记录不证明画面已发生穿插。'],
  visible_unmapped_order_conflict:['排序约束互相冲突','检查环路中的部件关系；单独换动一整层可能影响其他部件。'],
  visible_depth_order_changes_within_interval:['区间内前后建议不同','分别检查两个已有采样；不能将起点的建议沿用到整个区间。'],
  held_interval_depth_missing:['区间采样缺少深度依据','该时刻未完成深度验证，不能据此判断前后正确。'],
  depth_overlap_pixel_budget:['像素检查预算不足','该位置未测完；不计作已看到的画面错误。'],
  depth_overlap_tile_limit:['局部检查数量超限','该位置未测完；不计作已看到的画面错误。'],
  depth_overlap_frame_limit:['检查时刻数量超限','该时刻未测完；不计作已看到的画面错误。'],
  depth_overlap_attachment_unsupported:['附件类型尚未支持','需要补充对应附件的检查能力，当前不能给出遮挡结论。']
};
const timeLabels={overlap_sample:'实际重叠采样',constraint_sample:'环路关系采样',
  requested_sample:'缺少依据的请求时刻',unmeasured_sample:'未完成检查的时刻',
  record_time:'报告记录时刻（没有单独的像素采样时间）'};
export function depthReason(reason){return explanations[reason]||[reason,'此诊断尚无专用解释；保留原记录，不能据此自动改绑或换序。'];}
export function depthTimeLabel(kind){return timeLabels[kind]||'未知时间来源';}
