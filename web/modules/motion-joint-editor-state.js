import {createEditHistory} from './motion-editor-history.js';
import {windParameters} from './motion-wind-solver.js';

export const JOINT_SCHEMA='autospine.joint-animation-config/v1';
const jobId=/^motion-[a-f0-9]{32}$/,sha=/^[a-f0-9]{64}$/;
const groups=new Set(['face','hair','cloth','objects','wind']);
const clone=value=>structuredClone(value);
const pathParts=key=>{const parts=key.split('.');if(!parts.length||parts.some(p=>!p||['__proto__','constructor','prototype'].includes(p)))throw Error('无效的参数路径。');return parts;};
export function jointValue(object,key){return pathParts(key).reduce((value,part)=>value?.[part],object);}
export function setJointValue(object,key,value){const parts=pathParts(key),leaf=parts.pop();let target=object;
  for(const part of parts){if(!target?.[part]||typeof target[part]!=='object')throw Error('参数路径不存在。');target=target[part];}
  if(!Object.hasOwn(target??{},leaf))throw Error('参数不存在。');target[leaf]=value;
}
export const sameConfig=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export const isJointActive=job=>['pending','queued','running'].includes(job?.status);
export const canRetryJoint=job=>['failed','cancelled','canceled','interrupted'].includes(job?.status);
export const jointDraftKey=meta=>`autospine:joint-animation:${meta.parent_job_id}:${meta.artifact_sha256}`;
export const JOINT_CHANNELS={blink:['value'],gaze:['x','y'],brows:['lift','tilt'],mouth:['open','wide'],turn:['yaw','pitch']};
export const JOINT_LOCAL_LIMITS={strength:[0,2],stiffness:[9,100],damping:[.3,2],max_angle:[0,10],root_fraction:[.15,.75],anchor_x:[0,1],anchor_y:[0,1],wind_response:[0,2]};
export const localFieldAllowed=(group,key)=>key==='root_fraction'?group==='hair':key.startsWith('anchor_')?group==='objects':true;

