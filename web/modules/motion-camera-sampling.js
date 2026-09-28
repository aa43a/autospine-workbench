// Same versioned grid and world-space interpolation as camera_sampling.py.
import {validateYawTrack,sampleYaw} from './motion-yaw-track.js';
export const SAMPLING_PROFILE='camera-world-linear-adaptive-v1';
const TICKS=1000000,MAX_SAMPLES=4096,MAX_TRAVEL=14;
export function cameraSchedule(times,keys,duration){
  validateYawTrack(keys,duration);
  if(!Array.isArray(times)||times.length<2||times.length>MAX_SAMPLES||times[0]!==0||times.at(-1)!==duration
    ||times.some((t,i)=>!Number.isFinite(t)||(i&&t<=times[i-1])))throw Error('camera_sampling_source_times_invalid');
  const tick=t=>Math.floor(t*TICKS+.5),native=times.map(tick);
  if(times.some((t,i)=>Math.abs(t-native[i]/TICKS)>1e-10))throw Error('camera_sampling_source_time_precision');
  const knots=[...new Set([...native,...keys.map(k=>tick(k.time))])].sort((a,b)=>a-b),ticks=new Set(knots);
  for(let i=1;i<knots.length;i++){
    const a=knots[i-1],b=knots[i],first=a/TICKS,last=b/TICKS;
    const split=[first,...keys.filter(k=>first<k.time&&k.time<last).map(k=>k.time),last];
    let travel=0;for(let j=1;j<split.length;j++)travel+=Math.abs(sampleYaw(keys,split[j])-sampleYaw(keys,split[j-1]));
    const parts=Math.max(1,Math.ceil(travel/MAX_TRAVEL));
    if(parts>b-a)throw Error('camera_sampling_tick_resolution_exceeded');
    if(ticks.size+parts-1>MAX_SAMPLES)throw Error('camera_sampling_budget_exceeded');
    for(let j=1;j<parts;j++)ticks.add(a+Math.floor((b-a)*j/parts+.5));
  }
  return [...ticks].sort((a,b)=>a-b).map(n=>n/TICKS);
}
export function interpolateWorld(values,times,wanted){
  if(values.length!==times.length)throw Error('camera_sampling_observation_count');
  function mix(a,b,f){
    if(Array.isArray(a)&&Array.isArray(b)&&a.length===b.length)return a.map((x,i)=>mix(x,b[i],f));
    if(!Number.isFinite(a)||!Number.isFinite(b))throw Error('camera_sampling_observation_invalid');
    return a+(b-a)*f;
  }
  return wanted.map(t=>{
    if(t<times[0]||t>times.at(-1))throw Error('camera_sampling_extrapolation_forbidden');
    let lo=0,hi=times.length-1;while(hi-lo>1){const m=Math.floor((lo+hi)/2);if(times[m]<=t)lo=m;else hi=m;}
    if(t===times[lo])return structuredClone(values[lo]);if(t===times[hi])return structuredClone(values[hi]);
    return mix(values[lo],values[hi],(t-times[lo])/(times[hi]-times[lo]));
  });
}
