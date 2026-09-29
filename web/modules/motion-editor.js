import {createSourcePlayer} from './motion-source-player.js';
import {projectOptionLabel} from './project-option-label.js';
import {sampleYaw,validateYawTrack,yawSurfaceWarning} from './motion-yaw-track.js';
import {DRAFT_SCHEMA,matchEditorDraft,createEditorDraftControls} from './motion-editor-draft.js';
import {createEditorBuild} from './motion-editor-build.js';
import {createLiveCharacter} from './motion-editor-live.js';
import {createEditorIntake} from './motion-editor-intake.js';
import {createEditorResult,resultTrack} from './motion-editor-result.js';
import {createJointEditor} from './motion-joint-editor.js';
import {SAMPLING_PROFILE} from './motion-camera-sampling.js';
import {PROJECTED_SAMPLING_PROFILE} from './motion-projected-camera-sampling.js';
import {createEditHistory} from './motion-editor-history.js';
import {createLayerEditor} from './motion-editor-layers.js';
const $=id=>document.getElementById(id);
const get=async url=>{const r=await fetch(url);if(!r.ok)throw Error(`读取失败 (${r.status})`);return r.json();};
let keys=[{time:0,yaw:0}],fixed=0,sourceToken=0,projectToken=0,duration=0,lastYaw=null,lastTime=null,override=null;
let characterJob=null,loadedSource=null,sourceData=null,resultView=null,layers=null,joint=null;
let bodyCandidates=[],candidateToken=0;
let variantToken=0;
$('body-candidate').onchange=async()=>{
  const token=++variantToken,id=$('body-candidate').value;++candidateToken;
  $('body-variant').replaceChildren(new Option('主候选',''));
  $('load-body-candidate').disabled=false;
  if(!id)return;
  try{const value=await get(`/api/motions/${id}/view/related-candidates.json`);
    if(token!==variantToken||$('body-candidate').value!==id)return;
    for(const row of value.rows){const accepted=row.stage_review?.current?.decision;
      $('body-variant').add(new Option(`修正候选 · ${row.registration_sha256.slice(0,8)}${accepted?' · '+accepted:''}`,row.registration_sha256));}
  }catch(e){if(token===variantToken)$('body-candidate-status').textContent=`修正版本读取失败：${e.message}；主候选仍可载入。`;}
};
$('body-variant').onchange=()=>{++candidateToken;$('load-body-candidate').disabled=false;};
const history=createEditHistory();
const editState=()=>({keys,fixed,override,adaptive:$('adaptive-camera').checked,version:$('sampling-version').value,layer_edits:layers?.snapshot()??null});
function historyControls(){$('undo-edit').disabled=!history.canUndo;$('redo-edit').disabled=!history.canRedo;}
function remember(){history.record(editState());historyControls();}
function restoreEdit(value){if(!value)return;({keys,fixed,override}=value);$('adaptive-camera').checked=value.adaptive;
  layers.restore(value.layer_edits??null);
  $('sampling-version').value=value.version;
  const time=Number($('time').value),yaw=override??(keys.length>1?sampleYaw(keys,time):fixed);
  lastYaw=yaw;player.setView(yaw);$('yaw-value').value=yaw;$('yaw').value=((yaw%360)+360)%360;
  $('surface').textContent=yawSurfaceWarning(yaw);
  keySummary();seekLive(time);resultView?.seek(time);historyControls();}
$('undo-edit').onclick=()=>restoreEdit(history.undo(editState()));
$('redo-edit').onclick=()=>restoreEdit(history.redo(editState()));
const live=createLiveCharacter($('character-canvas'),$('character-status'));
const currentKeys=()=>override!==null?[{time:0,yaw:override}]:keys.length>1?keys:[{time:0,yaw:fixed}];
const sampling=()=>{const track=currentKeys();if(!$('adaptive-camera').checked)return null;
  if($('sampling-version').value===PROJECTED_SAMPLING_PROFILE)return PROJECTED_SAMPLING_PROFILE;
  return Math.abs(track[0].yaw)>90||track.some(k=>k.yaw!==track[0].yaw)?SAMPLING_PROFILE:null;};
