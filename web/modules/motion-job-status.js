// Legacy lifecycle reason codes are shared; present the actual operation.
export function jobStatus(job,states,reasons,steps){
  const operation=job.kind==='generate'?'生成':job.kind==='adapt'?'构建':'解析';
  let state=states[job.status]||job.status;
  if(job.status==='pending')state=`等待${operation}`;
  if(job.status==='running')state=job.cancel_requested?'正在停止':`${operation}中`;
  if(job.status==='succeeded')state=job.kind==='adapt'?'角色候选已生成':`${operation}完成`;
  let detail=job.reason_code?(reasons[job.reason_code]||job.reason_code):steps[job.step];
  if(job.reason_code==='motion_decode_timeout')detail=`${operation}超过处理时限，输入与历史记录保留，可独立重试。`;
  if(job.reason_code==='motion_target_timeout')detail='角色构建超过总运行时限，已停止；输入和历史记录保留，可缩短动作后重试。';
  if(job.reason_code==='motion_target_stalled')detail='角色构建长时间未更新进度，已停止；请查看诊断记录后重试。';
  if(job.reason_code==='motion_decode_failed')detail=`${operation}失败，输入与诊断保留。`;
  if(job.reason_code==='motion_final_leg_fixed_vertices_infeasible')detail='固定区域超过当前局部修正能力；未生成候选，可查看限制和原动作位置。';
  if(job.reason_code==='motion_import_interrupted')detail=`上次${operation}因服务中断未完成；重新执行会创建新任务，保留旧记录。`;
  if(job.kind==='generate'&&job.status==='interrupted')detail=(detail||'生成中断，旧记录保留。')+' Kimodo 将从生成起点重新运行，不是模型断点续算。';
  return {state,detail};
}
