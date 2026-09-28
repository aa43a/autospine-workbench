import {createSourcePlayer} from './motion-source-player.js';
import {sampleYaw,validateYawTrack,yawSurfaceWarning} from './motion-yaw-track.js';
import {DRAFT_SCHEMA,matchEditorDraft,createEditorDraftControls} from './motion-editor-draft.js';
import {createEditorBuild} from './motion-editor-build.js';
import {createLiveCharacter} from './motion-editor-live.js';
import {createEditorIntake} from './motion-editor-intake.js';
const $=id=>document.getElementById(id);
const get=async url=>{const r=await fetch(url);if(!r.ok)throw Error(`读取失败 (${r.status})`);return r.json();};
let keys=[{time:0,yaw:0}],fixed=0,sourceToken=0,projectToken=0,duration=0,lastYaw=null,lastTime=null,override=null;
let characterJob=null,loadedSource=null;
const live=createLiveCharacter($('character-canvas'),$('character-status'));
const currentKeys=()=>override!==null?[{time:0,yaw:override}]:keys.length>1?keys:[{time:0,yaw:fixed}];
const player=createSourcePlayer($('source-canvas'),$('time'),$('play'),$('clock'),time=>{
  if(time!==lastTime){override=null;lastTime=time;}
  const yaw=override??(keys.length>1?sampleYaw(keys,time):fixed);
  if(yaw!==lastYaw){lastYaw=yaw;player.setView(yaw);}
  $('surface').textContent=yawSurfaceWarning(yaw);
  if(keys.length>1){$('yaw-value').value=yaw.toFixed(2);$('yaw').value=((yaw%360)+360)%360;}
  live.seek(time,currentKeys());
},{maxYaw:3600,interpolateFrames:true});
function keySummary(){ $('keys').textContent=keys.length>1?keys.map(k=>`${k.time.toFixed(3)} 秒：${k.yaw}°`).join(' → '):`固定角度 ${fixed}°`; }
function changeAngle(value){
  if(!Number.isFinite(value)||Math.abs(value)>3600)return;
  player.seek(Number($('time').value));override=value;fixed=value;lastYaw=value;player.setView(value);
  $('yaw-value').value=value;$('yaw').value=((value%360)+360)%360;
  $('surface').textContent=yawSurfaceWarning(value);
  keySummary();
}
$('yaw').oninput=()=>changeAngle(Number($('yaw').value));
$('yaw-value').onchange=()=>changeAngle(Number($('yaw-value').value));
$('key').onclick=()=>{
  const time=Number($('time').value),yaw=Number($('yaw-value').value);
  try{
    const next=keys.filter(k=>k.time!==time).concat({time,yaw}).sort((a,b)=>a.time-b.time);
    keys=validateYawTrack(next,duration);override=null;keySummary();live.seek(time,currentKeys());
  }catch(e){$('status').textContent=e.message;}
};
$('clear-keys').onclick=()=>{const value=Number($('yaw-value').value);if(!Number.isFinite(value)||Math.abs(value)>3600)return;
  fixed=value;keys=[{time:0,yaw:fixed}];override=null;keySummary();live.seek(Number($('time').value),currentKeys());};
$('source').onchange=async()=>{
  const token=++sourceToken,id=$('source').value;player.clear();duration=0;
  loadedSource=null;
  live.source(null);
  $('key').disabled=$('clear-keys').disabled=true;keys=[{time:0,yaw:0}];fixed=0;lastYaw=null;override=null;lastTime=null;
  $('yaw-value').value=$('yaw').value=0;keySummary();
  if(!id)return;
  $('status').textContent='正在加载源动作…';
  try{const value=await get(`/api/motions/${encodeURIComponent(id)}/editor-source`);if(token!==sourceToken)return;
    duration=value.duration;loadedSource=id;live.source(value);player.load(value.preview);$('key').disabled=$('clear-keys').disabled=false;
    $('status').textContent='源动作已加载。旋转角度或拖动时间轴，右侧实时映射角色姿态。';
  }catch(e){if(token===sourceToken)$('status').textContent=e.message;}
};
$('project').onchange=async()=>{
  const token=++projectToken,id=$('project').value;live.clear();
  characterJob=null;
  if(!id){$('character-status').textContent='选择角色后加载已保存候选。';return;}$('character-status').textContent='正在核对角色绑定…';
  try{const value=await get(`/api/projects/${encodeURIComponent(id)}/automation/character/motion-target`);if(token!==projectToken)return;
    if(value.job?.status!=='needs_review')throw Error('请先在角色工作台构建整角色候选。');
    const artifact=await live.load(`/api/projects/${encodeURIComponent(id)}/automation/character/jobs/${encodeURIComponent(value.job.job_id)}/view/player-assets/`);
    if(token!==projectToken||!artifact)return;characterJob=value.job.job_id;live.seek(Number($('time').value),currentKeys());
  }catch(e){if(token===projectToken)$('character-status').textContent=e.message;}
};
async function refresh(){
  $('refresh').disabled=true;
  try{const value=await get('/api/motions'),selected=$('source').value;
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
get('/api/projects').then(value=>{for(const p of value.projects)$('project').add(new Option(p.name,p.id));}).catch(e=>{$('status').textContent=e.message;});
void refresh();$('surface').textContent=yawSurfaceWarning(0);
function identity(){return {project_id:$('project').value,source_id:loadedSource,character_job_id:characterJob,duration};}
function snapshot(){if(!loadedSource||!characterJob)throw Error('请先完成角色和源动作加载');
  return {schema:DRAFT_SCHEMA,...identity(),time:Number($('time').value),keys:keys.length>1?keys:[{time:0,yaw:fixed}]};}
createEditorBuild({snapshot});
createEditorDraftControls({snapshot,
  async restore(draft){
    // Verify against currently loaded identities before replacing any edits.
    if(!loadedSource||!characterJob)throw Error(`请先选择草稿角色 ${draft.project_id} 和动作 ${draft.source_id}，再恢复草稿`);
    const current=identity(),tokens=[sourceToken,projectToken];
    const target=await get(`/api/projects/${encodeURIComponent(current.project_id)}/automation/character/motion-target`);
    if(tokens[0]!==sourceToken||tokens[1]!==projectToken)throw Error('选择已变化，请重试恢复草稿');
    const value=matchEditorDraft(draft,{...current,character_job_id:target.job?.job_id});
    keys=value.keys;fixed=keys[0].yaw;override=null;lastYaw=null;lastTime=null;player.seek(value.time);
    const yaw=sampleYaw(keys,value.time);$('yaw-value').value=yaw;$('yaw').value=((yaw%360)+360)%360;keySummary();
    $('status').textContent='草稿已恢复，角色版本和源动作一致。';
  },status:text=>{$('status').textContent=text;},
});
