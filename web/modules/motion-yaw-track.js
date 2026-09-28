// Keep unwrapped angles: 350 -> 370 crosses 360; 0 -> 360 means a full turn.
export function validateYawTrack(keys,duration){
  if(!Number.isFinite(duration)||duration<=0||!Array.isArray(keys)||!keys.length||keys.length>256)throw Error('无效角度时间轴');
  let previous=-1;
  for(const key of keys){
    if(!key||Object.keys(key).sort().join(',')!=='time,yaw'||!Number.isFinite(key.time)||key.time<0||key.time>duration||key.time<=previous
      ||!Number.isFinite(key.yaw)||Math.abs(key.yaw)>3600)throw Error('角度关键帧无效');
    previous=key.time;
  }
  if(keys[0].time!==0)throw Error('角度时间轴必须从零秒开始');
  return keys;
}
export function sampleYaw(keys,time){
  if(!Number.isFinite(time))throw Error('无效时间');
  if(time<=keys[0].time)return keys[0].yaw;
  const index=keys.findIndex(k=>k.time>=time);
  if(index<0)return keys.at(-1).yaw;
  const a=keys[index-1],b=keys[index];
  return a.yaw+(b.yaw-a.yaw)*(time-a.time)/(b.time-a.time);
}
export function yawSurfaceWarning(yaw){
  const angle=((yaw%360)+540)%360-180;
  return Math.abs(angle)>90?'当前为背向投影：正面素材不能表示背面外观。':Math.abs(angle)>60?'接近侧向：肢体可能投影缩短，侧面素材尚未验证。':'正面范围：仍需检查变形、接触与遮挡。';
}
