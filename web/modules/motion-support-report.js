import {deliveryState,deliveryCounts,deliveryLabels} from './motion-cohort-delivery.js';
import {supportExceptions} from './motion-support-exceptions.js';
import {sourceScope} from './motion-source-scope.js';
import {depthCoverageText} from './motion-depth-coverage.js';
import {independentAcceptance,independentAcceptedEntries} from './motion-support-acceptance.js';
import {stageLocationsHTML} from './motion-support-locations.js';
const gates=['投影','几何','接触','遮挡','Runtime'];
const statuses={sampled_pass:'采样通过',needs_changes:'需处理',unmeasured:'未验证'};
const decisions={accepted:'阶段接受',accepted_with_exceptions:'阶段接受，保留异常',rejected:'需调整',revoked:'已撤销',
  stage_accepted_with_retained_exceptions:'限定范围阶段接受，保留异常'};
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const effectiveStatus=row=>{
  const report=row.review?.readiness;
  if(report?.status!=='stage_review')return report?.status;
  if(report.stages.some(s=>s.status==='needs_changes'))return 'needs_changes';
  if(gates.some(name=>!report.stages.some(s=>s.stage===name&&s.status==='sampled_pass'))
      ||report.stages.some(s=>s.status!=='sampled_pass'))return 'evidence_incomplete';
  return 'stage_review';
};
const state=row=>({loaded:row.status==='verified',status:effectiveStatus(row),
  applies:row.review?.current_applies===true,decision:row.review?.current?.decision});
