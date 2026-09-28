import {createJointState,isJointActive,canRetryJoint,jointDraft,jointDraftKey,restoreJointDraft} from './motion-joint-editor-state.js';
import {buildProgressText} from './motion-editor-build.js';
import {jointChecksum,validateJointResultRestore} from './motion-joint-editor-restore.js';

const validId=id=>/^motion-[a-f0-9]{32}$/.test(id);
const labels={pending:'已排队',queued:'已排队',running:'联合动画构建中',succeeded:'联合候选已生成（待检查）',failed:'构建失败',canceled:'已取消',cancelled:'已取消',interrupted:'构建已中断',outdated:'任务已不可用'};
const jointStages={joint_inventory:'检查角色通道与素材',joint_face:'生成面部动画',joint_secondary:'计算发束和裙袖响应',joint_validate:'核对连接与网格变形'};
const reasons={joint_animation_parent_unavailable:'身体动作候选尚不可用，请先选择构建成功的候选。',
  joint_animation_original_body_required:'请载入原始身体候选，联合动画会从该版本重新生成。',
  joint_animation_body_changed:'身体候选版本不匹配，请重新载入。',joint_animation_config_invalid:'联合动画参数不兼容，请检查关键帧和数值范围。',
  motion_queue_full:'当前构建队列已满，请等待已有任务完成后再试。',joint_animation_sample_limit:'联合动画采样量超限，请缩短身体动作片段。'};
function progressText(job){const stage=job.progress?.step||job.step;return buildProgressText({...job,step:jointStages[stage]||job.step,
  progress:{...job.progress,...(jointStages[stage]?{step:jointStages[stage]}:{})}});}