const seekLive=time=>live.seek(time,currentKeys(),sampling());
const player=createSourcePlayer($('source-canvas'),$('time'),$('play'),$('clock'),time=>{
  if(time!==lastTime){override=null;lastTime=time;}
  const yaw=override??(keys.length>1?sampleYaw(keys,time):fixed);
  if(yaw!==lastYaw){lastYaw=yaw;player.setView(yaw);}
  $('surface').textContent=yawSurfaceWarning(yaw);
  if(keys.length>1){$('yaw-value').value=yaw.toFixed(2);$('yaw').value=((yaw%360)+360)%360;}
  seekLive(time);
  resultView?.seek(time);
  joint?.seek(time);
},{maxYaw:3600,interpolateFrames:true});
layers=createLayerEditor({live,beforeChange:remember,changed:()=>resultView?.seek(Number($('time').value)),
  pause:()=>player.seek(Number($('time').value))});
function keySummary(){ $('keys').textContent=keys.length>1?keys.map(k=>`${k.time.toFixed(3)} 秒：${k.yaw}°`).join(' → '):`固定角度 ${fixed}°`; }
function changeAngle(value){
  if(!Number.isFinite(value)||Math.abs(value)>3600)return;
  if(value===(override??(keys.length>1?sampleYaw(keys,Number($('time').value)):fixed)))return;
  remember();
  player.seek(Number($('time').value));override=value;fixed=value;lastYaw=value;player.setView(value);
  $('yaw-value').value=value;$('yaw').value=((value%360)+360)%360;
  $('surface').textContent=yawSurfaceWarning(value);
  keySummary();
  seekLive(Number($('time').value));resultView?.seek(Number($('time').value));
  if(keys.length>1)$('status').textContent='当前角度尚未写入轨道；请点击“在当前时间记录角度”，或恢复固定角度后再保存、构建。';
}
$('yaw').oninput=()=>changeAngle(Number($('yaw').value));
$('yaw-value').onchange=()=>changeAngle(Number($('yaw-value').value));
$('key').onclick=()=>{
  const time=Number($('time').value),yaw=Number($('yaw-value').value);
  try{
    const next=keys.filter(k=>k.time!==time).concat({time,yaw}).sort((a,b)=>a.time-b.time);
    validateYawTrack(next,duration);remember();keys=next;override=null;keySummary();seekLive(time);resultView?.seek(time);
  }catch(e){$('status').textContent=e.message;}
};
$('clear-keys').onclick=()=>{const value=Number($('yaw-value').value);if(!Number.isFinite(value)||Math.abs(value)>3600)return;
  remember();
  fixed=value;keys=[{time:0,yaw:fixed}];override=null;keySummary();seekLive(Number($('time').value));resultView?.seek(Number($('time').value));};
