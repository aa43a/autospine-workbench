import {deliveryLabels,deliveryState,deliveryCounts} from './motion-cohort-delivery.js';
import {readRelatedSummary,relatedCounts} from './motion-related-summary.js';
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const visualLabels={accepted:'阶段接受',accepted_with_exceptions:'阶段接受，保留异常',rejected:'需调整',revoked:'已撤销'};
export function createCohortStatus(parent,pack,onSelect){
  const section=node('section');section.setAttribute('aria-label','固定集状态');
  const title=node('h2','固定集状态与异常');
  const refresh=node('button','核对全部候选状态'),stop=node('button','停止核对');stop.disabled=true;
  const label=node('label'),filter=node('input');filter.type='checkbox';label.append(filter,'仅显示异常或未验收');
  const relatedLabel=node('label'),relatedFilter=node('input');relatedFilter.type='checkbox';relatedLabel.append(relatedFilter,'仅显示已发现的改进结果');
  const stageLabel=node('label','按检查阶段筛选 '),stageFilter=node('select');stageFilter.setAttribute('aria-label','按检查阶段筛选');
  for(const stage of ['', '投影','几何','接触','遮挡','Runtime']){const option=node('option',stage||'全部阶段');option.value=stage;stageFilter.append(option);}stageLabel.append(stageFilter);
  const summary=node('p');summary.setAttribute('role','status');
  const deliverySummary=node('p');deliverySummary.setAttribute('aria-label','交付状态统计');
  const relatedStatus=node('p');relatedStatus.setAttribute('aria-label','关联改进结果统计');
  const deliveryLabel=node('label','按交付状态筛选 '),deliveryFilter=node('select');deliveryFilter.setAttribute('aria-label','按交付状态筛选');
  for(const [value,text] of [['','全部状态'],...Object.entries(deliveryLabels)]){const option=node('option',text);option.value=value;deliveryFilter.append(option);}deliveryLabel.append(deliveryFilter);
  const note=node('p','点击核对可更新状态快照；读取现有检查与验收记录，不重新捕获动画，不自动接受。阶段接受不会清除技术异常；未读取或读取失败保留在总数中。');
  const scroll=node('div');scroll.style.cssText='overflow:auto;max-height:360px';const table=node('table');table.style.width='100%';
  const head=node('thead'),headRow=node('tr');
  for(const text of ['动作 / 角色','交付状态','技术检查','阶段视觉','关联改进结果','操作'])headRow.append(node('th',text));
  head.append(headRow);const body=node('tbody');table.append(head,body);scroll.append(table);
  note.append(' 阶段筛选显示该项未通过的候选；缺失或无法核实的记录始终保留，统计不随筛选改变。');
  note.append(' 交付状态互斥计数；技术异常优先，阶段接受不代表发布授权。');
  note.append(' 关联改进结果单独展示；局部阶段接受不替换旧候选，也不计入固定集通过数量。');
  const controls=node('nav');controls.setAttribute('aria-label','固定集筛选与核对');
  controls.append(refresh,stop,label,relatedLabel,stageLabel,deliveryLabel);
  section.append(title,controls,summary,deliverySummary,relatedStatus,note,scroll);parent.append(section);
  let generation=0,controller;
  const rows=pack.groups.flatMap((g,mi)=>g.targets.map((t,ci)=>({g,t,mi,ci,status:'unread',visual:'未读取'})));
  const missing=pack.coverage?.missing||[];
  function render(){
    body.replaceChildren();let read=0,technical=0,accepted=0,historical=0;
    for(const row of rows){
      const pass=row.status==='stage_review',ok=row.applies&&['accepted','accepted_with_exceptions'].includes(row.decision);
      read+=Boolean(row.loaded);technical+=pass;accepted+=Boolean(ok);
      historical+=Boolean(row.loaded&&['accepted','accepted_with_exceptions'].includes(row.decision));
      const delivery=deliveryState(row);
      if(relatedFilter.checked&&!(row.related?.status==='loaded'&&row.related.rows.length))continue;
      if(deliveryFilter.value&&deliveryFilter.value!==delivery)continue;
      if(filter.checked&&pass&&ok)continue;
      const selectedStage=row.stages?.find(s=>s.stage===stageFilter.value);
      if(stageFilter.value&&selectedStage?.status==='sampled_pass')continue;
      const tr=node('tr');tr.append(node('td',row.g.label+' / '+row.t.label));
      tr.append(node('td',deliveryLabels[delivery]));
      const technicalCell=node('td',row.error||({unread:'未读取',loading:'正在核对',stage_review:'已实施技术检查通过',needs_changes:'存在技术异常',evidence_incomplete:'技术证据不完整'})[row.status]||'技术状态未知');
      for(const stage of row.stages||[]){
        const detail=node('details'),caption=node('summary',`${stage.stage}：${({sampled_pass:'限定采样通过',needs_changes:'需处理',unmeasured:'尚未验证'})[stage.status]||'状态未知'}`);
        detail.append(caption,node('p',stage.explanation||'未提供说明'));technicalCell.append(detail);
      }
      if(row.loaded&&!row.stages?.length)technicalCell.append(node('p','未提供分阶段证据'));
      tr.append(technicalCell);
      tr.append(node('td',row.visual));
      const relatedCell=node('td');
      if(row.related?.status==='loaded'){
        if(!row.related.rows.length)relatedCell.textContent='暂无已关联改进结果';
        for(const candidate of row.related.rows){
          const link=node('a',`播放改进版 ${candidate.artifact.slice(0,10)}`);
          link.href=`/api/motions/${row.t.job_id}/view/related-candidates/${candidate.registration}/player.html`;
          link.target='_blank';link.rel='noopener';
          relatedCell.append(link,node('p',candidate.visual+'；具体范围及异常见本项对照面板'));
        }
      }else relatedCell.textContent=row.related?.message||'未核对';
      tr.append(relatedCell);const action=node('td'),open=node('button','检查此项');
      open.onclick=()=>onSelect(row.mi,row.ci);action.append(open);tr.append(action);body.append(tr);
    }
    if(!relatedFilter.checked&&(!deliveryFilter.value||deliveryFilter.value==='missing'))for(const row of missing){const tr=node('tr');tr.append(node('td',row.motion+' / '+row.character),node('td',deliveryLabels.missing),node('td','未生成可复核候选：'+row.status),node('td','未验收'),node('td','无可关联基线'),node('td','在动作中心处理来源或构建任务'));body.append(tr);}
    const total=rows.length+missing.length;
    deliverySummary.textContent=Object.entries(deliveryCounts(rows,missing.length)).map(([key,count])=>`${deliveryLabels[key]} ${count}/${total}`).join('；');
    const related=relatedCounts(rows);
    relatedStatus.textContent=`关联记录已核对 ${related.checked}/${rows.length} 项；其中 ${related.available} 项有改进结果。独立统计，不改变固定集验收结论。`;
    summary.textContent=`已读取 ${read}/${rows.length} 个可复核候选；技术通过 ${technical}/${total}；有效阶段接受 ${accepted}/${total}；历史阶段接受 ${historical} 项。${pack.coverage?'固定集共 '+total+' 项。':'此清单未声明缺失项目，以上仅统计列出的候选。'}`;
  }
  async function get(path,signal){const response=await fetch(path,{cache:'no-store',signal});const value=await response.json();if(!response.ok)throw Error(value.reason_code||'读取失败');return value;}
  refresh.onclick=async()=>{
    const token=++generation;controller?.abort();controller=new AbortController();const signal=controller.signal;
    refresh.disabled=true;stop.disabled=false;
    for(const row of rows)Object.assign(row,{status:'unread',visual:'未读取',loaded:false,applies:false,decision:null,error:null,stages:null,related:null});render();
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
        Object.assign(row,{loaded:true,status:review.readiness.status,stages:Array.isArray(review.readiness.stages)?review.readiness.stages:[],applies:review.current_applies===true,decision:review.current?.decision});
        row.visual=review.current?(row.applies?(visualLabels[row.decision]||'未知结论'):`历史：${visualLabels[row.decision]||'未知结论'}；旧结论已过期，需复核`):'尚未验收';
        if(review.evidence_match==='legacy_empty_projection_fields')row.visual+='（仅新增空字段，原确认保留）';
        render();
        const related=await readRelatedSummary(get,row.t.job_id,row.t.artifact_sha256,signal);
        if(token!==generation)return;
        if(row.version!==version)continue;
        row.related=related;
      }catch(error){if(token!==generation)return;if(row.version!==version)continue;row.status='error';row.error='无法核对：'+error.message;row.visual='尚未核实';}
      render();
    }}
    try{await Promise.all([worker(),worker()]);}
    finally{if(token===generation){refresh.disabled=false;stop.disabled=true;render();}}
  };
  stop.onclick=()=>{generation++;controller?.abort();for(const row of rows)if(row.status==='loading'){row.status='unread';row.visual='未读取';}refresh.disabled=false;stop.disabled=true;render();};
  window.addEventListener('motion-stage-review-saved',event=>{
    const row=rows.find(r=>r.t.job_id===event.detail?.jobId);if(!row)return;
    Object.assign(row,{version:(row.version||0)+1,loaded:false,status:'unread',applies:false,decision:null,error:null,stages:null,visual:'结论已更新，请重新核对'});render();
  });
  filter.onchange=render;
  relatedFilter.onchange=render;
  stageFilter.onchange=render;
  deliveryFilter.onchange=render;
  window.addEventListener('pagehide',()=>{generation++;controller?.abort();},{once:true});render();
}
