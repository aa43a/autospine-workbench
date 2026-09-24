// Read-only presentation of existing evidence; never an adoption decision.
export const deliveryLabels = {
  accepted: '技术通过且阶段接受',
  review: '技术通过，待视觉验收',
  visual_changes: '视觉退回待调整',
  technical_changes: '需处理技术异常',
  incomplete: '证据待核实',
  missing: '尚无可复核候选',
};

export function deliveryState(row) {
  if (!row.loaded || !['stage_review', 'needs_changes', 'evidence_incomplete'].includes(row.status)) return 'incomplete';
  if (row.status === 'needs_changes') return 'technical_changes';
  if (row.status === 'evidence_incomplete') return 'incomplete';
  if (row.applies && row.decision === 'rejected') return 'visual_changes';
  if (row.applies && ['accepted', 'accepted_with_exceptions'].includes(row.decision)) return 'accepted';
  return 'review';
}

export function deliveryCounts(rows, missingCount) {
  const counts = Object.fromEntries(Object.keys(deliveryLabels).map(key => [key, 0]));
  for (const row of rows) counts[deliveryState(row)]++;
  counts.missing = missingCount;
  return counts;
}
