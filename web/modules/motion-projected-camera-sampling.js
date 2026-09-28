// Opt-in v2 foundation; public tasks still retain their existing v1 grid.
import {cameraSchedule,interpolateWorld} from './motion-camera-sampling.js';
import {sampleYaw} from './motion-yaw-track.js';
export const PROJECTED_SAMPLING_PROFILE='camera-world-projected-adaptive-v2';
export function refineProjectedCamera(times,vectors,keys,duration,reference){
  if(!Object.keys(vectors).length||!Number.isFinite(reference)||reference<=0)throw Error('camera_refinement_input_invalid');
  const ticks=new Set(cameraSchedule(times,keys,duration).map(t=>Math.round(t*1e6))),cache=new Map();
  function angles(tick){
    if(!cache.has(tick)){
      const t=tick/1e6,r=sampleYaw(keys,t)*Math.PI/180;
      const result=Object.keys(vectors).sort().map(role=>{
        const v=interpolateWorld(vectors[role],times,[t])[0];
        const x=Math.cos(r)*v[0]-Math.sin(r)*v[2],y=v[1],z=Math.sin(r)*v[0]+Math.cos(r)*v[2];
        if(Math.hypot(x,y)<=Math.max(1e-12,Math.hypot(x,y,z)*1e-6,reference*1e-9))throw Error('camera_refinement_direction_unobservable:'+role);
        return Math.atan2(y,x)*180/Math.PI;
      });cache.set(tick,result);
    }return cache.get(tick);
  }
  const delta=(a,b)=>((b-a+180)%360+360)%360-180;
  const sorted=[...ticks].sort((a,b)=>a-b),pending=sorted.slice(1).map((b,i)=>[sorted[i],b]);
  while(pending.length){
    const [a,b]=pending.pop(),m=Math.floor((a+b)/2),first=angles(a),last=angles(b),middle=a<m&&m<b?angles(m):first;
    const needs=first.some((x,i)=>{const y=last[i],z=middle[i];return Math.abs(delta(x,y))>12||
      (a<m&&m<b&&(Math.abs(delta(x,z))>12||Math.abs(delta(z,y))>12||Math.abs(delta(x,z)-delta(x,y)*(m-a)/(b-a))>2));});
    if(!needs)continue;
    if(!(a<m&&m<b))throw Error('camera_refinement_tick_resolution_exceeded');
    if(ticks.size>=4096)throw Error('camera_sampling_budget_exceeded');
    ticks.add(m);pending.push([a,m],[m,b]);
  }
  return [...ticks].sort((a,b)=>a-b).map(t=>t/1e6);
}
