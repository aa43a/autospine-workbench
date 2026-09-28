export function sampleSourceFrame(frames,time){
  if(!Number.isFinite(time)||!frames?.length)throw Error('source_sample_invalid');
  if(time<=frames[0].time)return frames[0];if(time>=frames.at(-1).time)return frames.at(-1);
  let low=0,high=frames.length-1;
  while(high-low>1){const mid=(low+high)>>1;if(frames[mid].time<=time)low=mid;else high=mid;}
  const a=frames[low],b=frames[high];if(a.time===time)return a;if(b.time===time)return b;
  const t=(time-a.time)/(b.time-a.time);
  return {time,frame:a.frame,interpolated:true,joints:a.joints.map((point,i)=>point.map((v,j)=>v+(b.joints[i][j]-v)*t))};
}
