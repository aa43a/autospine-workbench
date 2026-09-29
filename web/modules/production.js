import {projectOptionLabel} from './project-option-label.js';
import {createProductionIntake} from './production-intake.js';
import {createProductionEntrances} from './production-entrances.js';
import {createProductionMeasurements} from './production-measurements.js';
import {createProductionRevision} from './production-revision.js';
import {inspectionControls} from './production-inspection.js';
import {existingBody} from './production-existing-body.js';
import {createProductionBatches} from './production-batches.js';
import {createProductionCoverage} from './production-coverage.js';
import {appendStageReview} from './motion-stage-review.js';
import {appendReadiness} from './motion-readiness.js';
const $=id=>document.getElementById(id);
const labels={source:'来源准备',bindings:'默认绑定',character:'整角色来源',body:'身体动作与 Runtime',joint:'表情、发束、裙袖与 Runtime',review:'阶段验收',delivery:'Spine 候选'};
const states={pending:'准备中',running:'处理中',reused:'沿用已有结果',succeeded:'已完成',needs_review:'待阶段验收',stage_accepted:'阶段已接受',candidate_available:'可下载候选',blocked:'需要干预',failed:'未完成',canceled:'已取消'};
const reasons={joint_review_required:'请检查并保存关节点，然后点击“继续”。已完成步骤会保留。',character_route_confirmation_required:'请在角色编辑中选择普通肢体或袖装处理路线，然后继续。',character_sleeve_resolution_required:'已有袖装修复记录需要处理，请先检查该角色的袖装结果。',production_source_changed:'角色或动作来源已变化，请使用“按当前角色修正重建”建立关联的新版本。',animated_source_stale:'动画来源需要同步已保存的修改，请在角色编辑中更新来源后重建。'};
let selected=new URL(location.href).searchParams.get('run'),runs=[],options=null,busy=false;
let evidenceJob=null;
const coverage=createProductionCoverage(api);
const measurements=createProductionMeasurements(api);
async function openRun(id){selected=id;history.replaceState(null,'',`?run=${id}`);await refreshRuns();$('summary').scrollIntoView({behavior:'smooth'});}
const revision=createProductionRevision({api,openRun});
function projectName(run){return Array.from($('project').options).find(p=>p.value===run.request.project_id)?.textContent||run.request.project_id;}
async function evidence(run){
  const key=run?`${run.stages.body.job_id}:${run.stages.joint.job_id}`:null;
  if(evidenceJob===key)return;evidenceJob=key;
  const panel=$('evidence');panel.replaceChildren();panel.hidden=!run;if(!run)return;
  panel.textContent='正在读取候选检查与验收…';
  try{const value=await api(`/api/motions/${run.stages.joint.job_id}`);if(evidenceJob!==key)return;
    if(value.status!=='succeeded'||value.result?.artifact_sha256!==run.stages.joint.artifact_sha256)throw Error('联合候选版本已变化，请刷新来源');
    panel.replaceChildren(node('h2','检查异常与记录阶段验收'));
    appendStageReview(panel,value);const joint=node('section','');panel.append(joint);appendReadiness(joint,value,null,{...inspectionControls(joint,value),onJointEdit:()=>$('revision-panel').scrollIntoView({behavior:'smooth',block:'start'})});
    const selection=run.request.body_selection;
    if(selection){const selected=node('section','');selected.append(node('h3','本次联合动画使用的身体修复版本'),node('p',`版本 ${selection.artifact_sha256.slice(0,12)}。下方原身体诊断用于追溯，不代表修复版本的检查结论。`));
      const show=node('button','在本页播放修复身体'),frame=document.createElement('iframe');frame.title='所选身体修复版本';frame.hidden=true;
      show.onclick=()=>{frame.src=`/api/motions/${selection.parent_job_id}/view/`+(selection.registration_sha256?`related-candidates/${selection.registration_sha256}/`:'')+'player.html';frame.hidden=false;};
      selected.append(show,frame);panel.append(selected);}
    const body=node('details','');body.append(node('summary','追溯身体动作原候选的异常'));panel.append(body);
    const original=await api(`/api/motions/${run.stages.body.job_id}`);if(evidenceJob!==key)return;
    if(original.status!=='succeeded'||original.result?.artifact_sha256!==run.stages.body.artifact_sha256)throw Error('身体候选版本已变化，请刷新来源');
    appendReadiness(body,original,null,inspectionControls(body,original));
  }catch(e){if(evidenceJob===key){panel.append(node('p',e.message));evidenceJob=null;}}
}
async function api(url,body){const r=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)});const value=await r.json();if(!r.ok)throw Error(value.reason_code||value.error||`请求失败 ${r.status}`);return value;}
function node(tag,text){const e=document.createElement(tag);e.textContent=text;return e;}
function link(label,url){const a=node('a',label);a.href=url;return a;}
async function action(name){if(busy)return;const run=runs.find(r=>r.run_id===selected);if(!run)return;busy=true;try{const value=await api(`/api/production/${selected}/${name}`,{expected_revision:run.revision});selected=value.run_id;history.replaceState(null,'',`?run=${selected}`);await refreshRuns();}catch(e){$('detail').textContent=e.message;}finally{busy=false;}}
function render(){
  $('runs').replaceChildren();
  for(const run of runs){const b=node('button',`${projectName(run)} · ${states[run.status]||run.status}`);b.setAttribute('aria-current',String(run.run_id===selected));b.onclick=()=>{selected=run.run_id;history.replaceState(null,'',`?run=${selected}`);render();};$('runs').append(b);}
  const run=runs.find(r=>r.run_id===selected);if(!run)return;
  measurements(run);
  revision(run);
  void coverage(run);
  $('summary').replaceChildren(node('h2',`${projectName(run)} · ${states[run.status]||run.status}`),node('p',`创建于 ${new Date(run.created_at).toLocaleString()} · 更新于 ${new Date(run.updated_at).toLocaleTimeString()}`));
  $('stages').replaceChildren();for(const key of Object.keys(labels)){const row=run.stages[key];if(!row)continue;const li=node('li','');li.dataset.state=row.status;li.append(node('span',labels[key]||key),node('strong',states[row.status]||row.status));$('stages').append(li);}
  $('detail').textContent=run.status==='blocked'&&run.reason_code?`${reasons[run.reason_code]||'此步骤未完成，可查看角色来源与绑定，或重试失败步骤。'}\n诊断：${run.reason_code}`:'技术检查与人工验收分别记录；候选可下载不代表所有视觉问题都已解决。';
  $('actions').replaceChildren();
  for(const [name,label] of [['resume','继续 / 同步验收'],['retry','重试失败步骤'],['cancel','取消任务']]){if(name==='retry'&&run.status!=='blocked'||name==='cancel'&&!['pending','running'].includes(run.status)||name==='resume'&&run.status==='canceled')continue;const b=node('button',label);b.onclick=()=>action(name);$('actions').append(b);}
  $('actions').append(link('定位角色与绑定',`/?project=${encodeURIComponent(run.request.project_id)}`));
  if(run.stages.character.status==='succeeded'&&run.stages.character.job_id)$('actions').append(link('检查整角色覆盖与缺项',`/api/projects/${encodeURIComponent(run.request.project_id)}/automation/character/jobs/${run.stages.character.job_id}/view/index.html`));
  if(!['pending','running'].includes(run.status)){const revise=node('button','按当前角色修正重建');revise.onclick=()=>$('revision-panel').scrollIntoView({behavior:'smooth',block:'start'});$('actions').append(revise);}
  const delivery=run.stages.delivery;
  void evidence(delivery.player_url?run:null);
  if(delivery.player_url){$('actions').append(link('独立播放窗口',delivery.player_url),link('下载 Spine 候选',delivery.download_url),link('调整联合动画',`/motion-editor.html?joint=${run.stages.joint.job_id}`));if($('player').getAttribute('src')!==delivery.player_url)$('player').src=delivery.player_url;$('player').hidden=false;}
  else{$('player').hidden=true;$('player').removeAttribute('src');}
}
async function refreshRuns(){const value=await api('/api/production');runs=value.runs;selected??=runs[0]?.run_id;render();}
async function refresh(){try{const [projects,motions,config]=await Promise.all([api('/api/projects'),api('/api/motions'),api('/api/production/options')]);options=config;const previous=$('project').value,source=$('source').value;$('project').replaceChildren(new Option('选择已绑定角色',''));for(const p of projects.projects)$('project').add(new Option(projectOptionLabel(p,projects.projects),p.id));$('project').value=previous;$('source').replaceChildren(new Option('选择已解析动作',''));for(const j of motions.jobs)if(j.kind!=='adapt'&&j.status==='succeeded'&&j.result?.motion_status==='compiled')$('source').add(new Option(j.name,j.job_id));$('source').value=source;await refreshRuns();$('status').textContent='选择已绑定角色和源动作后开始制作。';}catch(e){$('status').textContent=e.message;}}
$('create').onsubmit=async event=>{
  event.preventDefault();if(busy||!options)return;busy=true;$('start').disabled=true;
  try{
    const project=$('project').value;
    const target=await api(`/api/projects/${encodeURIComponent(project)}/automation/character/motion-target`);
    const body=structuredClone(options.body_options),config=structuredClone(options.joint_config);
    body.projection.keys[0].yaw=Number($('yaw').value);
    for(const group of ['face','hair','cloth'])config[group].enabled=$(group).checked;
    const run=await api('/api/production',{project_id:project,character_job_id:target.job?.status==='needs_review'?target.job.job_id:null,
      source_job_id:$('source').value,body_options:body,joint_config:config});
    selected=run.run_id;history.replaceState(null,'',`?run=${selected}`);await refreshRuns();
    $('status').textContent='制作任务已保存，将自动衔接后续步骤。';
  }catch(e){$('status').textContent=e.message;}finally{busy=false;$('start').disabled=false;}
};
$('refresh').onclick=refresh;
await refresh();
const productionControls={api,settings:()=>{
  if(!options)throw Error('请先刷新角色与动作列表');
  const body_options=structuredClone(options.body_options),joint_config=structuredClone(options.joint_config);
  body_options.projection.keys[0].yaw=Number($('yaw').value);
  for(const group of ['face','hair','cloth'])joint_config[group].enabled=$(group).checked;
  return {body_options,joint_config};
},openRun};
createProductionBatches(productionControls);
createProductionEntrances(productionControls);
existingBody(productionControls);
createProductionIntake({refresh,selectProject:id=>{$('project').value=id;},selectSource:id=>{$('source').value=id;}});
setInterval(()=>{if(!busy&&!document.hidden)refreshRuns().catch(e=>{$('status').textContent=`读取进度失败：${e.message}。任务记录保留，可刷新重试。`;});},4000);
