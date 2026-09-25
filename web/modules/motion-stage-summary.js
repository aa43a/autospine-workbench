import {deliveryLabels, deliveryState} from './motion-cohort-delivery.js';

const visual = {accepted:'阶段可接受', accepted_with_exceptions:'阶段可接受，保留异常',
  rejected:'需要调整', revoked:'已撤销'};

export function stageSummary(state, artifact) {
  if (!state) return '当前候选状态尚未核对；点击“记录 / 查看阶段验收”读取。';
  if (state.artifact_sha256 !== artifact || state.readiness?.artifact_sha256 !== artifact)
    throw Error('候选检查身份不匹配，请刷新任务后重新核对。');
  const delivery = deliveryState({loaded:true, status:state.readiness.status,
    applies:state.current_applies===true, decision:state.current?.decision});
  const stages = Array.isArray(state.readiness.stages) ? state.readiness.stages : [];
  const pending = stages.filter(s=>s.status!=='sampled_pass').map(s=>s.stage);
  const technical = !stages.length ? '未提供分阶段证据'
    : pending.length ? `待处理或未验证：${pending.join('、')}` : '已实施技术检查通过';
  const decision = state.current
    ? `${state.current_applies===true?'':'历史结论（当前证据不适用）：'}${visual[state.current.decision]||'未知结论'}`
    : '尚未阶段验收';
  return `${deliveryLabels[delivery]}。${technical}。视觉：${decision}。`;
}
