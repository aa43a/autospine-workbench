// Interactive amplitude comparison of an immutable, already baked candidate.
// This is deliberately not the spring solver or the export/validation path.
const groups=['hair','cloth','objects'];
const names={hair:'发束',cloth:'裙袖',objects:'挂饰',face:'表情',loop:'循环',seed:'随机种子',fps:'采样率',
  stiffness:'刚度',damping:'阻尼',max_angle:'角度上限',root_fraction:'发根固定范围',cascade:'发束逐级跟随',anchor_x:'挂点',anchor_y:'挂点'};
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const selected=(config,slot)=>Boolean(config?.enabled)&&(!config.slots?.length||config.slots.includes(slot));
const local=(config,slot,key)=>config?.overrides?.[slot]?.[key]??config?.[key];

export function jointAmplitudePreview(document,report,config){
  const gains=new Map(),pending=new Set(),regions=report?.secondary?.regions??[],base=report?.config;
  if(!base||!config)return {gains,changed:false,pending:[],available:false,reason:'请先构建并载入联合候选，再实时比较摆动幅度。'};
  const bones=new Map((document.bones??[]).map(b=>[b.name,b]));
  const tracks=document.animations?.[report.animation]?.bones??{};
  for(const key of ['face','loop','seed','fps'])if(!same(base[key],config[key]))pending.add(names[key]);
  for(const group of groups){
    for(const key of ['stiffness','damping','max_angle','root_fraction','cascade','anchor_x','anchor_y'])
      if(!same(base[group]?.[key],config[group]?.[key]))pending.add(`${names[group]}${names[key]}`);
    const rows=regions.filter(r=>r.region_kind===group),generated=new Set(rows.map(r=>r.slot));
    for(const row of report.inventory?.[group]??[])if(row.state==='available'&&selected(config[group],row.slot)&&!generated.has(row.slot))
      pending.add(`${row.name||row.slot}尚未生成响应`);
    for(const row of rows){
      const slot=row.slot,desired=local(config[group],slot,'strength'),requested=row.requested_config?.strength;
      for(const key of ['stiffness','damping','max_angle','root_fraction','anchor_x','anchor_y'])
        if(!same(local(base[group],slot,key),local(config[group],slot,key)))pending.add(`${slot} ${names[key]}`);
      let gain=1;
      if(!selected(config[group],slot))gain=0;
      else if(!Number.isFinite(desired)||desired<0||desired>2)pending.add(`${slot}强度无效`);
      else if(desired===0)gain=0;
      else if(!Number.isFinite(requested)||requested<=0||row.post_solve_gain===0||row.effective_gain===0){
        if(desired!==requested)pending.add(`${slot}没有可缩放的响应，需重新构建`);
      }else if(row.motion_status==='static_driver_no_inertia'&&desired!==requested){
        pending.add(`${slot}原响应静止，调整强度不能产生新运动`);
      }else gain=desired/requested;
      for(const helper of row.helpers??[]){
        if(!/^m5-(hair|response|object)-/.test(helper)||!bones.has(helper)||!Array.isArray(tracks[helper]?.rotate)){
          pending.add(`${slot}响应骨骼不兼容`);continue;
        }
        // Leave body bones, deforms, UVs, textures and saved animation untouched.
        if(gains.has(helper)&&gains.get(helper)!==gain)throw Error('响应骨骼重复归属，无法即时预览。');
        gains.set(helper,gain);
      }
    }
  }
  return {gains,changed:[...gains.values()].some(v=>Math.abs(v-1)>1e-10),pending:[...pending],available:gains.size>0,
    reason:gains.size?'':'当前候选没有已生成的随动骨骼，请先构建所需通道。'};
}

export function applyJointAmplitude(skeleton,gains,setupRotations){
  if(!gains?.size)return;
  for(const bone of skeleton.bones){
    const name=bone.data.name,gain=gains.get(name);
    if(!/^m5-(hair|response|object)-/.test(name)||!Number.isFinite(gain)||gain<0||gain===1)continue;
    const setup=setupRotations.get(bone.data.name)??0;
    bone.pose.rotation=setup+(bone.pose.rotation-setup)*gain;
  }
}

export function jointPreviewText(preview){
  if(!preview)return '';
  const text=preview.changed?'即时幅度预览（未验证）：沿用已构建轨迹，仅缩放新增随动；完整求解和最终幅度以重新构建为准。':
    preview.available?'当前幅度与已构建结果一致。':preview.reason;
  return text+(preview.pending?.length?` 尚需构建：${preview.pending.slice(0,6).join('、')}${preview.pending.length>6?'等':''}。`:'');
}
