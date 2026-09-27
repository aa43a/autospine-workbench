// Each entry belongs to one exact candidate; this index never changes acceptance.
const required = ['投影', '几何', '接触', '遮挡', 'Runtime'];
export function supportExceptions(snapshot) {
  const result = [];
  function inspect(row, context, anchor) {
    const identity = {...context, artifact_sha256: row.artifact_sha256,
      registration_sha256: row.registration_sha256 ?? null, anchor};
    const add = (kind, stage, reason) => result.push({...identity, kind, stage, reason});
    if (row.status !== 'verified' || !row.review) {
      add('evidence', '证据', row.reason || '候选证据未读取');
      return;
    }
    const stages = row.review.readiness?.stages || [];
    for (const stage of stages) {
      if (stage.status !== 'sampled_pass') add(stage.status === 'needs_changes' ? 'technical' : 'evidence',
        stage.stage, stage.explanation || '检查未通过或未完成');
    }
    for (const name of required) {
      if (!stages.some(stage => stage.stage === name)) add('evidence', name, '缺少该项检查');
    }
    if (!['stage_review', 'needs_changes', 'evidence_incomplete'].includes(row.review.readiness?.status)) {
      add('evidence', '整体检查', '整体检查状态未识别');
    } else if (row.review.readiness.status !== 'stage_review' && !stages.some(s => s.status !== 'sampled_pass')) {
      add('evidence', '整体检查', '整体状态尚未通过，需核对完整报告');
    }
    const review = row.review;
    if (!review.current_applies || !review.current || !['accepted', 'accepted_with_exceptions'].includes(review.current.decision)) {
      const imported = !review.current && review.imported_visual;
      add('visual', '阶段结论', imported ? '已有局部导入结论，仍需核对完整候选范围' :
        review.current_applies && review.current?.decision === 'rejected' ? '视觉退回，需调整' :
        review.current && !review.current_applies ? '历史结论不适用于当前证据' : '尚无当前候选的有效阶段接受');
    }
  }
  snapshot.rows.forEach((row, i) => {
    const context = {motion: row.motion, character: row.character, job_id: row.job_id, family: '固定候选'};
    inspect(row, context, `cell-${i}`);
    if (row.status !== 'verified') return;
    for (const [key, label] of [['related', '独立改进'], ['alternatives', '替代视角']]) {
      const family = row[key];
      if (family?.status !== 'verified' || !family.complete) result.push({...context, family: label,
        artifact_sha256: null, registration_sha256: null, anchor: `cell-${i}`, kind: 'evidence', stage: '候选清单',
        reason: family?.reason || '清单或候选证据不完整；不推断未返回候选通过'});
      if (family?.status === 'verified') (family.rows || []).forEach((candidate, j) =>
        inspect(candidate, {...context, family: label, job_id: candidate.job_id || row.job_id}, `cell-${i}-${key}-${j}`));
    }
  });
  for (const row of snapshot.missing) result.push({...row, family: '固定候选', artifact_sha256: null,
    registration_sha256: null, job_id: null, anchor: null, kind: 'evidence', stage: '候选', reason: row.status});
  return result;
}