export function supportTotals(snapshot){
  const rows=snapshot.rows,missing=snapshot.missing.length;
  return {expected:snapshot.expected,verified:rows.filter(r=>r.status==='verified').length,
    independent_acceptance:independentAcceptance(snapshot),
    accepted:rows.filter(r=>r.status==='verified'&&r.review.current_applies&&['accepted','accepted_with_exceptions'].includes(r.review.current?.decision)).length,
    delivery:deliveryCounts(rows.map(state),missing),
    gates:Object.fromEntries(gates.map(name=>[name,Object.fromEntries(Object.keys(statuses).map(status=>[status,
      rows.filter(r=>{const s=r.status==='verified'?r.review.readiness.stages.find(s=>s.stage===name)?.status:null;
        return (s in statuses?s:'unmeasured')===status;}).length+(status==='unmeasured'?missing:0)]))])),
    related_checked:rows.filter(r=>r.related?.status==='verified'&&r.related.complete).length,
    alternatives_checked:rows.filter(r=>r.alternatives?.status==='verified'&&r.alternatives.complete).length,
    policies_checked:rows.filter(r=>r.policy_variants?.status==='verified'&&r.policy_variants.complete).length};
}
function reviewHTML(row,base,path){
  const review=row.review;if(row.status!=='verified'||!review)return `<p>未核实：${escape(row.reason||'未读取')}</p>`;
  const current=review.current,imported=!current&&review.imported_visual;
  let visual='尚无阶段结论';
  if(current)visual=(review.current_applies?'':'历史结论（当前证据不适用）：')+(decisions[current.decision]||'未知结论');
  else if(imported)visual='独立导入记录：'+(decisions[imported.decision]||imported.decision);
  const notes=current?.notes??imported?.notes??imported?.user_response??'';
  return `<p><strong>${escape(visual)}</strong></p><p class="notes">${escape(typeof notes==='string'?notes:JSON.stringify(notes))}</p>`+
    (imported?`<p>导入记录范围：${escape(imported.scope)}；保留异常：${escape((imported.retained_exceptions||[]).join('、'))}</p>`:'')+
    `<ul>${review.readiness.stages.map(s=>`<li>${escape(s.stage)}：${escape(statuses[s.status]||'未知')} — ${escape(s.explanation)}${stageLocationsHTML(s,base,path)}</li>`).join('')}</ul>`+
    `<details><summary>身份与验收范围</summary><p>证据 ${escape(review.evidence_sha256)}；验收版本 ${review.revision}；匹配 ${escape(review.evidence_match)}</p>`+
    `<p>核对时间 ${escape(row.checked_at)}${row.review_checked_at?`；同证据验收复查 ${escape(row.review_checked_at)}`:''}</p></details>`;
}
function link(base,path,label){return `<a href="${escape(base+path)}" target="_blank" rel="noopener">${escape(label)}</a>`;}
function depthHTML(row,base,path){
  const depth=row.evidence?.depth_diagnostics;
  if(row.status!=='verified'||!depth)return '';
  return `<details><summary>补充遮挡诊断 · ${depth.failures.length} 条失败记录</summary>`+
    '<p>来源深度与局部像素重叠检查，不代表整帧渲染验收；不改写历史检查或阶段结论。</p>'+
    `<p>${escape(depthCoverageText(depth))}</p>`+
    `<p>诊断证据 ${escape(depth.audit_sha256)}</p>`+
    (depth.failures.length?'<ul>'+depth.failures.map(r=>`<li>${link(base,path+'?time='+encodeURIComponent(r.time),Number(r.time).toFixed(3)+' 秒')} · ${escape(r.location_kind==='order_cycle'?r.conflict_slots.join(' → '):r.pair.join(' / '))} · ${escape(r.reason_code)}</li>`).join('')+'</ul>':
      '<p>本诊断未列出冲突，完整遮挡检查仍以技术状态为准。</p>')+'</details>';
}
function scopeHTML(snapshot,row){
  const s=sourceScope(snapshot.plan_sha256,row);
  return s?`<p><strong>本次源动作内容：</strong>${escape(s.observed)} ${escape(s.limits)}<br>来自六时刻骨架观察，不是人工验收或完整动作类别证明。</p>`:'';
}
function familyHTML(family,kind,job,base,anchor){
  if(family?.status!=='verified')return `<p>未核实：${escape(family?.reason||'未读取')}</p>`;
  const partial=!family.complete?'<p>清单或证据不完整；未返回、未核实的候选不计通过。</p>':'';
  return partial+(family.rows.length?family.rows.map((r,i)=>{
    const path=kind==='related'?`/api/motions/${job}/view/related-candidates/${r.registration_sha256}/player.html`:`/api/motions/${r.job_id}/view/player.html`;
    const title=kind==='related'?'独立改进候选':kind==='policy'?'不同处理策略候选':`替代视角 ${r.view||''} ${r.projection?JSON.stringify(r.projection):''}`;
    return `<details id="${escape(anchor)}-${i}"><summary>${escape(title)} · ${escape(r.artifact_sha256?.slice(0,12)||r.job_id)}</summary>`+
      `<p>候选 ${escape(r.artifact_sha256)}${r.registration_sha256?'；关联 '+escape(r.registration_sha256):''}</p>`+
      (kind==='policy'?`<p>相对固定候选的策略变化：${escape(JSON.stringify(r.policy_changes))}。独立检查，不参与视角推荐。</p>`:'')+
      (r.status==='verified'?link(base,path,'打开该候选'):'')+reviewHTML(r,base,path)+depthHTML(r,base,path)+
      (r.source_link?`<p>源区间 ${r.source_link.source_start}–${r.source_link.source_end} 秒；来源 ${escape(r.source_link.source_job_id)}</p>`:'')+
      (kind!=='related'&&r.related?`<h4>此候选的独立改进</h4>${familyHTML(r.related,'related',r.job_id,base,`${anchor}-${i}-related`)}`:'')+'</details>';
  }).join(''):'<p>当前查询未发现独立候选。</p>');
}
export function supportReportHTML(snapshot,origin){
  const acceptedEntries=independentAcceptedEntries(snapshot);
  const acceptedLinks=cell=>{
    const entries=acceptedEntries.filter(r=>r.cell===cell);
    return entries.length?entries.map((r,i)=>{
      const path=r.registration_sha256?`/api/motions/${r.job_id}/view/related-candidates/${r.registration_sha256}/player.html`:
        `/api/motions/${r.job_id}/view/player.html`;
      return link(base,path,`播放已接受候选 ${i+1}`)+` · <a href="#${escape(r.anchor)}">范围与异常</a>`;
    }).join('<br>'):'暂无有效独立阶段接受';
  };
  const url=new URL(origin);if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('工作台地址无效');
  const base=url.origin,totals=supportTotals(snapshot);
  const exceptions=supportExceptions(snapshot);
  const queue=`<section id="exceptions"><h2>待处理异常与验收</h2><p>共 ${exceptions.length} 条检查事项，同一候选可能有多条。此数量不是失败角色数或错误率。独立候选单列；技术异常不会因阶段接受消失。先处理技术与证据问题，再对实际候选做阶段验收。</p>`+
    ['technical','evidence','visual'].map(kind=>{const items=exceptions.filter(r=>r.kind===kind);
      return `<details${kind==='technical'?' open':''}><summary>${{technical:'技术异常',evidence:'证据缺失或待核实',visual:'阶段结论待处理'}[kind]} · ${items.length}</summary><ul>`+
        items.map(r=>`<li>${r.anchor?`<a href="#${escape(r.anchor)}">定位</a> · `:''}${escape(r.motion)} / ${escape(r.character)} · ${escape(r.family)} · ${escape(r.artifact_sha256?.slice(0,12)||'未确定候选')} · <strong>${escape(r.stage)}</strong>：${escape(r.reason)}</li>`).join('')+'</ul></details>';
    }).join('')+'</section>';
  const cards=snapshot.rows.map((r,i)=>`<section id="cell-${i}"><h2>${escape(r.motion)} / ${escape(r.character)}</h2>`+
    scopeHTML(snapshot,r)+
    `<p>固定候选 ${escape(r.artifact_sha256)}；任务 ${escape(r.job_id)}</p>`+
    `<p>来源 ${escape(r.source_job_id)}；源文件 ${escape(r.source_sha256)}</p>`+
    (r.source_link?`<p>源区间 ${r.source_link.source_start}–${r.source_link.source_end} 秒 · ${r.source_link.source_fps} FPS</p>`:'')+
    (r.status==='verified'?link(base,`/api/motions/${r.job_id}/view/player.html`,'播放固定候选')+' · '+link(base,`/api/motions/${r.job_id}/download`,'下载固定候选'):'')+
    reviewHTML(r,base,`/api/motions/${r.job_id}/view/player.html`)+`<h3>独立改进结果</h3>${familyHTML(r.related,'related',r.job_id,base,`cell-${i}-related`)}`+
    `<h3>独立替代视角</h3>${familyHTML(r.alternatives,'alternative',r.job_id,base,`cell-${i}-alternatives`)}`+
    `<h3>不同处理策略</h3>${familyHTML(r.policy_variants,'policy',r.job_id,base,`cell-${i}-policy_variants`)}</section>`).join('');
  const table=snapshot.rows.map((r,i)=>`<tr><td><a href="#cell-${i}">${escape(r.motion)} / ${escape(r.character)}</a></td>`+
    `<td>${escape(deliveryLabels[deliveryState(state(r))])}</td><td>${r.status==='verified'?escape(r.review.current_applies?decisions[r.review.current?.decision]||'尚无有效阶段结论':'尚无有效阶段结论'):'未核实'}</td>`+
    `<td>${acceptedLinks(i)}</td>`+
    gates.map(name=>{const status=r.status==='verified'?r.review.readiness.stages.find(s=>s.stage===name)?.status:null;return `<td>${statuses[status]||'未验证'}</td>`;}).join('')+'</tr>').join('')+
    snapshot.missing.map(r=>`<tr><td>${escape(r.motion)} / ${escape(r.character)}</td><td>缺少候选</td><td colspan="7">${escape(r.status)}</td></tr>`).join('');
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>M4 支持范围核对</title>
<style>body{font:16px system-ui;background:#101923;color:#e1e9f1;margin:24px;line-height:1.6}a{color:#75d6ff}table{border-collapse:collapse;width:100%}td,th{border:1px solid #42556a;padding:8px;text-align:left}section{margin:28px 0;padding:20px;background:#192735;overflow-wrap:anywhere}details{margin:12px 0}summary{cursor:pointer}.notes{white-space:pre-wrap}.scroll{overflow:auto}</style>
<h1>M4 支持范围核对</h1><p>固定清单 ${escape(snapshot.plan_sha256)}</p><p>读取时间：${escape(snapshot.started_at)} 至 ${escape(snapshot.finished_at)}</p>
<p>这是已有证据的逐项读取快照，不是同时刻事务，也未重新捕获动画。${snapshot.coverage_declared?'包含清单声明的全部组合。':'清单未声明完整覆盖，仅统计列出项。'}
仅适用于记录的来源、角色版本、视角和片段。阶段接受不会清除技术失败；独立候选不替换固定候选，不计入其通过率。未登记到工作台的本地实验不在本报告清单内。本报告不授予发布权限。详细失败采样与原始验收记录见配套 JSON。</p>
<p>身份已核对 ${totals.verified}/${totals.expected}；有效阶段接受 ${totals.accepted}/${totals.expected}；改进记录完整核对 ${totals.related_checked}/${snapshot.rows.length}；替代记录完整核对 ${totals.alternatives_checked}/${snapshot.rows.length}；不同策略清单完整核对 ${totals.policies_checked}/${snapshot.rows.length}。</p>
<p>另有 ${totals.independent_acceptance.accepted} 个独立候选获有效阶段接受（按候选及注册身份去重）；${totals.independent_acceptance.conflicting} 个重复记录结论不一致，未计入接受。此数不加入固定候选通过率，不包含仅局部反馈，技术异常仍保留。</p>
<p>${Object.entries(totals.delivery).map(([k,v])=>`${deliveryLabels[k]} ${v}/${totals.expected}`).join('；')}</p>
${queue}<div class="scroll"><table><thead><tr><th>动作 / 角色</th><th>固定候选交付状态</th><th>固定候选阶段验收</th><th>已接受的独立结果（保留异常）</th>${gates.map(n=>`<th>${n}</th>`).join('')}</tr></thead><tbody>${table}</tbody></table></div>${cards}
<script>
function revealReportTarget(){
  const id=location.hash.slice(1);
  if(!/^cell-[0-9]+(?:-(?:related|alternatives|policy_variants)-[0-9]+)*$/.test(id))return;
  const target=document.getElementById(id);if(!target)return;
  for(let el=target;el;el=el.parentElement)if(el.tagName==='DETAILS')el.open=true;
  requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
}
addEventListener('hashchange',revealReportTarget);revealReportTarget();
</script></html>`;
}
