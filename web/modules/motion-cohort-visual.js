// Human visual decisions remain separate from technical delivery readiness.
export const visualFilters = {
  accepted: '已阶段接受（含保留异常）',
  exceptions: '阶段接受且保留异常',
  rejected: '视觉退回',
  pending: '尚无有效阶段结论',
};

export function visualState(row) {
  if (!row.loaded || !row.applies) return 'pending';
  if (row.decision === 'accepted_with_exceptions') return 'exceptions';
  if (row.decision === 'accepted') return 'accepted';
  if (row.decision === 'rejected') return 'rejected';
  return 'pending';
}

export function matchesVisual(row, filter) {
  const state = visualState(row);
  return !filter || state === filter || filter === 'accepted' && state === 'exceptions';
}

export function visualNotes(row) {
  if (!row.loaded || typeof row.notes !== 'string' || !row.notes.trim()) return '';
  return (row.applies ? '验收说明：' : '历史说明（不适用于当前证据）：') + row.notes;
}
