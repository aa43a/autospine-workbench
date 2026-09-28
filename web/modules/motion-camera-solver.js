// Browser counterpart of motion_camera_pose: full source frames, one camera basis.
import {validateYawTrack,sampleYaw} from './motion-yaw-track.js';
const radians=Math.PI/180,degrees=180/Math.PI;
const det=m=>m[0]*m[3]-m[1]*m[2];
const unwrap=(previous,value)=>previous===undefined?value:previous+((value-previous+180)%360+360)%360-180;
const project=(p,yaw)=>{const c=Math.cos(yaw*radians),s=Math.sin(yaw*radians);return [c*p[0]-s*p[2],p[1],s*p[0]+c*p[2]];};
function matrix(bone,parent,rotation=0,sx=1,sy=1,translation=[0,0]){
  const angle=((bone.rotation||0)+rotation)*radians;
  sx*=bone.scaleX??1;sy*=bone.scaleY??1;
  const a=Math.cos(angle)*sx,b=-Math.sin(angle)*sy,c=Math.sin(angle)*sx,d=Math.cos(angle)*sy;
  const x=(bone.x||0)+translation[0],y=(bone.y||0)+translation[1];
  if(!parent)return [a,b,c,d,x,y];
  const [pa,pb,pc,pd,px,py]=parent;
  return [pa*a+pb*c,pa*b+pb*d,pc*a+pd*c,pc*b+pd*d,px+pa*x+pb*y,py+pc*x+pd*y];
}
export function solveCamera(document,source,keys){
  validateYawTrack(keys,source.duration);
  if(source.schema!=='autospine.motion-editor-source/v1'||![5,12].includes(source.precision))throw Error('动作来源协议不支持');
  const times=source.times;
  if(!Array.isArray(times)||times.length<2||times.length>768||times[0]!==0||times.at(-1)!==source.duration)throw Error('动作采样范围无效');
  for(let i=1;i<times.length;i++){
    if(!Number.isFinite(times[i])||times[i]<=times[i-1])throw Error('动作采样顺序无效');
    const knots=[times[i-1],...keys.filter(k=>k.time>times[i-1]&&k.time<times[i]).map(k=>k.time),times[i]];
    let travel=0;for(let j=1;j<knots.length;j++)travel+=Math.abs(sampleYaw(keys,knots[j])-sampleYaw(keys,knots[j-1]));
    if(travel>15)throw Error('角度变化超过源采样能力，需要增加动作采样；未丢弃旋转。');
  }
  const bones=document.bones,lookup=Object.fromEntries(bones.map(b=>[b.name,b])),rest={},tracks={},selected={};
  if(!lookup.root||lookup.root.parent||!Number.isFinite(source.reference)||source.reference<=0)throw Error('角色或来源参考无效');
  for(const bone of bones){
    if((bone.inherit??'normal')!=='normal'||bone.shearX||bone.shearY||(bone.parent&&!rest[bone.parent]))throw Error('角色骨骼变换暂不支持');
    rest[bone.name]=matrix(bone,rest[bone.parent]);
  }
  for(const side of ['l','r'])for(const [child,parent] of [['calf','thigh'],['foot','calf'],['forearm','upperarm'],['hand','forearm']])
    if(lookup[`${child}_${side}`]?.parent!==`${parent}_${side}`)throw Error('角色肢体骨骼结构不匹配');
  const reference=['calf_l','foot_l','calf_r','foot_r'].reduce((sum,n)=>sum+Math.hypot(lookup[n].x,lookup[n].y),0)/2;
  const ratio=reference/source.reference,yaws=times.map(t=>sampleYaw(keys,t));
  const vectors={},angles={},issues=[];
  for(const [role,values] of Object.entries(source.vectors)){
    const target=source.role_bones[role];if(!lookup[target]||values.length!==times.length)throw Error('角色骨骼映射或采样缺失');
    vectors[role]=values.map((p,i)=>project(p,yaws[i]));angles[role]=[];
    vectors[role].forEach((p,i)=>{
      const length=Math.hypot(...p),visible=Math.hypot(p[0],p[1]);
      if(!p.every(Number.isFinite)||visible<=Math.max(1e-12,length*1e-6,source.reference*1e-9))throw Error(`投影方向不可观察：${target} · ${times[i].toFixed(3)}秒`);
      angles[role].push(unwrap(angles[role].at(-1),Math.atan2(p[1],p[0])*degrees));
      if(visible/length<.2)issues.push({bone:target,time:times[i],visibility:visible/length});
    });
    tracks[target]={rotate:[]};
    if(role.startsWith('humanoid.arm.')||role.startsWith('humanoid.leg.')){selected[target]=role;tracks[target].scale=[];}
  }
  tracks.root??={};tracks.root.translate=[];
  if(source.roots.length!==times.length||source.hip_centers.length!==times.length)throw Error('身体位移采样缺失');
  const pivot=source.roots[0],relative=p=>p.map((v,i)=>v-pivot[i]);
  const centers=source.hip_centers.map((p,i)=>project(relative(p),yaws[i]));
  const previous={},boneRoles=Object.fromEntries(Object.keys(angles).map(r=>[source.role_bones[r],r]));
  let hipOrigin;
  for(let i=0;i<times.length;i++){
    const time=times[i],world={},root=project(relative(source.roots[i]),yaws[i]);
    const translation=[Number((root[0]/source.reference).toFixed(source.precision))*reference,
      -Number((root[1]/source.reference).toFixed(source.precision))*reference];
    for(const bone of bones){
      const name=bone.name,parent=world[bone.parent],role=boneRoles[name];let rotation=0,sx=1,sy=1;
      if(role){const p=source.role_parents[role];
        rotation=-Number((angles[role][i]-angles[role][0]-(p?angles[p][i]-angles[p][0]:0)).toFixed(source.precision));}
      if(selected[name]){
        const vector=vectors[selected[name]][i],[x,screenY]=vector,y=-screenY;
        const transform=parent??[1,0,0,1,0,0],d=det(transform);
        if(d<=1e-10)throw Error('父骨骼投影退化，未生成该姿态');
        const lx=(transform[3]*x-transform[1]*y)/d,ly=(-transform[2]*x+transform[0]*y)/d;
        rotation=unwrap(previous[name],Math.atan2(ly,lx)*degrees-(bone.rotation||0));previous[name]=rotation;
        const visibility=Math.hypot(x,y)/Math.hypot(...vector);
        let current=matrix(bone,parent,rotation);
        sx=Math.hypot(rest[name][0],rest[name][2])*visibility/Math.hypot(current[0],current[2]);
        current=matrix(bone,parent,rotation,sx);
        sy=det(rest[name])*visibility/det(current);
        if(!Number.isFinite(sx)||!Number.isFinite(sy)||sx<=0||sy<=0)throw Error('肢体缩放退化，未生成该姿态');
        tracks[name].scale.push({time,x:sx,y:sy});
      }
      if(role)tracks[name].rotate.push({time,value:rotation});
      world[name]=matrix(bone,parent,rotation,sx,sy,name==='root'?translation:[0,0]);
    }
    const hip=[(world.thigh_l[4]+world.thigh_r[4])/2,(world.thigh_l[5]+world.thigh_r[5])/2];
    hipOrigin??=hip;
    const desired=[hipOrigin[0]+(centers[i][0]-centers[0][0])*ratio,hipOrigin[1]-(centers[i][1]-centers[0][1])*ratio];
    tracks.root.translate.push({time,x:translation[0]+desired[0]-hip[0],y:translation[1]+desired[1]-hip[1]});
  }
  return {animation:{bones:tracks},issues,source_snapshot:source.snapshot_sha256,
    scope:'raw_camera_pose_not_corrected_or_quality_accepted'};
}