$('adaptive-camera').onchange=()=>{seekLive(Number($('time').value));resultView?.seek(Number($('time').value));};
$('sampling-version').onchange=()=>{seekLive(Number($('time').value));resultView?.seek(Number($('time').value));};
$('source').onchange=async()=>{
  joint?.reset();
  const token=++sourceToken,id=$('source').value;player.clear();duration=0;
  loadedSource=null;sourceData=null;resultView?.seek(0);
  history.reset();historyControls();
  live.source(null);
  $('key').disabled=$('clear-keys').disabled=true;keys=[{time:0,yaw:0}];fixed=0;lastYaw=null;override=null;lastTime=null;
  $('yaw-value').value=$('yaw').value=0;keySummary();
  if(!id)return;
  $('status').textContent='正在加载源动作…';
  try{const value=await get(`/api/motions/${encodeURIComponent(id)}/editor-source`);if(token!==sourceToken)return;
    duration=value.duration;loadedSource=id;sourceData=value;live.source(value);player.load(value.preview);$('key').disabled=$('clear-keys').disabled=false;
    $('status').textContent='源动作已加载。旋转角度或拖动时间轴，右侧实时映射角色姿态。';
  }catch(e){if(token===sourceToken)$('status').textContent=e.message;}
};
async function loadProject(exactJob=null){
  joint?.reset();
  layers.reset();history.reset();historyControls();
  const token=++projectToken,id=$('project').value;live.clear();
  characterJob=null;resultView?.seek(Number($('time').value));
  if(!id){$('character-status').textContent='选择角色后加载已保存候选。';return;}$('character-status').textContent='正在核对角色绑定…';
  try{const [value,project]=await Promise.all([
    exactJob?{job:{status:'needs_review',job_id:exactJob}}:get(`/api/projects/${encodeURIComponent(id)}/automation/character/motion-target`),
    get(`/api/projects/${encodeURIComponent(id)}`)]);if(token!==projectToken)return;
    if(value.job?.status!=='needs_review')throw Error('请先在角色工作台构建整角色候选。');
    const artifact=await live.load(`/api/projects/${encodeURIComponent(id)}/automation/character/jobs/${encodeURIComponent(value.job.job_id)}/view/player-assets/`);
    if(token!==projectToken||!artifact)return;characterJob=value.job.job_id;
    const sourceNames=new Map((project.layers??[]).map(layer=>[`layer-${String(layer.source_index).padStart(3,'0')}`,layer.name]));
    const labels=Object.fromEntries(live.layers().map(layer=>{
      const prefix=layer.slot.match(/^layer-\d+/)?.[0],name=sourceNames.get(prefix);
      return [layer.slot,name?`${name} · ${layer.slot}`:layer.slot];
    }));
    layers.loaded(labels);seekLive(Number($('time').value));resultView?.seek(Number($('time').value));
  }catch(e){if(token===projectToken)$('character-status').textContent=e.message;}
};
$('project').onchange=()=>loadProject();
async function refresh(){
  $('refresh').disabled=true;
  try{const value=await get('/api/motions'),selected=$('source').value;
    bodyCandidates=value.jobs.filter(j=>j.kind==='adapt'&&j.status==='succeeded'&&!j.result?.joint_animation_profile);
    const picked=$('body-candidate').value;
    $('body-candidate').replaceChildren(new Option('选择已完成的身体动作',''));
    for(const j of bodyCandidates)$('body-candidate').add(new Option(`${j.project_id} · ${j.name} · ${j.job_id.slice(-6)}`,j.job_id));
    if(bodyCandidates.some(j=>j.job_id===picked))$('body-candidate').value=picked;
    intake.update(value);
    $('source').replaceChildren(new Option('选择已解析动作',''));
    for(const job of value.jobs)if(job.kind!=='adapt'&&job.status==='succeeded'&&job.result?.motion_status==='compiled')
      $('source').add(new Option(`${job.name} · ${job.job_id.slice(-6)}`,job.job_id));
    if([...$('source').options].some(o=>o.value===selected))$('source').value=selected;
    else if(selected){$('source').value='';await $('source').onchange();}
    $('status').textContent='动作库已更新；请选择角色与源动作。';
  }catch(e){$('status').textContent=e.message;}finally{$('refresh').disabled=false;}
}
$('refresh').onclick=refresh;
const intake=createEditorIntake({refresh,async load(id){
  if(![...$('source').options].some(o=>o.value===id))throw Error('动作尚未完成解析，请刷新任务');
  $('source').value=id;await $('source').onchange();
}});
const projectsReady=get('/api/projects').then(value=>{for(const p of value.projects)$('project').add(new Option(projectOptionLabel(p,value.projects),p.id));});
const libraryReady=refresh();projectsReady.catch(e=>{$('status').textContent=e.message;});
$('surface').textContent=yawSurfaceWarning(0);
function identity(){const edits=layers.snapshot();return {project_id:$('project').value,source_id:loadedSource,character_job_id:characterJob,duration,...(edits?{layer_edits:edits}:{}),...(sampling()?{sampling_profile:sampling()}:{})};}
function snapshot(){if(!loadedSource||!characterJob)throw Error('请先完成角色和源动作加载');
  if(override!==null&&keys.length>1)throw Error('当前角度尚未写入轨道，请先记录角度或恢复固定角度');
  return {schema:DRAFT_SCHEMA,...identity(),time:Number($('time').value),keys:keys.length>1?keys:[{time:0,yaw:fixed}]};}
