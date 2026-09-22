export const POSE_PROFILE='absolute-projection-hip-center-temporal-v1';
export function poseSelection(value,body){
  if(!value)return {};
  if(value!==POSE_PROFILE)throw Error('未知源姿态策略');
  if(['clip','projection','projection_selection','torso_projection_profile'].some(k=>body[k]!=null))
    throw Error('源姿态候选目前要求完整片段及来源视角，请取消裁剪、恒定偏转和躯干投影。');
  return {pose_profile:value};
}
export function createPoseSelection(button){
  const label=document.createElement('label');label.textContent='姿态策略 ';
  const select=document.createElement('select');select.setAttribute('aria-label','姿态策略');
  select.add(new Option('现有策略',''));select.add(new Option('源姿态与髋中心（实验候选）',POSE_PROFILE));
  const note=document.createElement('p');note.textContent='源姿态候选保留源举臂方向；肩部连接、掌面和遮挡仍需检查，不代表已通过验收。';
  label.append(select);button.before(label,note);
  return {selection:body=>poseSelection(select.value,body),reset(){select.value='';}};
}
