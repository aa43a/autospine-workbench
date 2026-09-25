import {createSourcePlayer} from './motion-source-player.js';
import {appendStageReview} from './motion-stage-review.js';
import {appendRotationDetails} from './motion-rotation-details.js';
import {appendTargetComparison} from './motion-target-comparison.js';
import {createAlternativePanel} from './motion-cohort-alternative.js';
import {appendCandidateDownload} from './motion-candidate-download.js';
import {appendReadiness} from './motion-readiness.js';
import {createCohortSync} from './motion-cohort-sync.js';
import {createExperimentPanel} from './motion-experiments.js';
import {appendKneeDetails} from './motion-knee-details.js';
import {createCohortStatus} from './motion-cohort-status.js';
import {appendDepthSummary} from './motion-depth-summary.js';
import {navigationPack} from './motion-cohort-entry.js';
import {appendRelatedCandidates} from './motion-related-candidates.js';
const byId=id=>document.getElementById(id), motion=byId('motion'),character=byId('character');
const sync=createCohortSync(byId('sync-status'));
let related=null;
const player=createSourcePlayer(byId('source'),byId('time'),byId('play'),byId('time-label'),(time,end)=>{sync.seek(time,end);alternative.seek(time,end);experiments.seek(time,end);related?.seek(time,end);});
byId('source-view').onchange=()=>player.setView(byId('source-view').value||null);
const alternative=createAlternativePanel(byId('alternative'),get,{onSeek:time=>player.seek(time)});
const experiments=createExperimentPanel(byId('experiments'),get,time=>player.seek(time));
let pack,revision=0;
const id=/^motion-[a-f0-9]{32}$/,sha=/^[a-f0-9]{64}$/;
function validate(value){
  if(value.version!==1||!sha.test(value.plan_sha256)||!Array.isArray(value.groups)||!value.groups.length||value.groups.length>32)throw Error('复核清单无效');
  const jobs=new Set();let count=0;
  for(const g of value.groups){
    if(!id.test(g.job_id)||!sha.test(g.source_sha256)||typeof g.label!=='string'||g.label.length>100||!Array.isArray(g.targets)||!g.targets.length)throw Error('动作来源清单无效');
    for(const t of g.targets){
      if(!id.test(t.job_id)||!sha.test(t.artifact_sha256)||typeof t.label!=='string'||t.label.length>100||jobs.has(t.job_id))throw Error('角色候选清单无效');
      jobs.add(t.job_id);if(++count>96)throw Error('复核数量超过限制');
    }
  }
  if(value.coverage){const c=value.coverage;
    if(!Number.isInteger(c.expected)||c.expected<1||c.expected>96||c.available!==count||!Array.isArray(c.missing)||c.expected!==count+c.missing.length
      ||c.missing.some(r=>['motion','character','status'].some(k=>typeof r[k]!=='string'||r[k].length>100)))throw Error('固定集覆盖数量无效');
  }
  return value;
}
async function get(path){const r=await fetch(path,{cache:'no-store'});const v=await r.json();if(!r.ok)throw Error(v.reason_code||'读取失败');return v;}
function targets(){
  character.replaceChildren();pack.groups[Number(motion.value)].targets.forEach((t,i)=>character.add(new Option(t.label,String(i))));
}
async function show(){
  const version=++revision,g=pack.groups[Number(motion.value)],t=g.targets[Number(character.value)];
  related?.clear();related=null;
  alternative.clear();
  experiments.clear();
  sync.clear();
  player.clear();byId('target').replaceChildren();byId('review').replaceChildren();
  byId('status').textContent='正在核对当前动作与角色版本…';
  const flat=pack.groups.flatMap((g,mi)=>g.targets.map((t,ci)=>({mi,ci}))),index=flat.findIndex(v=>v.mi===Number(motion.value)&&v.ci===Number(character.value));
  byId('position').textContent=`${index+1} / ${flat.length}`;
  byId('previous').disabled=index===0;byId('next').disabled=index===flat.length-1;
  for(const [name,step] of [['previous',-1],['next',1]])byId(name).onclick=()=>{const n=flat[index+step];if(!n)return;motion.value=String(n.mi);targets();character.value=String(n.ci);show();};
  try{
    const [source,job]=await Promise.all([get(`/api/motions/${g.job_id}`),get(`/api/motions/${t.job_id}`)]);
    if(version!==revision)return;
    if(source.status!=='succeeded'||source.source_sha256!==g.source_sha256||job.status!=='succeeded'||job.kind!=='adapt'||job.result?.artifact_sha256!==t.artifact_sha256)throw Error('来源或候选身份已变化，请重新生成复核清单');
    const preview=await get(`/api/motions/${g.job_id}/preview`);if(version!==revision)return;
    player.load(preview);byId('target-title').textContent=`${g.label} · ${t.label}`;
    const frame=document.createElement('iframe');frame.title=`${t.label} 角色动作时间轴`;frame.src=`/api/motions/${t.job_id}/view/player.html`;byId('target').append(frame);
    sync.attach(frame,t.artifact_sha256);
    experiments.load(t.job_id);
    appendKneeDetails(byId('review'),`/api/motions/${t.job_id}/view/`,t.artifact_sha256,time=>{if(version===revision)player.seek(time);});
    appendStageReview(byId('review'),job);
    related=appendRelatedCandidates(byId('review'),job,{synchronize:true});
    related.seek(Number(byId('time').value),Number(byId('time').max));
    appendCandidateDownload(byId('review'),job);
    const inspection={onSeek:time=>{
      if(version!==revision)return;
      player.seek(time);
      frame.scrollIntoView({block:'nearest'});
    },onInspect:(slot,triangle,animation)=>{
      if(version===revision)sync.inspect(slot,triangle,animation);
    },onRegions:pair=>{if(version===revision)sync.regions(pair);}};
    const whole=document.createElement('button');whole.textContent='显示完整角色';
    whole.onclick=()=>{if(version===revision)sync.regions([],'full');};byId('review').append(whole);
    appendReadiness(byId('review'),job,null,inspection);
    appendDepthSummary(byId('review'),job,inspection);
    appendTargetComparison(byId('review'),job,get,{onOpen:row=>{
      if(version===revision)alternative.open(row,g.source_sha256);
    }});
    appendRotationDetails(byId('review'),job,{onSeek:time=>{
      if(version!==revision)return;
      player.seek(time);
      frame.scrollIntoView({block:'nearest'});
    }});
    byId('status').textContent='已核对版本。查看角色动作后，可直接在本页保存阶段结论；不会自动确认。';
  }catch(error){if(version===revision)byId('status').textContent='无法打开：'+error.message;}
}
try{
  pack=validate(await navigationPack(location.hash,location.search,get));
  pack.groups.forEach((g,i)=>motion.add(new Option(g.label,String(i))));targets();
  createCohortStatus(byId('cohort-status'),pack,(mi,ci)=>{motion.value=String(mi);targets();character.value=String(ci);show();byId('target-title').scrollIntoView({block:'start'});});
  motion.onchange=()=>{targets();show();};character.onchange=show;show();
}catch(error){byId('status').textContent=error.message+'。请从固定动作矩阵的“集中播放与验收”入口打开。';}
