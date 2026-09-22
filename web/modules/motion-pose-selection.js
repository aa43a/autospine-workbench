export const POSE_PROFILE='absolute-projection-hip-center-temporal-v1';
export const POST_CONTACT_PROFILE='source-pose-post-contact-margin-v1';
export function appendPoseSummary(container,job){
  const profile=job.result?.pose_profile;if(!profile)return;
  const note=document.createElement('p');
  note.textContent=profile===POST_CONTACT_PROFILE?'姿态策略：源姿态与接触后修正（实验候选）':profile===POSE_PROFILE?'姿态策略：源姿态与髋中心（实验候选）':'姿态策略：'+profile;
  const link=document.createElement('a');link.textContent='查看姿态与修正依据';
  link.href=`/api/motions/${job.job_id}/view/motion-review.json`;
  link.target='_blank';link.rel='noopener';
  note.append(' · ',link);container.append(note);
  if(profile===POST_CONTACT_PROFILE){
    const finalContact=document.createElement('a');finalContact.textContent='最终时间轴接触复核';
    finalContact.href=`/api/motions/${job.job_id}/view/final-contact.json`;
    finalContact.target='_blank';finalContact.rel='noopener';container.append(finalContact);
  }
}
export function poseSelection(value,body){
  if(!value)return {};
  if(![POSE_PROFILE,POST_CONTACT_PROFILE].includes(value))throw Error('未知源姿态策略');
  if(value===POST_CONTACT_PROFILE&&body.contact_correction===false)throw Error('接触后修正需要启用接触处理。');
  if(['clip','projection','projection_selection','torso_projection_profile'].some(k=>body[k]!=null))
    throw Error('源姿态候选目前要求完整片段及来源视角，请取消裁剪、恒定偏转和躯干投影。');
  return {pose_profile:value};
}
export function createPoseSelection(button){
  const label=document.createElement('label');label.textContent='姿态策略 ';
  const select=document.createElement('select');select.setAttribute('aria-label','姿态策略');
  select.add(new Option('现有策略',''));select.add(new Option('源姿态与髋中心（实验候选）',POSE_PROFILE));
  select.add(new Option('源姿态与接触后修正（FBX/BVH 实验）',POST_CONTACT_PROFILE));
  const note=document.createElement('p');note.textContent='源姿态候选保留源举臂方向；接触后修正还会重算脚部方向和局部变形，仅支持可观测脚部的 FBX/BVH。肩部、掌面与遮挡仍需检查。';
  label.append(select);button.before(label,note);
  return {selection:body=>poseSelection(select.value,body),reset(){select.value='';}};
}
