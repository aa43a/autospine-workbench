import {validateEditorDraft} from './motion-editor-draft.js';
import {appendCandidateDownload} from './motion-candidate-download.js';
import {appendReadiness} from './motion-readiness.js';
const jobId=/^motion-[a-f0-9]{32}$/;
const reasons={motion_layer_target_mismatch:'角色图层版本已变化，请重新加载角色后恢复兼容草稿。',
  moving_ankle_distinct_times_collide_in_runtime:'动作时间点在 Runtime 精度下发生冲突，未生成候选；原始动作和草稿保留。',
  motion_target_timeout:'构建超过运行时限，已停止。请缩短动作或关闭中间姿态补帧后重试；已有候选保留。',
  motion_target_stalled:'构建长时间没有更新进度，已停止。请查看任务记录后重试；已有候选保留。',
  motion_decode_timeout:'动作处理超过时限。请查看任务记录，尝试缩短动作后重新构建。',
  motion_layer_attachment_unsupported:'所选附件不支持当前网格校正，请恢复该层修改后重试。',
  motion_layer_attachment_timeline_unsupported:'此候选含附件切换动画，暂不支持整段网格校正。',
  motion_layer_sample_limit:'图层校正所需采样超过上限，请缩短源动作后重试。',
  motion_layer_interpolation_error:'图层校正在中间姿态误差过大，请减小旋转或缩放后重试。',
  motion_layer_transform_out_of_range:'图层校正数值超出支持范围。'};
const steps={queued:'排队等待',verify_source:'校验来源',retarget:'映射角色并修正局部变形',
  joint_inventory:'核对联合动画素材',joint_face:'烘焙面部表情',joint_secondary:'烘焙发束与裙袖响应',joint_validate:'验证联合动画与循环',
  depth_overlap:'检查前后遮挡',depth_partition:'划分绘制区域',depth_refinement:'校准深度',
  depth_cloth_constraints:'检查服装遮挡',depth_limb_constraints:'检查肢体遮挡',depth_ordering:'检查绘制顺序',
  runtime:'官方 Runtime 检查',runtime_prepare:'准备动画检查',runtime_geometry:'检查网格',
  runtime_reference:'核对动画数据',runtime_setup:'核对初始图像',local_depth:'整理遮挡异常',
  publish_candidate:'保存候选',complete:'处理结束'};
