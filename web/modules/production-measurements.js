import {createWorkSessions} from './workbench-work-sessions.js';
function el(tag,text){const e=document.createElement(tag);e.textContent=text;return e;}
export function createProductionMeasurements(api){
  const panel=document.getElementById('measurements'),summary=el('div','');let current=null,key=null;
  let storage;try{storage=localStorage;}catch{}
  const timer=createWorkSessions(document,{context:()=>({projectId:current?.run_id}),storage,
    scopeLabel:'本次制作',pauseWhenHidden:true,
    description:'仅记录你主动开始的操作时间。切换任务、离开页面或隐藏标签页会暂停，刷新后可恢复未提交草稿。请在离开工作时暂停；不会把构建等待、历史操作或其他任务时间补算为人工耗时。',
    apiRequest:async(url,options)=>{
      const run=decodeURIComponent(url.split('/')[3]);
      const result=await api(`/api/production/${run}/work-sessions`,options?.method==='POST'?JSON.parse(options.body):undefined);
      if(options?.method==='POST')void load(current);
      return result;
    }});
  const refresh=el('button','刷新耗时统计');refresh.onclick=()=>load(current);
  panel.append(el('h2','操作与流程耗时'),refresh,summary,timer.element);
  async function load(run){if(!run)return;const id=run.run_id;
    try{const value=await api(`/api/production/${id}/metrics`);if(current?.run_id!==id)return;
      const minutes=value.human.recorded_minutes;
      summary.replaceChildren(el('p',`本次已记录人工操作：${minutes===null?'尚未计时':minutes.toFixed(2)+' 分钟'}；完整人工耗时未知。`),
        el('p',`任务经过 ${(value.task_elapsed_seconds/60).toFixed(1)} 分钟（含排队和等待，不含之前的上传）。阻塞记录 ${value.blocked_observations} 项，重试请求 ${value.retry_requests} 次；这些次数不等于人工干预次数。`));
      summary.append(el('p',`已记录自动执行：${value.recorded_execution_seconds===null?'未测量':(value.recorded_execution_seconds/60).toFixed(2)+' 分钟'}，覆盖 ${value.execution_measured_attempts} 次尝试，另 ${value.execution_unmeasured_attempts} 次缺测。包含执行中的读写与捕获，不代表 CPU 用时。`));
      if(value.stages_without_observed_intervals?.length)summary.append(el('p',`未记录独立执行时段：${value.stages_without_observed_intervals.map(s=>({source:'来源准备',bindings:'默认绑定',character:'整角色',body:'身体动作',joint:'联合动画'})[s]).join('、')}。已有结果复用和缺测均不补算执行耗时。`));
      else summary.append(el('p','未列出的步骤和已有结果复用不补算执行耗时；以上记录不代表全流程计时完整。'));
      const details=el('details','');details.append(el('summary','查看自动步骤的观测时段'));
      details.append(el('p','以下为子任务预留到观测完成的时间，包含排队或服务中断。纯计算时间、等待时间尚未独立测量。'));
      for(const row of value.observed_child_intervals)details.append(el('p',`${({body:'身体动作',joint:'联合动画',character:'整角色'})[row.stage]||row.stage} · 观测 ${(row.seconds/60).toFixed(2)} 分钟 · 执行 ${row.execution_seconds===null?'缺测':(row.execution_seconds/60).toFixed(2)+' 分钟'} · ${row.status}`));
      summary.append(details);
    }catch(e){if(current?.run_id===id)summary.textContent=`读取耗时失败：${e.message}`;}
  }
  return run=>{current=run;panel.hidden=!run;timer.sync();const next=run?run.run_id+':'+run.revision:null;if(next!==key){key=next;void load(run);}};
}