export function validateJointCandidate(job){
  if(job?.kind!=='adapt'||job.status!=='succeeded'||!jobId.test(job.job_id)||!sha.test(job.result?.artifact_sha256))
    throw Error('请选择已经构建成功的身体动作候选。');
  return job;
}
export function validateJointConfig(value,meta){
  if(!value||value.schema!==JOINT_SCHEMA)throw Error('联合动画草稿格式不兼容。');
  value=clone(value);
  // Migrate only the newly added optional fields, after source identity checks.
  if(value.objects===undefined&&meta.defaults?.objects)value.objects=clone(meta.defaults.objects);
  if(value.hair&&value.hair.cascade===undefined&&meta.defaults?.hair?.cascade!==undefined)value.hair.cascade=false;
  if(meta.defaults?.wind){
    value.wind??=clone(meta.defaults.wind);
    for(const group of ['hair','cloth','objects'])if(value[group])value[group].wind_response??=meta.defaults[group]?.wind_response??1;
  }
  const result=clone(value);
  for(const c of meta.controls){
    if(!groups.has(c.group)||jointValue(result[c.group],c.key)===undefined)throw Error('联合动画参数定义不完整。');
    const v=jointValue(value[c.group],c.key);
    if(c.type==='boolean'){
      if(typeof v!=='boolean')throw Error(`${c.label}需要开关值。`);
    }else if(c.type==='number'){
      if(!Number.isFinite(v)||(Number.isFinite(c.min)&&v<c.min)||(Number.isFinite(c.max)&&v>c.max))throw Error(`${c.label}超出范围。`);
    }else throw Error('不支持的联合动画参数类型。');
    setJointValue(result[c.group],c.key,v);
  }
  if(!Number.isInteger(value.seed)||value.seed<0||value.seed>2147483647)throw Error('随机种子应为 0 至 2147483647 的整数。');
  if(![24,30,60].includes(value.fps))throw Error('采样帧率支持 24、30 或 60。');
  if(typeof value.loop!=='boolean')throw Error('循环设置无效。');
  if(value.face?.blink?.duration>=value.face?.blink?.period)throw Error('闭合周期应短于眨眼间隔。');
  result.seed=value.seed;result.fps=value.fps;result.loop=value.loop;
  if(value.cloth?.response_profile!==undefined&&!['helper-local-v1','material-falloff-v2'].includes(value.cloth.response_profile))
    throw Error('裙袖固定边缘过渡模式无效。');
  if(value.wind){
    const w=value.wind;
    if(w.schema!=='autospine.wind/v1'||!Number.isInteger(w.seed)||w.seed<0||w.seed>2147483647||
       Object.keys(w).some(k=>!['schema','enabled','strength','direction','gust','frequency','seed','keys','response_profile'].includes(k)))throw Error('风场参数格式无效。');
    if(w.response_profile!==undefined&&!['legacy-angular-v1','bounded-equilibrium-v2'].includes(w.response_profile))throw Error('受风模式无效。');
    if(!Array.isArray(w.keys)||w.keys.length>128)throw Error('风场最多保存 128 个关键帧。');
    let last=-1,stored=-1;
    for(const key of w.keys){
      if(Object.keys(key).sort().join(',')!=='direction,strength,time'||!Number.isFinite(key.time)||key.time<0||key.time>meta.duration||key.time<=last||Math.fround(key.time)<=stored)
        throw Error('风场关键帧时间无效或重复。');
      if(!Number.isFinite(key.strength)||key.strength<0||key.strength>100||!Number.isFinite(key.direction)||key.direction<0||key.direction>360)throw Error('风场关键帧数值超出范围。');
      last=key.time;stored=Math.fround(key.time);
    }
  }
  if(value.face?.anchors!==undefined){
    const anchors=value.face.anchors;if(!anchors||typeof anchors!=='object'||Array.isArray(anchors)||Object.keys(anchors).length>64)throw Error('面部锚点格式无效。');
    for(const [slot,point]of Object.entries(anchors)){
      if(!slot||slot.length>256||!Array.isArray(point)||point.length!==2||point.some(v=>!Number.isFinite(v)||Math.abs(v)>8192))throw Error('面部锚点坐标超出范围。');
    }
  }
  const mouthImage=value.face?.mouth?.template_image;
  if(mouthImage!==undefined&&mouthImage!==null&&(!mouthImage||typeof mouthImage!=='object'||
      Object.keys(mouthImage).sort().join(',')!=='png_base64,sha256'||!sha.test(mouthImage.sha256)||
      typeof mouthImage.png_base64!=='string'||mouthImage.png_base64.length>43692||!/^[A-Za-z0-9+/]+={0,2}$/.test(mouthImage.png_base64)))
    throw Error('嘴部替换图片格式无效，请重新上传 PNG。');
  for(const group of ['hair','cloth','objects']){
    const overrides=value[group]?.overrides;if(overrides===undefined)continue;
    if(!overrides||typeof overrides!=='object'||Array.isArray(overrides)||Object.keys(overrides).length>64)throw Error('局部响应参数格式无效。');
    for(const [slot,values]of Object.entries(overrides)){
      if(!meta.inventory?.[group]?.some(row=>row.slot===slot&&row.state==='available'))throw Error('局部响应区域与当前角色不一致。');
      if(!values||typeof values!=='object'||Array.isArray(values))throw Error('局部响应参数格式无效。');
      for(const [key,v]of Object.entries(values)){
        const bounds=JOINT_LOCAL_LIMITS[key];
        if(!bounds||!localFieldAllowed(group,key)||!Number.isFinite(v)||v<bounds[0]||v>bounds[1])throw Error('局部响应参数超出范围。');
      }
    }
  }
  for(const [channel,fields]of Object.entries(JOINT_CHANNELS)){
    const keys=value.face?.[channel]?.keys;if(keys===undefined)continue;
    if(!Array.isArray(keys)||keys.length>256)throw Error('每个面部通道最多保存 256 个关键帧。');
    let last=-1,lastStored=-1;
    for(const key of keys){
      if(!Number.isFinite(key.time)||key.time<0||key.time>meta.duration||key.time<=last||Math.fround(key.time)<=lastStored)throw Error('关键帧时间无效或重复。');last=key.time;lastStored=Math.fround(key.time);
      for(const field of fields){
        const c=meta.controls.find(c=>c.group==='face'&&c.key===`${channel}.${field}`);
        const min=c?.min??(channel==='blink'?0:-1),max=c?.max??1;
        if(!Number.isFinite(key[field])||key[field]<min||key[field]>max)throw Error(`${channel}关键帧数值超出范围。`);
      }
    }
  }
  return result;
}
export function validateJointMetadata(meta,job){
  validateJointCandidate(job);
  if(meta?.parent_job_id!==job.job_id||meta.artifact_sha256!==job.result.artifact_sha256)
    throw Error('身体候选版本已变化，请重新加载。');
  if(!Number.isFinite(meta.duration)||meta.duration<=0||!Array.isArray(meta.controls))throw Error('联合动画能力信息不完整。');
  validateJointConfig(meta.defaults,meta);return meta;
}
export function jointDraft(meta,config){
  return {schema:'autospine.joint-animation-draft/v1',parent_job_id:meta.parent_job_id,
    artifact_sha256:meta.artifact_sha256,config:validateJointConfig(config,meta)};
}
export function restoreJointDraft(value,meta){
  if(value?.schema!=='autospine.joint-animation-draft/v1'||value.parent_job_id!==meta.parent_job_id||value.artifact_sha256!==meta.artifact_sha256)
    throw Error('草稿属于不同的身体候选或版本，未应用。');
  return validateJointConfig(value.config,meta);
}
export function createJointState(){
  const history=createEditHistory();
  let meta=null,config=null,submitted=null,result=null,epoch=0;
  return {
    reset(){epoch++;meta=null;config=null;submitted=null;result=null;history.reset();return epoch;},
    load(value,job){meta=validateJointMetadata(value,job);config=clone(meta.defaults);submitted=null;result=null;history.reset();},
    set(value){const next=validateJointConfig(value,meta);if(sameConfig(next,config))return false;history.record(config);config=next;return true;},
    change(group,key,value){const next=clone(config);setJointValue(group?next[group]:next,key,value);return this.set(next);},
    windParameter(key,value,time){
      if(!['strength','direction'].includes(key))return this.change('wind',key,value);
      const next=clone(config);next.wind[key]=value;
      if(next.wind.keys.length){
        if(!Number.isFinite(time)||time<0||time>meta.duration)throw Error('关键帧时间超出身体动作范围。');
        const [strength,direction]=windParameters(config.wind,time),t=Math.min(meta.duration,Math.round(time*1e6)/1e6);
        const entry={time:t,strength,direction:((direction%360)+360)%360,[key]:value};
        next.wind.keys=next.wind.keys.filter(k=>k.time!==t).concat(entry).sort((a,b)=>a.time-b.time);
      }
      return this.set(next);
    },
    windProfile(value){const next=clone(config);next.wind.response_profile=value;return this.set(next);},
    clothProfile(value){const next=clone(config);next.cloth.response_profile=value;return this.set(next);},
    defaults(){return this.set(meta.defaults);},
    undo(){const previous=history.undo(config);if(previous)config=previous;},
    redo(){const next=history.redo(config);if(next)config=next;},
    submit(value=config){submitted=validateJointConfig(value,meta);result=null;return clone(submitted);},
    key(channel,time,values){
      const fields=channel==='wind'?['strength','direction']:JOINT_CHANNELS[channel];if(!fields)throw Error('不支持的动画通道。');
      if(!Number.isFinite(time)||time<0||time>meta.duration)throw Error('关键帧时间超出身体动作范围。');
      const next=clone(config),entry={time:Math.min(meta.duration,Math.round(time*1e6)/1e6)};for(const field of fields)entry[field]=values[field];
      const target=channel==='wind'?next.wind:next.face[channel];
      target.keys=(target.keys??[]).filter(k=>k.time!==entry.time).concat(entry).sort((a,b)=>a.time-b.time);return this.set(next);
    },
    deleteKey(channel,time){const next=clone(config),t=Math.min(meta.duration,Math.round(time*1e6)/1e6);
      const target=channel==='wind'?next.wind:next.face[channel];
      target.keys=(target.keys??[]).filter(k=>k.time!==t);return this.set(next);},
    clearKeys(channel,time=0){const next=clone(config),target=channel==='wind'?next.wind:next.face[channel];
      if(channel==='wind'){const [strength,direction]=windParameters(config.wind,time);Object.assign(target,{strength,direction:((direction%360)+360)%360});}
      target.keys=[];return this.set(next);},
    enableWind(){const next=clone(config);next.wind.enabled=true;next.wind.response_profile='bounded-equilibrium-v2';
      for(const group of ['hair','cloth','objects']){
        const rows=meta.inventory?.[group]??[],available=rows.filter(r=>r.state==='available');
        if(available.length){next[group].enabled=true;
          if(!next[group].slots?.length&&available.length!==rows.length)next[group].slots=available.map(r=>r.slot).sort();}
      }
      return this.set(next);},
    anchor(slot,point){
      if(!meta.inventory?.face?.parts?.some(part=>part.available&&part.slot===slot))throw Error('面部图层不属于当前候选的可用范围。');
      const next=clone(config);next.face.anchors??={};
      if(point===null)delete next.face.anchors[slot];else next.face.anchors[slot]=point;return this.set(next);
    },
    targets(group,slots){
      if(!['hair','cloth','objects'].includes(group))throw Error('不支持的响应区域。');
      const available=(meta.inventory?.[group]??[]).filter(row=>row.state==='available').map(row=>row.slot);
      if(!slots.length)throw Error('至少保留一个区域；要关闭此效果，请关闭整个响应通道。');
      if(slots.some(slot=>!available.includes(slot))||new Set(slots).size!==slots.length)throw Error('响应区域与当前角色不一致。');
      const next=clone(config);next[group].slots=slots.length===available.length?[]:[...slots].sort();return this.set(next);
    },
    local(group,slot,values){
      if(!['hair','cloth','objects'].includes(group)||!meta.inventory?.[group]?.some(row=>row.slot===slot&&row.state==='available'))throw Error('局部响应区域与当前角色不一致。');
      const next=clone(config);next[group].overrides??={};
      if(values===null||!Object.keys(values).length)delete next[group].overrides[slot];else next[group].overrides[slot]=clone(values);return this.set(next);
    },
    mouthAsset(value){const next=clone(config);next.face.mouth.template_image=value;return this.set(next);},
    result(job){result=job;},
    get epoch(){return epoch;},get meta(){return meta;},get config(){return config;},
    get resultJob(){return result;},get submitted(){return submitted;},
    get changed(){return Boolean(submitted)&&!sameConfig(config,submitted);},
    get canUndo(){return history.canUndo;},get canRedo(){return history.canRedo;},
  };
}
