import {validateEditorDraft} from './motion-editor-draft.js';
import {appendCandidateDownload} from './motion-candidate-download.js';
import {appendReadiness} from './motion-readiness.js';
const jobId=/^motion-[a-f0-9]{32}$/;
const steps={queued:'排队等待',verify_source:'校验来源',retarget:'映射角色并修正局部变形',
  depth_overlap:'检查前后遮挡',depth_partition:'划分绘制区域',depth_refinement:'校准深度',
  depth_cloth_constraints:'检查服装遮挡',depth_limb_constraints:'检查肢体遮挡',depth_ordering:'检查绘制顺序',
  runtime:'官方 Runtime 检查',runtime_prepare:'准备动画检查',runtime_geometry:'检查网格',
  runtime_reference:'核对动画数据',runtime_setup:'核对初始图像',local_depth:'整理遮挡异常',
  publish_candidate:'保存候选',complete:'处理结束'};
export function fixedBuildRequest(draft){
  const value=validateEditorDraft(draft),yaw=value.keys[0].yaw;
  if(value.keys.some(k=>k.yaw!==yaw))throw Error('动态角度烘焙尚未接入；请保留草稿，或明确恢复固定角度后构建。');
  if(Math.abs(yaw)>90)throw Error('当前构建支持 −90° 至 90°；不会自动改写或截断你的旋转角度。');
  return {project_id:value.project_id,character_job_id:value.character_job_id,contact_correction:true,clip:null,
    projection:{profile:'constant-yaw-source-motion-v1',yaw_degrees:yaw},
    pose_profile:'constant-view-absolute-pose-hip-center-v1-experiment'};
}
export function createEditorBuild({snapshot}){
  const $=id=>document.getElementById(id);
  let current=null,timer=null,busy=false,fetching=false;
  const request=async(url,body)=>{
    const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)}:{cache:'no-store'});
    const value=await response.json();if(!response.ok)throw Error(value.reason_code||`请求失败 (${response.status})`);return value;
  };
  function render(job){
    const active=['pending','running'].includes(job.status);
    const states={pending:'已排队',running:'构建中',succeeded:'候选已生成',failed:'构建失败',canceled:'已取消',interrupted:'任务已中断',outdated:'来源已变化'};
    $('build-status').textContent=`${states[job.status]||job.status} · ${job.name||''} · ${job.project_id||''} · ${steps[job.step]||job.step||''}${job.reason_code?' · '+job.reason_code:''}`;
    $('build').disabled=busy||active;$('cancel-build').disabled=!active||Boolean(job.cancel_requested);
    const panel=$('build-result');panel.replaceChildren();
    const history=document.createElement('a');history.href=`/motions.html#${job.job_id}`;history.textContent='查看此独立任务与完整记录';panel.append(history);
    if(job.status==='succeeded'&&job.result?.artifact_sha256){
      const note=document.createElement('p');note.textContent='这是已冻结角度的构建结果。上方草稿的新修改不会影响它；技术异常与阶段验收独立保留。';panel.append(note);
      const play=document.createElement('a');play.href=`/api/motions/${job.job_id}/view/player.html`;play.textContent='打开此候选的可动验收窗口';play.target='_blank';play.rel='noopener';panel.append(play);
      appendCandidateDownload(panel,job);appendReadiness(panel,job);
    }
    return active;
  }
  async function refresh(){
    if(!current||fetching)return;fetching=true;clearTimeout(timer);timer=null;const id=current;
    try{const job=await request(`/api/motions/${id}`);if(current!==id)return;
      if(job.kind!=='adapt'||job.job_id!==id)throw Error('不是角色动作构建任务');
      if(render(job))timer=setTimeout(refresh,3000);
    }catch(e){$('build-status').textContent=e.message;}finally{fetching=false;}
  }
  $('build').onclick=async()=>{
    if(busy)return;busy=true;$('build').disabled=true;
    try{const draft=snapshot(),body=fixedBuildRequest(draft);
      $('build-status').textContent='正在提交独立候选，请勿重复提交…';
      const queued=await request(`/api/motions/${draft.source_id}/adapt`,body);
      if(!jobId.test(queued.job_id))throw Error('未收到有效任务编号，请在动作库检查任务');
      current=queued.job_id;history.replaceState(null,'',`#${current}`);await refresh();
    }catch(e){$('build-status').textContent=e.message;}
    finally{busy=false;$('build').disabled=Boolean(timer);}
  };
  $('refresh-build').onclick=refresh;
  $('cancel-build').onclick=async()=>{
    if(!current)return;$('cancel-build').disabled=true;
    try{await request(`/api/motions/${current}/cancel`,{});await refresh();}
    catch(e){$('build-status').textContent=e.message;}
  };
  const initial=location.hash.slice(1);if(jobId.test(initial)){current=initial;void refresh();}
  window.addEventListener('pagehide',()=>clearTimeout(timer));
}
