// Restore only correspondence for the exact live task and source topology.
const canonical=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
const equal=(a,b)=>canonical(a)===canonical(b);
export function restoreViewDraft(live,saved) {
  if(!saved?.view_pose||!equal(saved.request,live.request))throw Error('草稿来源或版本与当前任务不一致');
  const pose=saved.view_pose,base=live.view_pose,mesh=live.control_template;
  for(const key of ['document_sha256','slot','animation'])if(pose[key]!==base[key])throw Error('草稿不属于当前候选附件');
  const range=pose.interval;
  if(!Array.isArray(range)||range.length!==2||!range.every(Number.isFinite)||!(0<=range[0]&&range[0]<range[1]&&range[1]<=base.interval[1]))throw Error('草稿生效区间无效');
  if(!Array.isArray(pose.poses)||!pose.poses.length||pose.poses.length>512)throw Error('草稿姿态数量无效');
  const count=mesh.source_uv.length;
  if(count>12000)throw Error('控制点过多，暂不支持画布恢复');
  function points(values,uv){return Array.isArray(values)&&values.length===count&&values.every(p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&(!uv||(0<=v&&v<=1))));}
  let previous=range[0],uv=null;
  for(const row of pose.poses){
    if(!Number.isFinite(row.time)||row.time<=previous||row.time>=range[1])throw Error('草稿姿态时间必须有序且位于区间内部');
    previous=row.time;const c=row.correspondence;
    if(!c||c.mesh_sha256!==mesh.mesh_sha256||!equal(c.source_uv,mesh.source_uv)||!equal(c.triangles,mesh.triangles))throw Error('草稿控制网格已改变，不能恢复到此画布');
    if(!points(c.target_uv,true)||!points(c.target_xy,false))throw Error('草稿对应坐标无效');
    if(uv&&!equal(uv,c.target_uv))throw Error('各姿态必须使用相同贴图对应');uv=c.target_uv;
  }
  const result=structuredClone(live);
  result.view_pose=structuredClone(pose);
  result.control_template=structuredClone(pose.poses.at(-1).correspondence);
  return result;
}

export function bindViewTexture(template,digest,size) {
  const pose=template.view_pose;
  if((pose.texture_sha256&&pose.texture_sha256!==digest)||(pose.texture_size&&!equal(pose.texture_size,size)))throw Error('所选 PNG 与草稿使用的图片不一致');
  pose.texture_sha256=digest;pose.texture_size=[...size];
}