export function createJointWorkflow({getSelection=()=>null,notify=()=>{},inspect=()=>{},request=jointRequest,
  checksum=jointChecksum,storage=globalThis.localStorage,schedule=setTimeout,unschedule=clearTimeout}){
  const state=createJointState();let job=null,busy=false,message='',timer=null,selection=null,read=0,inspected=null;
  const currentSelection=()=>{const value=getSelection()??{};return JSON.stringify({project_id:value.project_id,
    source_id:value.source_id,character_job_id:value.character_job_id});};
  const token=()=>({epoch:state.epoch,selection});
  const current=t=>t.epoch===state.epoch&&t.selection===selection&&selection===currentSelection();
  const update=()=>notify(state,{busy,job,message});
  const error=e=>{message=e.message||String(e);update();};
  const taskKey=()=>`${jointDraftKey(state.meta)}:task`;
  function storeTask(){try{storage?.setItem(taskKey(),JSON.stringify({job_id:job.job_id,config:state.submitted}));}catch{/* The running task is still usable when storage is full. */}}
  function clearTimer(){if(timer!==null)unschedule(timer);timer=null;}
  function reset(){clearTimer();state.reset();selection=currentSelection();job=null;busy=false;message='载入身体候选后调整联合动画。';read++;inspected=null;update();}
  async function refresh(){
    if(!job||!state.meta)return;clearTimer();const t=token(),id=job.job_id,sequence=++read;
    try{
      const value=await request(`/api/motions/${id}`);
      if(!current(t)||job?.job_id!==id||sequence!==read)return;
      const next=value.job??value;
      if(next.job_id!==id||next.kind!=='adapt')throw Error('联合构建任务身份不一致。');
      job=next;state.result(next);message=`${labels[next.status]||next.status} · ${progressText(next)}${next.reason_code?' · '+(reasons[next.reason_code]||next.reason_code):''}`;
      storeTask();update();
      if(next.status==='succeeded'&&inspected!==id){inspected=id;try{await inspect(next);}catch(e){if(current(t))error(e);}}
    }catch(e){if(current(t)&&sequence===read){
      if([404,410].includes(e.status)){job={...job,status:'outdated'};state.result(job);message='上次任务已不存在，已保留其参数。可重新构建联合动画。';}
      else message=`暂时无法刷新任务：${e.message}。已有任务保留，可继续刷新。`;update();}}
    finally{if(current(t)&&job?.job_id===id&&sequence===read&&isJointActive(job))timer=schedule(refresh,2500);}
  }
  async function load(candidate,{restoreTask=true}={}){
    reset();const t=token();busy=true;message='正在读取身体候选与联合动画能力…';update();
    try{
      const registration=candidate.joint_registration_sha256;
      if(registration&&!/^[a-f0-9]{64}$/.test(registration))throw Error('身体修正候选身份无效。');
      const base=`/api/motions/${encodeURIComponent(candidate.job_id)}`;
      const meta=await request(registration?`${base}/related-candidates/${registration}/joint-animation`:`${base}/joint-animation`);
      if((meta.registration_sha256??null)!==(registration??null))throw Error('身体修正候选版本不匹配。');
      if(!current(t))return;state.load(meta,candidate);message='来源已就绪。调整参数后构建；历史身体动作保持原样。';
      try{
        const saved=restoreTask?JSON.parse(storage?.getItem(taskKey())||'null'):null;
        if(saved&&validId(saved.job_id)){state.set(saved.config);state.submit(saved.config);job={job_id:saved.job_id,kind:'adapt',status:'pending'};
          message='已恢复此身体候选上次构建的参数与任务，正在核对状态。';}
      }catch{message+=' 上次任务记录不兼容，未自动恢复。';}
    }catch(e){if(current(t))error(e);}
    finally{if(current(t)){busy=false;update();if(job)void refresh();}}
    return current(t)&&Boolean(state.meta);
  }
  async function restoreResult(candidate,report){
    if(!state.meta||busy||isJointActive(job))return false;
    const t=token();busy=true;message='正在核对联合候选、原身体与已保存参数…';update();
    try{
      if(!validId(candidate?.job_id))throw Error('联合候选任务身份无效。');
      const base=`/api/motions/${candidate.job_id}`;
      const parentBase=state.meta.preview_base||`/api/motions/${state.meta.parent_job_id}/view/player-assets/`;
      const [provenance,parent,joint]=await Promise.all([request(`${base}/view/joint-provenance.json`),
        checksum(`${parentBase}skeleton.json`),checksum(`${base}/view/player-assets/skeleton.json`)]);
      if(!current(t))return false;
      const config=validateJointResultRestore(candidate,report,state.meta,provenance,{parent,joint});
      state.set(config);state.submit(config);state.result(candidate);job=candidate;inspected=job.job_id;storeTask();
      message='已恢复此联合候选的精确参数与构建结果；修改后会创建新的独立候选。';update();
      await inspect(candidate);return current(t);
    }catch(e){if(current(t))error(e);return false;}
    finally{if(current(t)){busy=false;update();}}
  }
  function edit(callback){if(!state.meta||busy)return;try{callback();message=state.changed?'参数已修改，需重新构建；当前画布仍是已构建结果。':'参数已更新，构建后可在共用时间轴检查。';update();}catch(e){error(e);}}
  async function build(){
    if(!state.meta||busy||isJointActive(job))return;const t=token();busy=true;message='正在提交联合动画候选…';update();
    if(state.meta.eligibility?.supported===false){busy=false;message=state.meta.eligibility.message||state.meta.eligibility.reason||'当前身体候选暂不支持联合叠加。';update();return;}
    const config=structuredClone(state.config);
    try{
      const body={artifact_sha256:state.meta.artifact_sha256,config};
      if(state.meta.registration_sha256)body.registration_sha256=state.meta.registration_sha256;
      const value=await request(`/api/motions/${state.meta.parent_job_id}/joint-animation`,body);
      if(!current(t))return;const next=value.job??value;
      if(!validId(next.job_id))throw Error('未收到有效任务编号，请到动作库核对任务。');
      state.submit(config);job={...next,kind:'adapt',status:next.status||'pending'};storeTask();message='联合候选已提交，正在构建。';
    }catch(e){if(current(t))error(e);}
    finally{if(current(t)){busy=false;update();if(job&&isJointActive(job))void refresh();}}
  }
  async function operate(action){
    if(!job||busy||(action==='cancel'?!isJointActive(job):!canRetryJoint(job)))return;
    if(action==='retry'&&state.meta?.eligibility?.supported===false){message='当前身体候选暂不支持联合叠加，请选择兼容的身体候选。';update();return;}
    const t=token(),id=job.job_id;busy=true;clearTimer();read++;update();
    try{
      const value=await request(`/api/motions/${id}/${action}`,{});if(!current(t)||job?.job_id!==id)return;
      if(action==='retry'){
        const next=value.job??value;if(!validId(next.job_id)||next.job_id===id)throw Error('未创建独立重试任务，旧任务保留。');
        job={...next,kind:'adapt',status:next.status||'pending'};inspected=null;storeTask();
      }else{job={...job,cancel_requested:true};message='已请求取消，等待后台停止。';}
    }catch(e){if(current(t))error(e);}
    finally{if(current(t)){busy=false;update();void refresh();}}
  }
  return {state,load,restoreResult,reset,refresh,build,cancel:()=>operate('cancel'),retry:()=>operate('retry'),
    change:(group,key,value)=>edit(()=>state.change(group,key,value)),
    undo:()=>edit(()=>state.undo()),redo:()=>edit(()=>state.redo()),defaults:()=>edit(()=>state.defaults()),
    key:(channel,time,values)=>edit(()=>state.key(channel,time,values)),
    deleteKey:(channel,time)=>edit(()=>state.deleteKey(channel,time)),clearKeys:channel=>edit(()=>state.clearKeys(channel)),
    anchor:(slot,point)=>edit(()=>state.anchor(slot,point)),
    targets:(group,slots)=>edit(()=>state.targets(group,slots)),
    local:(group,slot,values)=>edit(()=>state.local(group,slot,values)),
    mouthAsset:value=>edit(()=>state.mouthAsset(value)),
    save(){try{if(!state.meta)return;storage.setItem(jointDraftKey(state.meta),JSON.stringify(jointDraft(state.meta,state.config)));message='联合动画草稿已保存，仅用于此身体候选版本。';update();}catch(e){error(Error(`草稿保存失败：${e.message}`));}},
    restore(){edit(()=>{const saved=JSON.parse(storage?.getItem(jointDraftKey(state.meta))||'null');if(!saved)throw Error('此身体候选还没有保存的联合草稿。');state.set(restoreJointDraft(saved,state.meta));});},
    close(){reset();},
  };
}
export async function jointRequest(url,body){
  const response=await fetch(url,body===undefined?{cache:'no-store'}:{method:'POST',
    headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok){const error=Error(reasons[value.reason_code]||value.message||value.reason_code||`请求失败 (${response.status})`);error.status=response.status;throw error;}return value;
}
