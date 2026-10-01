// Fixed-step draft solver. Kept in parity with joint_spring.py / joint_wind.py.
// Results are immutable lookup tracks; drawing and seeking never integrate.
const rad=Math.PI/180,deg=180/Math.PI,mod=(v,n)=>((v%n)+n)%n;
export const WIND_SCHEMA='autospine.wind/v1';
export function windParameters(config,time){
  const keys=config.keys??[];if(!keys.length)return [config.strength,config.direction];
  if(time<=keys[0].time)return [keys[0].strength,keys[0].direction];
  for(let i=1;i<keys.length;i++)if(time<keys[i].time){const a=keys[i-1],b=keys[i],f=(time-a.time)/(b.time-a.time);
    return [a.strength+(b.strength-a.strength)*f,a.direction+mod(b.direction-a.direction+180,360)*f-180*f];}
  const last=keys.at(-1);return [last.strength,last.direction];
}
export function windVectors(config,times,loop=false){
  let frequency=config.frequency;if(loop&&frequency)frequency=Math.max(1,Math.floor(frequency*times.at(-1)+.5))/times.at(-1);
  const phase=(config.seed%65536)/65536*2*Math.PI;
  const values=times.map(time=>{const [strength,direction]=windParameters(config,time);
    const pulse=.65*Math.sin(2*Math.PI*frequency*time+phase)+.35*Math.sin(4*Math.PI*frequency*time+phase*.73);
    const speed=strength/100*(frequency?1+config.gust*pulse:1),force=config.enabled?speed*Math.abs(speed):0;
    return [force*Math.cos(direction*rad),force*Math.sin(direction*rad)];});
  return {values,compatible:Math.hypot(values[0][0]-values.at(-1)[0],values[0][1]-values.at(-1)[1])<=1e-8};
}
export function angularWind(vectors,poses,{axis_offset=0,response=1,length=100}={}){
  const scale=360*response*Math.max(.5,Math.min(2,Math.sqrt(100/Math.max(8,length))));
  return poses.map((p,i)=>scale*(Math.cos((p[2]+axis_offset)*rad)*vectors[i][1]-Math.sin((p[2]+axis_offset)*rad)*vectors[i][0]));
}
export function springSolve(times,poses,{stiffness=36,damping=.85,strength=1,max_angle=4,length=100,loop=false,external=null,compatible=true}={}){
  const n=times.length,dt=times[1]-times[0],angles=[poses[0][2]];
  for(let i=1;i<n;i++)angles.push(angles[i-1]+mod(poses[i][2]-angles[i-1]+180,360)-180);
  const periodic=loop&&compatible&&Math.hypot(poses[0][0]-poses.at(-1)[0],poses[0][1]-poses.at(-1)[1])<=.25&&Math.abs(angles.at(-1)-angles[0])<=.1;
  const forces=poses.map((p,i)=>{const a=i?i-1:periodic?n-2:0,b=i<n-1?i+1:periodic?1:n-1;
    let accel=0;
    if(periodic||i>0&&i<n-1){const dx=(poses[b][0]-2*p[0]+poses[a][0])/(dt*dt),dy=(poses[b][1]-2*p[1]+poses[a][1])/(dt*dt);
      accel=(-Math.sin(angles[i]*rad)*dx+Math.cos(angles[i]*rad)*dy)/Math.max(8,length);}
    return Math.max(-720,Math.min(720,strength*(stiffness*-(angles[i]-angles[0])*.35-accel*deg*.35+(external?.[i]??0))));});
  const friction=2*damping*Math.sqrt(stiffness);let position=0,velocity=0,values=[];
  for(let cycle=0;cycle<(periodic?9:1);cycle++){
    const start=[position,velocity];values=[position];
    for(let i=1;i<n;i++){velocity+=(forces[i]-stiffness*position-friction*velocity)*dt;position+=velocity*dt;
      if(Math.abs(position)>max_angle){position=Math.sign(position)*max_angle;if(position*velocity>0)velocity=0;}values.push(position);}
    if(periodic&&cycle>=1&&Math.abs(position-start[0])<=.01&&Math.abs(velocity-start[1])<=.1)break;
  }
  return values;
}
export function lookup(times,values,time){
  let lo=0,hi=times.length-1;while(lo+1<hi){const mid=(lo+hi)>>1;if(times[mid]<=time)lo=mid;else hi=mid;}
  const f=Math.max(0,Math.min(1,(time-times[lo])/(times[hi]-times[lo])));return values[lo]+f*(values[hi]-values[lo]);
}
export function bakeSpring(times,values){
  const indices=[];for(let i=0;i<times.length;i+=2)indices.push(i);if(indices.at(-1)!==times.length-1)indices.push(times.length-1);
  const kept=new Set(indices);
  for(let j=1;j<indices.length;j++){const a=indices[j-1],b=indices[j];for(let i=a+1;i<b;i++){
    const f=(times[i]-times[a])/(times[b]-times[a]);if(Math.abs(values[i]-values[a]-f*(values[b]-values[a]))>.05)kept.add(i);}}
  const order=[...kept].sort((a,b)=>a-b);return {times:order.map(i=>times[i]),values:order.map(i=>values[i])};
}
export function helperPose(base,bones,helpers,values){
  const result={...base};for(const name of helpers){const bone=bones[name],[a,b,c,d,x,y]=result[bone.parent],angle=((bone.rotation??0)+(values[name]??0))*rad;
    const co=Math.cos(angle),si=Math.sin(angle),bx=bone.x??0,by=bone.y??0;
    result[name]=[a*co+b*si,-a*si+b*co,c*co+d*si,-c*si+d*co,x+a*bx+b*by,y+c*bx+d*by];}return result;
}
