import {createSessionDrafts} from './workbench-work-session-draft.js';
export function createWorkSessions(document,hooks){
 const node=(tag,text='')=>{const e=document.createElement(tag);e.textContent=text;return e;};
 const element=node('details'),summary=node('summary','项目人工工作计时 · 未开始'),stage=node('select'),start=node('button','开始本阶段计时'),stop=node('button','暂停并保存'),refresh=node('button','刷新记录'),status=node('p'),rows=node('div');
 const stages={source_preparation:'来源准备',joints:'关节调整',bindings:'绑定修改',sleeves:'袖装标注',visual_review:'整角色验收',auto_audit:'自动绑定抽查',other:'其他处理'};
 element.style='padding:12px 24px;border-bottom:1px solid #344454';
 for(const [value,label]of Object.entries(stages)){const option=node('option',label);option.value=value;stage.append(option);}stage.value='joints';stage.setAttribute('aria-label','工作计时阶段');
 for(const b of [start,stop,refresh]){b.type='button';b.className='button button-secondary';}
 element.append(summary,node('p','显式记录导入后的人工操作段，离开工作时请暂停。同一标签页刷新可恢复计时草稿，恢复后保持暂停，点击“暂停并保存”提交；关闭标签页可能丢失草稿。不包含未计时工作，不与局部复核计时相加。'),stage,start,stop,refresh,status,rows);
 let project=null,report=null,running=null,pending=null,busy=false,generation=0;
 const drafts=new Map(),clock=hooks.clock||(()=>Date.now()),discard=node('button','放弃未保存计时');discard.type='button';discard.className='button button-secondary';element.append(discard);
 const host=document.defaultView;let storage;try{storage=hooks.storage??host?.sessionStorage;}catch{}
 const savedDrafts=createSessionDrafts(storage),warning=node('p');element.append(warning);
 function checkpoint(){if(!project)return;const end=clock(),draft=pending||(running?{...running,ended_at:new Date(end).toISOString(),seconds:(end-Date.parse(running.started_at))/1000}:null);
  const saved=savedDrafts.write(project,draft);warning.textContent=draft&&!saved?'浏览器未能暂存计时草稿，请在离开页面前暂停并保存。':'';
 }
 const onPageHide=()=>{pause();checkpoint();};host?.addEventListener('pagehide',onPageHide);
 const onPageShow=()=>render();host?.addEventListener('pageshow',onPageShow);
 const timer=host?.setInterval(()=>{if(running)checkpoint();},5000);
 discard.onclick=()=>{if(!busy&&!running){pending=null;status.textContent='已放弃未保存计时，服务器记录保留。';render();}};
 function pause(){if(running){const end=clock();pending={...running,ended_at:new Date(end).toISOString(),seconds:(end-Date.parse(running.started_at))/1000};running=null;}}
 function render(){element.hidden=!project;discard.hidden=!pending;discard.disabled=busy;stage.disabled=busy||Boolean(running||pending);start.disabled=busy||!report||Boolean(running||pending);stop.disabled=busy||(!running&&!pending);refresh.disabled=busy||Boolean(running);
  checkpoint();
  summary.textContent=`项目人工工作计时 · ${running?'计时中：'+stages[running.stage]:pending?'有未保存计时':'已暂停'}`;
  rows.replaceChildren(...(report?.sessions||[]).map(row=>{const item=node('p',`${stages[row.stage]} · ${(row.seconds/60).toFixed(2)} 分钟 · ${row.started_at} `),undo=node('button','撤销此记录');undo.type='button';undo.className='button button-secondary';undo.disabled=busy||Boolean(running||pending);undo.onclick=()=>void request('revoke',row.session_id);item.append(undo);return item;}));
 }
 async function request(action=null,payload=null){
  if(!project||busy)return;const token=generation,id=project;busy=true;render();
  try{const result=await hooks.apiRequest(`/api/projects/${encodeURIComponent(id)}/automation/character/work-sessions`,action?{method:'POST',headers:{'X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify({expected_head_sha256:report.head_sha256,expected_source_sha256:pending?.source||report.source_sha256,action,payload})}:{cache:'no-store'});
   if(token!==generation)return;
   if(result.project_id!==id||result.authority!=='none')throw Error('source');report=result;
   if(!action&&pending&&report.sessions.some(s=>s.session_id===pending.session_id&&s.source_sha256===pending.source&&['stage','started_at','ended_at','seconds','method'].every(k=>s[k]===pending[k])))pending=null;
   if(action==='record')pending=null;
   status.textContent=`已记录 ${report.sessions.length} 段，合计 ${report.metrics.recorded_minutes===null?'未测量':report.metrics.recorded_minutes.toFixed(2)+' 分钟'}。完整流程总耗时仍未知。`;
  }catch(e){if(token===generation)status.textContent='未保存或读取失败。计时草稿保留；刷新记录后可重试。来源变化或重叠计时会被拒绝。';}
  finally{if(token===generation){busy=false;render();}}
 }
 start.onclick=()=>{if(!report||busy||running||pending)return;running={source:report.source_sha256,session_id:crypto.randomUUID().replaceAll('-',''),stage:stage.value,started_at:new Date(clock()).toISOString(),method:'operator_stopwatch_segment_v1'};render();};
 stop.onclick=()=>{pause();if(!pending||pending.seconds<=0)return;const payload={...pending};delete payload.source;pending.source??=report.source_sha256;void request('record',payload);};
 refresh.onclick=()=>void request();
 return {element,sync(){const id=hooks.context().projectId;if(id!==project){pause();checkpoint();if(project&&pending)drafts.set(project,pending);generation++;project=id;pending=drafts.get(id)||savedDrafts.read(id);drafts.delete(id);report=null;busy=false;status.textContent='正在读取项目计时…';if(project)void request();}render();},dispose(){pause();checkpoint();generation++;host?.removeEventListener('pagehide',onPageHide);host?.removeEventListener('pageshow',onPageShow);if(timer!==undefined)host.clearInterval(timer);}};
}
