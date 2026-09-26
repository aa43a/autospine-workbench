// Related review journals are independent; their decisions never update the baseline.
import {createRelatedSync} from './motion-related-sync.js';
import {contactCheckText} from './motion-related-checks.js';
import {appendSkirtChecks} from './motion-related-skirt.js';
import {appendStageReview} from './motion-stage-review.js';
export function appendRelatedCandidates(parent, job, {synchronize=false}={}) {
  const clock=synchronize?createRelatedSync():null;
  const controller=new AbortController();let disposed=false;
  function clear(){disposed=true;controller.abort();clock?.clear();window.removeEventListener('pagehide',clear);}
  if(clock)window.addEventListener('pagehide',clear,{once:true});
  const button=document.createElement('button');button.textContent='查看已关联改进候选';
  const panel=document.createElement('section');panel.hidden=true;panel.setAttribute('aria-live','polite');
  const base=`/api/motions/${job.job_id}/view/`;
  button.onclick=async()=>{
    if(disposed)return;
    clock?.clear();
    button.disabled=true;panel.hidden=false;panel.textContent='正在核对关联候选…';
    try {
      const response=await fetch(base+'related-candidates.json',{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw Error('当前服务尚不能读取关联候选，或来源已变化；原候选保持不变。');
      const report=await response.json();
      if(disposed)return;
      if(report.baseline_sha256!==job.result.artifact_sha256)throw Error('原任务候选已变化，请刷新后重新查看。');
      if(!Array.isArray(report.rows)||report.rows.length>24)throw Error('关联清单无效');
      panel.replaceChildren();
      if(!report.rows.length)panel.textContent='此任务尚无已核验的改进候选。';
      for(const row of report.rows){
        if(!/^[a-f0-9]{64}$/.test(row.registration_sha256)||!/^[a-f0-9]{64}$/.test(row.candidate_sha256))throw Error('候选身份无效');
        const detail=document.createElement('details'),summary=document.createElement('summary');
        summary.textContent=`改进候选 ${row.candidate_sha256.slice(0,10)} · 证据 ${row.registration_sha256.slice(0,8)} · ${row.additional_checks?'含脚端复测 · ':''}${row.skirt_checks?'含遮挡定位 · ':''}播放、验收与下载`;
        const note=document.createElement('p');
        note.textContent=`目标 Spine ${row.target_version||'未记录'}；实际 Runtime ${row.runtime_version}，${row.sampled_frames} 个已有采样。与原任务共享动作和角色来源，策略及结果不同；不替换原任务。关联与 Runtime 通过不代表接触、遮挡或视觉通过，原任务结论不沿用。`;
        const visual=document.createElement('p');
        const checks=document.createElement('p');checks.textContent=contactCheckText(row.additional_checks);
        visual.textContent=row.visual ? `登记时保留的历史阶段记录：${row.visual.user_response||row.visual.decision}。范围：${row.visual.scope}。保留异常：${(row.visual.retained_exceptions||[]).join('、')||'见记录'}。当前结论请读取下方阶段验收。` : '可播放当前候选后，在下方记录阶段验收。';
        const path=base+'related-candidates/'+row.registration_sha256+'/';
        const play=document.createElement('button');play.textContent='加载改进候选时间轴';
        const syncStatus=document.createElement('p');syncStatus.setAttribute('role','status');
        if(clock)syncStatus.textContent='加载后使用左侧源动作时间轴同步对照；时长不匹配时保留独立播放。';
        const playerHost=document.createElement('div');playerHost.append(play);
        let detach=null;
        const show=(time=null)=>{
          if(disposed)return;
          detach?.();detach=null;
          const frame=document.createElement('iframe');frame.title='关联改进候选时间轴';
          frame.src=path+'player.html'+(time===null?'':`?time=${encodeURIComponent(time)}`);frame.style.cssText='width:100%;height:65vh;border:0';
          playerHost.replaceChildren(frame);
          if(time===null)detach=clock?.attach(frame,row.candidate_sha256,syncStatus);
          else syncStatus.textContent='已定位指定姿态，当前使用独立时间轴；不改变源动作播放位置。';
        };
        play.onclick=()=>show();
        const download=document.createElement('a');download.textContent='下载此候选（含异常与来源记录）';download.href=path+'candidate.zip';download.download='motion-related-'+row.candidate_sha256.slice(0,10)+'.zip';
        const evidence=document.createElement('a');evidence.textContent='查看关联依据';evidence.href=path+'report.json';evidence.target='_blank';evidence.rel='noopener';
        detail.append(summary,note,checks,visual);
        appendSkirtChecks(detail,row.skirt_checks,time=>show(time));
        detail.append(playerHost,syncStatus);
        appendStageReview(detail,{job_id:job.job_id,result:{artifact_sha256:row.candidate_sha256}},
          {registration:row.registration_sha256});
        detail.append(download,document.createTextNode(' · '),evidence);panel.append(detail);
      }
    }catch(error){if(!disposed)panel.textContent=error.message;}
    finally{if(!disposed)button.disabled=false;}
  };
  parent.append(button,panel);
  return {clear,seek(time,end){clock?.seek(time,end);}};
}