resultView=createEditorResult({canvas:$('result-canvas'),status:$('result-status'),
  viewport:value=>live.viewport(value),
  selection:()=>({source:sourceData,identity:identity(),keys:currentKeys()}),
  async restore(job,link,track,current){
    if(![...$('source').options].some(o=>o.value===link.source_job_id)||![...$('project').options].some(o=>o.value===job.project_id))
      throw Error('来源未在列表中，请刷新动作库后重试');
    $('source').value=link.source_job_id;
    const initialProject=projectToken;
    await $('source').onchange();
    if(!current()||loadedSource!==link.source_job_id||projectToken!==initialProject)throw Error('选择已变化或源动作加载失败，停止恢复');
    const initialSource=sourceToken;$('project').value=job.project_id;await loadProject(job.character_job_id);
    if(!current()||sourceToken!==initialSource||characterJob!==job.character_job_id||$('project').value!==job.project_id)throw Error('选择已变化或角色版本加载失败，停止恢复');
    keys=validateYawTrack(track,duration);fixed=keys[0].yaw;override=null;lastYaw=null;lastTime=null;$('adaptive-camera').checked=Boolean(job.result.projection?.sampling_profile);
    $('sampling-version').value=job.result.projection?.sampling_profile||SAMPLING_PROFILE;
    layers.restore(job.result.layer_edits??null);
    $('yaw-value').value=fixed;$('yaw').value=((fixed%360)+360)%360;keySummary();player.seek(0);
  }});
function inspectResult(job){$('result-viewport').hidden=false;document.querySelector('.canvases').append($('result-viewport'));
  const loading=resultView.load(job);document.querySelector('.canvases').scrollIntoView({block:'start'});return loading;}
joint=createJointEditor({container:$('joint-editor'),getSelection:identity,inspect:inspectResult,seek:time=>player.seek(time),
  preview:value=>resultView.jointPreview(value)});
