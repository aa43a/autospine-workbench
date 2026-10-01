import {windVectors,angularWind,springSolve,bakeSpring,lookup,helperPose} from './motion-wind-solver.js';
const groups=['hair','cloth','objects'];
const same=(a,b)=>{
  if(a===b)return true;
  if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;
  const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&same(a[k],b[k]));
};
const chosen=(cfg,slot)=>cfg?.enabled&&(!cfg.slots?.length||cfg.slots.includes(slot));
const local=(cfg,slot,key)=>cfg?.overrides?.[slot]?.[key]??cfg?.[key];
export function windPreviewGain(record,report,config){
  if(config.wind?.response_profile!=='bounded-equilibrium-v2'||report.config.wind?.response_profile==='bounded-equilibrium-v2')return record.post_solve_gain;
  const history=report.secondary?.geometry_guard?.find(row=>row.slot===record.slot)?.history??[];
  // Upgrade an old template only through a gain already measured to satisfy
  // the mesh limits. This removes a projected-overlap clamp, never fabricates
  // approval for a previously unsafe triangle or edge stretch.
  const measured=history.find(row=>row.min_area_ratio>=.55&&row.max_area_ratio<=1.9&&row.max_edge_stretch<=1.9);
  return measured?Math.max(record.post_solve_gain,measured.gain):record.post_solve_gain;
}
export function validateWindTemplate(template,report,document){
  if(template?.schema!=='autospine.wind-preview/v1'||template.skeleton_sha256!==report.skeleton_sha256||
    template.parent_skeleton_sha256!==report.parent_skeleton_sha256||template.config_sha256!==report.config_sha256)throw Error('受风预览来源不匹配，请重新载入候选。');
  const ticks=template.times,n=ticks?.length;
  if(!Array.isArray(ticks)||n<3||n>14403||ticks[0]!==0||Math.abs(ticks.at(-1)-report.duration)>1e-9||
    ticks.some((t,i)=>!Number.isFinite(t)||i>0&&Math.abs(t-ticks[i-1]-(ticks[1]-ticks[0]))>1e-8))throw Error('受风预览采样无效。');
  const available=new Set((document.bones??[]).map(b=>b.name)),owners=new Set();
  if(!template.regions?.length||template.regions.length>72)throw Error('受风预览区域无效。');
  for(const row of template.regions){
    if(!groups.includes(row.region_kind)||!Number.isFinite(row.post_solve_gain)||row.post_solve_gain<0||row.post_solve_gain>1||
      !Number.isFinite(row.wind_axis_offset)||!Array.isArray(row.helpers)||row.helpers.length>12)throw Error('受风预览区域无效。');
    for(const helper of row.helpers){const bone=template.bones?.[helper];
      if(!/^m5-(hair|response|object)-/.test(helper)||!available.has(helper)||owners.has(helper)||!bone||!available.has(bone.parent))throw Error('受风响应骨骼不兼容。');
      owners.add(helper);
      for(const name of [helper,bone.parent])if(!Array.isArray(template.matrices?.[name])||template.matrices[name].length!==n||
        template.matrices[name].some(m=>!Array.isArray(m)||m.length!==6||m.some(v=>!Number.isFinite(v))))throw Error('受风预览缺少原始运动轨迹。');
    }
  }
  return template;
}
export function jointWindPreview(template,report,config,{noWind=false}={}){
  const times=template.times,wind={...config.wind,enabled:noWind?false:config.wind.enabled},vectors=windVectors(wind,times,config.loop);
  const tracks=new Map(),pending=new Set(),regions=template.regions,bones=template.bones;
  const frames=times.map((t,i)=>Object.fromEntries(Object.entries(template.matrices).map(([name,matrices])=>[name,matrices[i]])));
  for(const group of groups){const generated=new Set(regions.filter(r=>r.region_kind===group).map(r=>r.slot));
    for(const row of report.inventory?.[group]??[])if(row.state==='available'&&chosen(config[group],row.slot)&&!generated.has(row.slot))pending.add(`${row.name||row.slot}需先生成受风骨骼`);}
  for(const key of ['face','fps','seed'])if(!same(report.config[key],config[key]))pending.add(key==='face'?'表情改动':key==='fps'?'采样率':'表情随机种子');
  for(const record of regions){const cfg=config[record.region_kind],slot=record.slot,solved={};
    for(const key of ['root_fraction','anchor_x','anchor_y'])if(!same(local(cfg,slot,key),record.requested_config[key]))pending.add(`${slot}固定根部或挂点`);
    for(const helper of record.helpers){
      const bone=bones[helper],driven=record.region_kind==='cloth'?bone.parent:helper;
      const poses=times.map((t,i)=>{
        let base=frames[i];
        if(record.region_kind==='hair'&&cfg.cascade&&Object.keys(solved).length)
          base=helperPose(base,bones,record.helpers,Object.fromEntries(record.helpers.map(n=>[n,solved[n]?.[i]??0])));
        const m=base[driven];return [m[4],m[5],Math.atan2(m[2],m[0])*180/Math.PI];});
      const length=bone.length??100,external=angularWind(vectors.values,poses,{axis_offset:record.wind_axis_offset,
        response:local(cfg,slot,'wind_response')??1,length,profile:config.wind.response_profile,
        stiffness:local(cfg,slot,'stiffness'),max_angle:local(cfg,slot,'max_angle')});
      const values=springSolve(times,poses,{stiffness:local(cfg,slot,'stiffness'),damping:local(cfg,slot,'damping'),
        strength:local(cfg,slot,'strength')*((helper.endsWith('-lower')||helper.endsWith('_lower')) ? .5 : 1),
        max_angle:local(cfg,slot,'max_angle'),length,loop:config.loop,external,compatible:vectors.compatible});
      const baked=bakeSpring(times,values);solved[helper]=times.map(t=>lookup(baked.times,baked.values,t));
      const gain=chosen(cfg,slot)?windPreviewGain(record,report,config):0;
      tracks.set(helper,{times:baked.times,values:baked.values.map(v=>v*gain)});
    }
  }
  const changed=noWind||!same(report.config.wind,config.wind)||groups.some(g=>!same(report.config[g],config[g]))||report.config.loop!==config.loop;
  if(changed)pending.add('新参数的网格、接触与 Runtime 验证');
  if(config.loop&&!vectors.compatible)pending.add('风场首尾方向或强度不连续');
  return {tracks,changed,pending:[...pending],available:tracks.size>0,mode:'wind_solver',noWind,initial_from_rest:!config.loop,
    regions:regions.map(record=>{
      const guard=report.secondary?.geometry_guard?.find(row=>row.slot===record.slot),measured=guard?.history?.at(-1);
      return {slot:record.slot,kind:record.region_kind,
        gain:chosen(config[record.region_kind],record.slot)?windPreviewGain(record,report,config):0,
        built_projected_overlap:guard?.collision?.policy==='diagnostic'&&measured?.collision_failed_samples>0};
    }),
    reason:tracks.size?'':'当前候选没有可用的受风骨骼。'};
}
export function windOffsets(preview,time){
  return preview?.tracks?new Map([...preview.tracks].map(([name,track])=>[name,lookup(track.times,track.values,time)])):null;
}
export function applyWindOffsets(skeleton,offsets,setup){
  if(!offsets)return;for(const bone of skeleton.bones){const name=bone.data.name,offset=offsets.get(name);
    if(/^m5-(hair|response|object)-/.test(name)&&Number.isFinite(offset))bone.pose.rotation=(setup.get(name)??0)+offset;}
}
