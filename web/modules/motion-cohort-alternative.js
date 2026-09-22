import {appendStageReview} from './motion-stage-review.js';
import {appendRotationDetails} from './motion-rotation-details.js';
import {appendCandidateDownload} from './motion-candidate-download.js';
import {appendReadiness} from './motion-readiness.js';
import {createCohortSync} from './motion-cohort-sync.js';

export function createAlternativePanel(container,request,{onSeek}={}){
  let revision=0,sync=null,lastTime=0,lastEnd=null;
  function clear(){revision++;sync?.clear();sync=null;container.replaceChildren();container.hidden=true;}
  async function open(row,sourceHash){
    clear();const version=revision;container.hidden=false;
    const title=document.createElement('h2');title.textContent='替代视角候选';
    const close=document.createElement('button');close.textContent='关闭替代候选';close.onclick=clear;
    const status=document.createElement('p');status.textContent='正在核对替代候选与来源…';
    container.append(title,close,status);container.scrollIntoView({block:'start'});
    try{
      if(!/^motion-[a-f0-9]{32}$/.test(row.job_id)||!/^motion-[a-f0-9]{32}$/.test(row.source_job_id))throw Error('候选清单无效');
      const base=`/api/motions/${row.job_id}`;
      const [job,source,review]=await Promise.all([request(base),request(`/api/motions/${row.source_job_id}`),request(base+'/stage-review')]);
      if(version!==revision)return;
      if(job.status!=='succeeded'||job.kind!=='adapt'||job.result?.artifact_sha256!==row.artifact_sha256
          ||source.status!=='succeeded'||source.source_sha256!==sourceHash
          ||review.artifact_sha256!==row.artifact_sha256||review.evidence_sha256!==row.evidence_sha256)throw Error('来源或候选证据已变化，请重新比较');
      title.textContent=`替代视角 · ${row.view==='side'?'侧面':'正面'}${row.projection?` · 偏转 ${row.projection.yaw_degrees}°`:''}`;
      status.textContent='原固定候选保留在上方。下面的验收只记录当前替代候选，不替换固定矩阵。';
      const frame=document.createElement('iframe');frame.title='替代视角角色时间轴';frame.src=base+'/view/player.html';
      container.append(frame);
      if(onSeek){
        const note=document.createElement('p');container.append(note);sync=createCohortSync(note);
        if(lastEnd!==null)sync.seek(lastTime,lastEnd);
        sync.attach(frame,row.artifact_sha256);
      }
      const seek=time=>{if(version!==revision)return;if(onSeek)onSeek(time);else frame.src=base+`/view/player.html?time=${encodeURIComponent(time)}`;};
      appendCandidateDownload(container,job);
      appendStageReview(container,job);
      appendReadiness(container,job,null,{onSeek:time=>{
        seek(time);
      },onInspect:onSeek?(slot,triangle,animation)=>{
        if(version===revision)sync?.inspect(slot,triangle,animation);
      }:undefined});
      appendRotationDetails(container,job,{onSeek:time=>{
        seek(time);
      }});
    }catch(error){if(version===revision)status.textContent='无法打开：'+error.message;}
  }
  return {clear,open,seek(time,end){lastTime=time;lastEnd=end;sync?.seek(time,end);}};
}
