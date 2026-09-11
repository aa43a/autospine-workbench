const STAGES = [
  ['weights','生成服装权重'],['root','建立驱动根部'],['interface','分析连接边界'],
  ['anchors','建立连接点'],['motion','检查动作范围'],['connection','求解袖口连接'],
  ['boundary','检查变形预算'],['cuff','平滑袖口权重'],['repair','自动修正与分支比较'],
  ['spine','导出 Spine 候选'],['contacts','检查纹理接缝'],['overlap','检查重叠'],
  ['runtime','官方核心验证'],['framebuffer','官方画面捕获']
];
const NAMES = new Map([...STAGES,
  ['ordinary-repair', '调整普通袖权重'], ['ordinary-deform', '修正普通袖局部变形'],
  ['ordinary-interpolation', '检查普通袖帧间过渡']]);

export function sleeveProgress(job) {
  const completed = job?.result?.steps;
  const ids = completed?.map(s => s.id) || job?.stage_ids;
  const stages = Array.isArray(ids) && ids.length ? ids.map(id => [id, NAMES.get(id) || `处理阶段 ${id}`]) : STAGES;
  const match = /^([\w-]+):\s*(running|succeeded|cached)$/.exec(job?.step || '');
  const index = stages.findIndex(([id]) => id === match?.[1]);
  const terminal = job && !['pending','running'].includes(job.status);
  const count = completed ? completed.filter(s => s.status === 'succeeded').length
    : index < 0 ? 0 : index + (match[2] === 'running' ? 0 : 1);
  const total = completed?.length || stages.length;
  const sourceIssue = ['project_snapshot_stale', 'sleeve_draft_changed', 'sleeve_annotation_required',
    'sleeve_annotation_source_changed', 'sleeve_source_check_failed'].includes(job?.reason_code);
  const label = !job ? '尚未构建' : sourceIssue ? '已有任务需要更新来源'
    : job.status === 'pending' ? '已排队，等待开始'
    : job.status === 'failed' ? '构建失败，需要处理'
    : job.status === 'canceled' ? '构建已取消，可重新构建'
    : job.status === 'blocked' ? '质量检查未通过'
    : terminal ? '构建完成，等待视觉复核'
    : index < 0 ? '正在准备' : `正在${stages[index][1]}`;
  return { count, total, label, stages: stages.map(([id,name], i) => ({ name,
    state: completed ? (completed.find(s => s.id === id)?.status === 'succeeded' ? 'done' : 'pending')
      : i < count ? 'done' : !terminal && i === index ? 'current' : 'pending' })) };
}
