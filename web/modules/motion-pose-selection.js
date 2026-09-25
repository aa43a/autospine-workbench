export const POSE_PROFILE='absolute-projection-hip-center-temporal-v1';
export const LEGACY_POST_CONTACT_PROFILE='source-pose-post-contact-margin-v1';
export const POST_CONTACT_PROFILE='source-pose-post-contact-timeline-v2';
const postProfiles=[LEGACY_POST_CONTACT_PROFILE,POST_CONTACT_PROFILE];
export function appendPoseSummary(container,job){
  if(job.result?.moving_ankle_profile){
    const ankle=document.createElement('p');ankle.textContent='脚端策略：跟随源动作（实验）；接触只检查，不锁脚。';
    const details=document.createElement('a');details.textContent='查看脚端修正与最终误差';
    details.href=`/api/motions/${job.job_id}/view/motion-review.json`;details.target='_blank';details.rel='noopener';
    ankle.append(' ',details);container.append(ankle);
  }
  const profile=job.result?.pose_profile;if(!profile)return;
  const note=document.createElement('p');
  note.textContent=profile===POST_CONTACT_PROFILE?'姿态策略：接触后修正与脚部帧间校正 v2（实验候选）':profile===LEGACY_POST_CONTACT_PROFILE?'姿态策略：接触后修正 v1（历史策略）':profile===POSE_PROFILE?'姿态策略：源姿态与髋中心（实验候选）':'姿态策略：'+profile;
  const link=document.createElement('a');link.textContent='查看姿态与修正依据';
  link.href=`/api/motions/${job.job_id}/view/motion-review.json`;
  link.target='_blank';link.rel='noopener';
  note.append(' · ',link);container.append(note);
  if(postProfiles.includes(profile)){
    const finalContact=document.createElement('a');finalContact.textContent='最终时间轴接触复核';
    finalContact.href=`/api/motions/${job.job_id}/view/final-contact.json`;
    finalContact.target='_blank';finalContact.rel='noopener';container.append(finalContact);
  }
}
export function poseSelection(value,body){
  if(!value)return {};
  if(![POSE_PROFILE,...postProfiles].includes(value))throw Error('未知源姿态策略');
  if(postProfiles.includes(value)&&body.contact_correction===false)throw Error('接触后修正需要启用接触处理。');
  if(['clip','projection','projection_selection','torso_projection_profile'].some(k=>body[k]!=null))
    throw Error('源姿态候选目前要求完整片段及来源视角，请取消裁剪、恒定偏转和躯干投影。');
  return {pose_profile:value};
}
export function createPoseSelection(button,onChange=()=>{}){
  const label=document.createElement('label');label.textContent='姿态策略 ';
  const select=document.createElement('select');select.setAttribute('aria-label','姿态策略');
  select.add(new Option('现有策略',''));select.add(new Option('源姿态与髋中心（实验候选）',POSE_PROFILE));
  select.add(new Option('接触后修正与脚部帧间校正 v2（实验）',POST_CONTACT_PROFILE));
  const note=document.createElement('p');note.textContent='源姿态候选保留源举臂方向；v2 还会检查脚部帧间朝向并补充必要关键帧。要求源脚部方向可观测；肩部、掌面、鞋底与遮挡仍需检查。旧任务重试保留其原策略。';
  label.append(select);button.before(label,note);
  select.onchange=()=>onChange(select.value);
  return {selection:body=>poseSelection(select.value,body),reset(){select.value='';}};
}
