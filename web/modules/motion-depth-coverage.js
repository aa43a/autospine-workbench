// Failure records and sampled pair coverage are distinct populations.
export function depthCoverageText(checks) {
  const c=checks.coverage;
  if(!c)return '采样覆盖未记录，不能推断全部已测。';
  return `部件对采样：可见重叠 ${c.visible_pair_samples}，其中深度不明确 ${c.ambiguous_visible_pair_samples}、前后顺序不符 ${c.order_mismatch_pair_samples}；未测 ${c.unmeasured_pair_samples}。这些计数不等于失败记录数，不应相减推算冲突数量。`;
}