createEditorBuild({snapshot,inspect(job){inspectResult(job);if(!job.result?.joint_animation_profile)void joint.load(job);}});
$('load-body-candidate').onclick=async({restoreTask=true}={})=>{
  let job=bodyCandidates.find(j=>j.job_id===$('body-candidate').value);if(!job)return;
  const registration=$('body-variant').value;
  const token=++candidateToken;$('load-body-candidate').disabled=true;
  const startingSource=sourceToken,startingProject=projectToken;
  $('body-candidate-status').textContent='正在载入候选的准确角色版本和身体动作…';
  try{
    let link;
    if(registration){const meta=await get(`/api/motions/${job.job_id}/related-candidates/${registration}/joint-animation`);
      if(meta.registration_sha256!==registration)throw Error('修正候选身份不一致');
      job={...job,joint_registration_sha256:registration,result:{...job.result,artifact_sha256:meta.artifact_sha256}};link=meta.source_link;
    }else link=await get(`/api/motions/${job.job_id}/view/source-link.json`);
    const track=resultTrack(job,link);
    if(token!==candidateToken||startingSource!==sourceToken||startingProject!==projectToken)throw Error('选择已变化，停止载入旧候选');
    if(![...$('source').options].some(o=>o.value===link.source_job_id))throw Error('源动作不在动作库中，请刷新后重试');
    $('source').value=link.source_job_id;await $('source').onchange();
    if(token!==candidateToken||loadedSource!==link.source_job_id||startingProject!==projectToken)throw Error('源动作或角色选择已变化');
    const sourceVersion=sourceToken;$('project').value=job.project_id;await loadProject(job.character_job_id);
    if(token!==candidateToken||sourceVersion!==sourceToken||characterJob!==job.character_job_id)throw Error('角色或来源已变化');
    keys=track;fixed=track[0].yaw;override=null;lastYaw=null;
    $('yaw-value').value=fixed;$('yaw').value=((fixed%360)+360)%360;
    $('adaptive-camera').checked=Boolean(job.result.projection?.sampling_profile);
    $('sampling-version').value=job.result.projection?.sampling_profile||SAMPLING_PROFILE;
    layers.restore(job.result.layer_edits??null);keySummary();player.seek(0);
    inspectResult(job);await joint.load(job,{restoreTask});
    $('body-candidate-status').textContent=`身体候选 ${job.name} 已载入；联合能力与参数读取状态见下方。`;
  }catch(e){if(token===candidateToken)$('body-candidate-status').textContent=e.message;}
  finally{if(token===candidateToken)$('load-body-candidate').disabled=false;}
};
createEditorDraftControls({snapshot,
  async restore(draft){
    // Verify against currently loaded identities before replacing any edits.
    if(!loadedSource||!characterJob)throw Error(`请先选择草稿角色 ${draft.project_id} 和动作 ${draft.source_id}，再恢复草稿`);
    const current=identity(),tokens=[sourceToken,projectToken];
    const target=await get(`/api/projects/${encodeURIComponent(current.project_id)}/automation/character/motion-target`);
    if(tokens[0]!==sourceToken||tokens[1]!==projectToken)throw Error('选择已变化，请重试恢复草稿');
    const value=matchEditorDraft(draft,{...current,character_job_id:target.job?.job_id});
    remember();
    layers.restore(value.layer_edits??null);
    keys=value.keys;fixed=keys[0].yaw;override=null;lastYaw=null;lastTime=null;$('adaptive-camera').checked=Boolean(value.sampling_profile);
    $('sampling-version').value=value.sampling_profile||SAMPLING_PROFILE;player.seek(value.time);
    const yaw=sampleYaw(keys,value.time);$('yaw-value').value=yaw;$('yaw').value=((yaw%360)+360)%360;keySummary();
    $('status').textContent='草稿已恢复，角色版本和源动作一致。';
  },status:text=>{$('status').textContent=text;},
});
// An exact saved joint result can be reopened for editing without relying on
// browser-local drafts or migrating another candidate's acceptance.
void Promise.all([projectsReady,libraryReady]).then(async()=>{
  const id=new URLSearchParams(location.search).get('joint');if(!id)return;
  if(!/^motion-[a-f0-9]{32}$/.test(id))throw Error('联合候选地址无效');
  const value=await get(`/api/motions/${id}`),saved=value.job??value;
  if(saved.kind!=='adapt'||saved.status!=='succeeded'||!saved.result?.joint_animation_profile)throw Error('此联合候选尚未构建成功');
  const parent=saved.result.joint_parent_job_id,registration=saved.result.joint_source_provenance?.registration_sha256;
  if(!bodyCandidates.some(j=>j.job_id===parent))throw Error('联合候选的身体来源已不可用');
  $('body-candidate').value=parent;await $('body-candidate').onchange();
  if(registration){
    if(![...$('body-variant').options].some(o=>o.value===registration))throw Error('联合候选的修正来源未通过核验');
    $('body-variant').value=registration;
  }
  await $('load-body-candidate').onclick({restoreTask:false});
  const report=await get(`/api/motions/${id}/view/joint-animation.json`);
  if(!await joint.restoreResult(saved,report))throw Error('联合候选未恢复，请查看联合动画状态。');
  $('body-candidate-status').textContent='已恢复此联合候选的精确来源和参数；修改后构建独立新候选。';
}).catch(error=>{$('body-candidate-status').textContent=error.message;});