const duration=value=>{const seconds=Math.max(0,Math.floor(Number(value)||0));return seconds<60?`${seconds} 秒`:`${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;};
export function buildProgressText(job,now=Date.now()){
  const running=['pending','running'].includes(job.status),progress=running?(job.progress||{}):{};
  const step=progress.step||job.step,parts=[steps[step]||step||'等待进度'];
  const stages={sample_geometry:'采样网格变形',inspect_attachment:'检查图层',solve_attachment:'求解图层修正',attachment_complete:'图层修正完成',refinement_round:'细化修正',check_interpolation:'检查中间姿态'};
  if(progress.stage)parts.push(stages[progress.stage]||progress.stage);
  if(progress.slot)parts.push(`图层 ${progress.slot}`);
  if(Number.isFinite(progress.slot_index)&&progress.total_slots>0)parts.push(`图层 ${progress.slot_index+1} / ${progress.total_slots}`);
  if(Number.isFinite(progress.iteration)&&progress.max_rounds>0)parts.push(`修正轮次 ${progress.iteration+1} / ${progress.max_rounds}`);
  if(Number.isFinite(progress.frame_index)&&progress.sample_count>0)parts.push(`采样 ${progress.frame_index+1} / ${progress.sample_count}`);
  if(Number.isFinite(job.elapsed_seconds))parts.push(`已用时 ${duration(job.elapsed_seconds)}`);
  if(!Number.isFinite(progress.frame_index)&&Number.isFinite(progress.completed)&&Number.isFinite(progress.total)&&progress.total>0)
    parts.push(`本阶段 ${progress.completed} / ${progress.total}${progress.unit?' '+progress.unit:''}`);
  else if(!Number.isFinite(progress.frame_index)&&Number.isFinite(progress.completed))parts.push(`本阶段已完成 ${progress.completed}${progress.unit?' '+progress.unit:''}`);
  const updated=typeof progress.updated_at==='number'?progress.updated_at*1000:Date.parse(progress.updated_at);
  if(Number.isFinite(updated)&&['pending','running'].includes(job.status)){
    const age=Math.max(0,(now-updated)/1000);parts.push(age<10?'刚收到进度更新':`上次进度更新 ${duration(age)} 前`);
  }
  if(Number.isFinite(job.timeout_seconds)&&job.timeout_seconds>0)parts.push(`运行时限 ${duration(job.timeout_seconds)}`);
  return parts.join(' · ');
}
export function fixedBuildRequest(draft){
  const value=validateEditorDraft(draft),yaw=value.keys[0].yaw;
  if(value.keys.some(k=>k.yaw!==yaw))throw Error('动态角度烘焙尚未接入；请保留草稿，或明确恢复固定角度后构建。');
  if(Math.abs(yaw)>90)throw Error('当前构建支持 −90° 至 90°；不会自动改写或截断你的旋转角度。');
  return {project_id:value.project_id,character_job_id:value.character_job_id,...(value.layer_edits?{layer_edits:value.layer_edits}:{}),contact_correction:true,clip:null,
    projection:{profile:'constant-yaw-source-motion-v1',yaw_degrees:yaw},
    pose_profile:'constant-view-absolute-pose-hip-center-v1-experiment'};
}
export function editorBuildRequest(draft){
  const value=validateEditorDraft(draft),yaw=value.keys[0].yaw;
  if(value.sampling_profile!=='camera-world-projected-adaptive-v2'&&Math.abs(yaw)<=90&&value.keys.every(k=>k.yaw===yaw))return fixedBuildRequest(value);
  return {project_id:value.project_id,character_job_id:value.character_job_id,...(value.layer_edits?{layer_edits:value.layer_edits}:{}),contact_correction:false,
    projection:{profile:'continuous-yaw-source-camera-v1',keys:value.keys.map(k=>({...k})),
      ...(value.sampling_profile?{sampling_profile:value.sampling_profile}:{})},
    pose_profile:'continuous-yaw-source-camera-v1',moving_ankle_profile:'continuous-camera-ankle-displacement-v1',
    depth_review_profile:'external-arm-torso-depth-sparse-v1-experiment'};
}
export function createEditorBuild({snapshot,inspect=()=>{}}){
  const $=id=>document.getElementById(id);
  let current=null,timer=null,busy=false,fetching=false,active=false,lastJob=null,closed=false;
  const request=async(url,body)=>{
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
    try{
      const response=await fetch(url,body?{signal:controller.signal,method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)}:{signal:controller.signal,cache:'no-store'});
      const value=await response.json();if(!response.ok){
        const detail=value.diagnostics?.[0];
        throw Error((reasons[value.reason_code]||value.reason_code||`请求失败 (${response.status})`)+(detail?` · ${detail.slot||''} ${detail.path} · ${detail.hint}`:''));
      }return value;
    }catch(error){if(error.name==='AbortError')throw Error('连接超时');throw error;}
    finally{clearTimeout(timeout);}
  };
  function render(job){
    active=['pending','running'].includes(job.status);lastJob=job;
    const states={pending:'已排队',running:'构建中',succeeded:'候选已生成',failed:'构建失败',canceled:'已取消',interrupted:'任务已中断',outdated:'来源已变化'};
    $('build-status').textContent=`${states[job.status]||job.status} · ${job.name||''} · ${job.project_id||''}\n${buildProgressText(job)}${job.reason_code?'\n'+(reasons[job.reason_code]||job.reason_code):''}`;
    $('build').disabled=busy||active;$('cancel-build').disabled=!active||Boolean(job.cancel_requested);
    const panel=$('build-result');panel.replaceChildren();
    const history=document.createElement('a');history.href=`/motions.html#${job.job_id}`;history.textContent='查看此独立任务与完整记录';panel.append(history);
    if(job.status==='succeeded'&&job.result?.artifact_sha256){
      const note=document.createElement('p');note.textContent='这是按已保存角度轨道与图层校正构建的独立结果。上方草稿的新修改不会影响它；技术异常与阶段验收独立保留。';panel.append(note);
      const play=document.createElement('a');play.href=`/api/motions/${job.job_id}/view/player.html`;play.textContent='打开此候选的可动验收窗口';play.target='_blank';play.rel='noopener';panel.append(play);
      const compare=document.createElement('button');compare.textContent='在编辑区对照导出结果';compare.onclick=()=>inspect(job);panel.append(compare);
      appendCandidateDownload(panel,job);appendReadiness(panel,job);
    }
    return active;
  }
  async function refresh(){
    if(!current||fetching||closed)return;fetching=true;clearTimeout(timer);timer=null;const id=current;
    try{const job=await request(`/api/motions/${id}`);if(current!==id)return;
      if(job.kind!=='adapt'||job.job_id!==id)throw Error('不是角色动作构建任务');
      render(job);
    }catch(e){$('build-status').textContent=`暂时无法刷新任务：${e.message}。${active?'任务状态尚未确认，将自动重试，请勿重复构建。':'可点击刷新任务重试。'}${lastJob?' 上次记录：'+buildProgressText(lastJob):''}`;}
    finally{fetching=false;$('build').disabled=busy||active;if(active&&!closed)timer=setTimeout(refresh,3000);}
  }
  $('build').onclick=async()=>{
    if(busy||active)return;busy=true;$('build').disabled=true;
    try{const draft=snapshot(),body=editorBuildRequest(draft);
      $('build-status').textContent='正在提交独立候选，请勿重复提交…';
      const queued=await request(`/api/motions/${draft.source_id}/adapt`,body);
      if(!jobId.test(queued.job_id))throw Error('未收到有效任务编号，请在动作库检查任务');
      current=queued.job_id;active=true;lastJob=null;history.replaceState(null,'',`#${current}`);await refresh();
    }catch(e){$('build-status').textContent=e.message;}
    finally{busy=false;$('build').disabled=active;}
  };
  $('refresh-build').onclick=refresh;
  $('cancel-build').onclick=async()=>{
    if(!current)return;$('cancel-build').disabled=true;
    try{await request(`/api/motions/${current}/cancel`,{});await refresh();}
    catch(e){$('build-status').textContent=e.message;}
  };
  const initial=location.hash.slice(1);if(jobId.test(initial)){current=initial;active=true;$('build').disabled=true;void refresh();}
  window.addEventListener('pagehide',()=>{closed=true;clearTimeout(timer);});
}
