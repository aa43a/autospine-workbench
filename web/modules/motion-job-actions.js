const active = new Set(['pending', 'running']);
export function jobAction(job) {
  if (active.has(job.status)) return {action:'cancel',
    label:job.cancel_requested ? '正在停止任务…' : '取消任务',
    disabled:Boolean(job.cancel_requested)};
  const operation=job.kind==='adapt' ? '重新构建角色动作' : job.kind==='generate' ? '重新生成动作' : '重新解析来源';
  return {action:'retry',label:`${operation}（保留旧记录）`,disabled:false};
}

export function successorId(original, response) {
  const id=response?.job_id;
  if(!/^motion-[a-f0-9]{32}$/.test(id)||id===original)throw Error('重试未返回新的任务记录，请刷新检查');
  return id;
}
