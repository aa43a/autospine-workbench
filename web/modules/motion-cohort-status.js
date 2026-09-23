const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const visualLabels={accepted:'阶段接受',accepted_with_exceptions:'阶段接受，保留异常',rejected:'需调整',revoked:'已撤销'};
export function createCohortStatus(parent,pack,onSelect){
  const section=node('section');section.setAttribute('aria-label','固定集状态');
  const title=node('h2','固定集状态与异常');
  const refresh=node('button','核对全部候选状态'),stop=node('button','停止核对');stop.disabled=true;
  const label=node('label'),filter=node('input');filter.type='checkbox';label.append(filter,'仅显示异常或未验收');
  const summary=node('p');summary.setAttribute('role','status');
  const note=node('p','点击核对可更新状态快照；读取现有检查与验收记录，不重新捕获动画，不自动接受。阶段接受不会清除技术异常；未读取或读取失败保留在总数中。');
  const scroll=node('div');scroll.style.cssText='overflow:auto;max-height:360px';const table=node('table');table.style.width='100%';
  const head=node('thead'),headRow=node('tr');
  for(const text of ['动作 / 角色','技术检查','阶段视觉','操作'])headRow.append(node('th',text));
  head.append(headRow);const body=node('tbody');table.append(head,body);scroll.append(table);
  section.append(title,refresh,stop,label,summary,note,scroll);parent.append(section);
  let generation=0,controller;
  const rows=pack.groups.flatMap((g,mi)=>g.targets.map((t,ci)=>({g,t,mi,ci,status:'unread',visual:'未读取'})));
  const missing=pack.coverage?.missing||[];
  function render(){
    body.replaceChildren();let read=0,technical=0,accepted=0,historical=0;
    for(const row of rows){
      const pass=row.status==='stage_review',ok=row.applies&&['accepted','accepted_with_exceptions'].includes(row.decision);
      read+=Boolean(row.loaded);technical+=pass;accepted+=Boolean(ok);
      historical+=Boolean(row.loaded&&['accepted','accepted_with_exceptions'].includes(row.decision));
      if(filter.checked&&pass&&ok)continue;
      const tr=node('tr');tr.append(node('td',row.g.label+' / '+row.t.label));
      tr.append(node('td',row.error||({unread:'未读取',loading:'正在核对',stage_review:'已实施技术检查通过',needs_changes:'存在技术异常',evidence_incomplete:'技术证据不完整'})[row.status]||'技术状态未知'));
      tr.append(node('td',row.visual));const action=node('td'),open=node('button','检查此项');
      open.onclick=()=>onSelect(row.mi,row.ci);action.append(open);tr.append(action);body.append(tr);
    }
    for(const row of missing){const tr=node('tr');tr.append(node('td',row.motion+' / '+row.character),node('td','未生成可复核候选：'+row.status),node('td','未验收'),node('td','在动作中心处理来源或构建任务'));body.append(tr);}
    const total=rows.length+missing.length;
    summary.textContent=`已读取 ${read}/${rows.length} 个可复核候选；技术通过 ${technical}/${total}；有效阶段接受 ${accepted}/${total}；历史阶段接受 ${historical} 项。${pack.coverage?'固定集共 '+total+' 项。':'此清单未声明缺失项目，以上仅统计列出的候选。'}`;
  }
  async function get(path,signal){const response=await fetch(path,{cache:'no-store',signal});const value=await response.json();if(!response.ok)throw Error(value.reason_code||'读取失败');return value;}
  refresh.onclick=async()=>{
    const token=++generation;controller?.abort();controller=new AbortController();const signal=controller.signal;
    refresh.disabled=true;stop.disabled=false;
    for(const row of rows)Object.assign(row,{status:'unread',visual:'未读取',loaded:false,applies:false,decision:null,error:null});render();
    let cursor=0;const sourceChecks=new Map();
    async function worker(){while(cursor<rows.length&&!signal.aborted){
      const row=rows[cursor++],version=row.version;row.status='loading';render();
      try{
        if(!sourceChecks.has(row.g.job_id))sourceChecks.set(row.g.job_id,get('/api/motions/'+row.g.job_id,signal));
        const source=await sourceChecks.get(row.g.job_id);
        if(source.status!=='succeeded'||source.source_sha256!==row.g.source_sha256)throw Error('来源身份已变化');
        const job=await get('/api/motions/'+row.t.job_id,signal);
        if(job.kind!=='adapt'||job.status!=='succeeded'||job.result?.artifact_sha256!==row.t.artifact_sha256)throw Error('候选身份已变化');
        const review=await get('/api/motions/'+row.t.job_id+'/stage-review',signal);
        if(review.artifact_sha256!==row.t.artifact_sha256||review.readiness?.artifact_sha256!==row.t.artifact_sha256)throw Error('检查身份不匹配');
        if(token!==generation)return;
        if(row.version!==version)continue;
        Object.assign(row,{loaded:true,status:review.readiness.status,applies:review.current_applies===true,decision:review.current?.decision});
        row.visual=review.current?(row.applies?(visualLabels[row.decision]||'未知结论'):`历史：${visualLabels[row.decision]||'未知结论'}；旧结论已过期，需复核`):'尚未验收';
      }catch(error){if(token!==generation)return;if(row.version!==version)continue;row.status='error';row.error='无法核对：'+error.message;row.visual='尚未核实';}
      render();
    }}
    try{await Promise.all([worker(),worker()]);}
    finally{if(token===generation){refresh.disabled=false;stop.disabled=true;render();}}
  };
  stop.onclick=()=>{generation++;controller?.abort();for(const row of rows)if(row.status==='loading'){row.status='unread';row.visual='未读取';}refresh.disabled=false;stop.disabled=true;render();};
  window.addEventListener('motion-stage-review-saved',event=>{
    const row=rows.find(r=>r.t.job_id===event.detail?.jobId);if(!row)return;
    Object.assign(row,{version:(row.version||0)+1,loaded:false,status:'unread',applies:false,decision:null,error:null,visual:'结论已更新，请重新核对'});render();
  });
  filter.onchange=render;
  window.addEventListener('pagehide',()=>{generation++;controller?.abort();},{once:true});render();
}
