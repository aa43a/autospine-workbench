"use strict";
import {needsBindingReview,auditBindingExceptions} from './workbench-character-ledger.js';

export function characterProgress(job,confirmed=[],review=null,dirty=false,audit=null){
 if(dirty)return ['校正尚未保存：当前候选状态不能代表最新修改。'];
 if(!job||job.status!=='needs_review')return ['整角色候选尚未准备完成。'];
 const layers=job.layers||[];
 const auditExact=audit?.authority==='none'&&['project_id','job_id','artifact_sha256'].every(k=>audit[k]===job[k]);
 const failedAudit=auditBindingExceptions(job,audit);
 const pending=layers.filter(l=>needsBindingReview(l,confirmed)||failedAudit.has(l.layer_id)).length;
 const rows=[`绑定处理：${layers.length-pending} / ${layers.length} 层；${pending} 层待处理。`];
 if(auditExact)rows.push(`自动绑定抽查：明确判断 ${audit.metrics.assessed_bindings} / ${audit.metrics.eligible_bindings} 项；${audit.metrics.incorrect} 项需修改。`);
 const geometry=job.runtime?.geometry_status;
 rows.push(geometry==='passed'?'采样网格：通过。':geometry==='needs_changes'?'采样网格：存在超限变形，需要修正。':'采样网格：尚无通过证据。');
 rows.push(job.runtime?.files?.['report.json']?'Runtime：已有报告，需结合实际播放与视觉复核。':'Runtime：尚无报告。');
 const exact=review&&review.project_id===job.project_id&&review.job_id===job.job_id&&review.artifact_sha256===job.artifact_sha256&&review.authority==='none';
 if(!exact)rows.push('视觉验收：尚未读取当前候选的记录。');
 else {
  const aspects=review.review?.aspects||{},labels={setup:'初始图像',draw_order:'前后顺序',connections:'连接',motion:'动作'};
  const accepted=Object.keys(labels).filter(k=>aspects[k]==='acceptable').length;
  const bad=Object.keys(labels).filter(k=>aspects[k]==='needs_changes').map(k=>labels[k]);
  rows.push(`视觉验收：${accepted} / 4 项可接受${bad.length?'；需要修改：'+bad.join('、'):''}。`);
 }
 rows.push('数值通过不代表视觉通过；此状态不授予发布权。');
 return rows;
}

export function createCharacterProgress(document,reviewAction,auditAction){
 const node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
 const element=node('section'),list=node('ul'),button=node('button','查看并记录视觉复核');
 element.className='character-progress';element.setAttribute('aria-label','整角色完成情况');
 button.type='button';button.className='button button-secondary';button.addEventListener('click',reviewAction);
 const auditButton=node('button','自动绑定抽查');
 auditButton.type='button';auditButton.className='button button-secondary';auditButton.addEventListener('click',()=>auditAction?.());
 element.append(node('h4','当前还差什么'),list,button,auditButton);
 return {element,sync(job,confirmed,review,disabled,audit=null){
  list.replaceChildren(...characterProgress(job,confirmed,review,disabled,audit).map(text=>node('li',text)));
  button.disabled=disabled||job?.status!=='needs_review'||!job.runtime?.files?.['report.json'];
  auditButton.disabled=button.disabled||!auditAction;
 }};
}
