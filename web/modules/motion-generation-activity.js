const seconds=value=>Number.isSafeInteger(value)&&value>=0;
function duration(value){return value<60?`${value} 秒`:`${Math.floor(value/60)} 分 ${value%60} 秒`;}
export function generationActivity(job){
  if(job.kind!=='generate'||job.status!=='running')return null;
  const a=job.activity;
  if(!a||a.meaning!=='observed_activity_not_completion_or_health')return '正在等待生成任务活动记录。';
  const stage=seconds(a.stage_elapsed_seconds)?`当前阶段已持续 ${duration(a.stage_elapsed_seconds)}`:'当前阶段时长尚不可用';
  const output=seconds(a.log_bytes)&&seconds(a.log_age_seconds)
    ? `已输出 ${(a.log_bytes/1024).toFixed(1)} KB 日志，${duration(a.log_age_seconds)}前更新`
    : '尚未获得生成日志更新';
  return `${stage}；${output}。模型加载期间可能暂时没有输出；这不是完成百分比，也不代表任务失败。`;
}
