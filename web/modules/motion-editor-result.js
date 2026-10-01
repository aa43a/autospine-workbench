import {createEditorRenderer} from './motion-editor-renderer.js';
import {validateYawTrack} from './motion-yaw-track.js';
import {normalizeLayerEdits} from './motion-layer-transform.js';
import {jointAmplitudePreview,jointPreviewText} from './motion-joint-preview.js';
import {validateWindTemplate,jointWindPreview,windOffsets} from './motion-wind-preview.js';

export async function readWindTemplate(jobId,report,document,read=fetch){
  const proof=report.secondary?.wind_preview;
  if(proof?.file!=='wind-preview.json')return null;
  const response=await read(`/api/motions/${jobId}/view/wind-preview.json`,{cache:'no-store'});
  if(!response.ok)throw Error(`受风预览资源读取失败（${response.status}），请刷新结果或重试。`);
  const raw=await response.arrayBuffer();
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(v=>v.toString(16).padStart(2,'0')).join('');
  if(hash!==proof.sha256)throw Error('受风预览版本不一致');
  return validateWindTemplate(JSON.parse(new TextDecoder().decode(raw)),report,document);
}

function windThumbnail(source,time,preview){
  const canvas=document.querySelector('[data-wind-preview-canvas]'),status=document.querySelector('[data-wind-preview-status]');
  if(!canvas)return;
  const context=canvas.getContext('2d');context?.clearRect(0,0,canvas.width,canvas.height);
  canvas.hidden=!source;
  if(!source){if(status)status.textContent='先构建或载入联合候选，即可同帧观察风场效果。';return;}
  const scale=Math.min(canvas.width/source.width,canvas.height/source.height);
  context?.drawImage(source,(canvas.width-source.width*scale)/2,(canvas.height-source.height*scale)/2,source.width*scale,source.height*scale);
  if(status)status.textContent=`${time.toFixed(3)} 秒 · ${preview?.noWind?'无风对照':preview?.changed?'即时草稿，需构建验证':'已构建结果'}`;
}

export function resultTrack(job,link){
  if(job.kind!=='adapt'||job.status!=='succeeded'||link.target_job_id!==job.job_id||link.artifact_sha256!==job.result?.artifact_sha256)
    throw Error('构建结果身份不一致');
  if(link.clip!==null)throw Error('此结果使用裁剪片段，请在独立验收窗口查看');
  const p=job.result.projection;
  const keys=p?.profile==='continuous-yaw-source-camera-v1'?p.keys:
    p?.profile==='constant-yaw-source-motion-v1'?[{time:0,yaw:p.yaw_degrees}]:
    p==null&&['front','side'].includes(link.source_view)?[{time:0,yaw:link.source_view==='front'?0:90}]:null;
  if(!keys)throw Error('此候选没有编辑页支持的角度轨道');
  // Source metadata uses rational frame duration; editor keys use MotionIR microseconds.
  return validateYawTrack(keys,Math.round(link.duration*1e6)/1e6);
}
export function resultMatch(job,link,source,identity,keys,track){
  if(identity.project_id!==job.project_id||identity.character_job_id!==job.character_job_id||identity.source_id!==link.source_job_id
    ||source?.source_sha256!==link.source_sha256||source?.motion_identity?.clip_sha256!==link.motion_identity?.clip_sha256
    ||source?.motion_identity?.bundle_sha256!==link.motion_identity?.bundle_sha256)return 'different_source';
  const editsMatch=JSON.stringify(normalizeLayerEdits(identity.layer_edits))===JSON.stringify(normalizeLayerEdits(job.result.layer_edits));
  return editsMatch&&JSON.stringify(keys)===JSON.stringify(track)&&(identity.sampling_profile??null)===(job.result.projection?.sampling_profile??null)?'matching':'draft_changed';
}
export function createEditorResult({canvas,status,restore,selection,viewport=()=>{}}){
  let renderer=null,job=null,link=null,track=null,version=0,time=0,jointReport=null,previewDraft=null,preview=null,previewSignature=null,windTemplate=null,jointResourceError=null;
  function refreshPreview(){
    preview=null;
    if(!renderer||!previewDraft?.enabled)return;
    if(jointResourceError){preview={available:false,changed:false,pending:[jointResourceError],gains:new Map(),reason:'受风预览未应用，画布保留已构建结果。'};return;}
    if(!jointReport)return;
    const provenance=job?.result?.joint_source_provenance;
    if(previewDraft.parent_job_id!==job?.result?.joint_parent_job_id||previewDraft.artifact_sha256!==provenance?.artifact_sha256)return;
    try{
      preview=windTemplate&&previewDraft.config.wind?
        jointWindPreview(windTemplate,jointReport,previewDraft.config,{noWind:previewDraft.noWind}):
        jointAmplitudePreview(renderer.document,jointReport,previewDraft.config);
      if(previewDraft.noWind&&!windTemplate)preview.pending.push('无风对照需先构建受风区域');
    }catch(e){preview={available:false,changed:false,pending:[e.message],gains:new Map(),reason:'受风预览未应用，画布保留已构建结果。'};}
  }
  function clear(){version++;renderer?.dispose();renderer=null;job=null;link=null;track=null;jointReport=null;preview=null;windTemplate=null;jointResourceError=null;windThumbnail(null);viewport(null);window.motionEditorResultState=null;document.getElementById('restore-result').disabled=true;}
  function seek(value){
    time=value;if(!renderer)return;
    const s=selection(),match=resultMatch(job,link,s.source,s.identity,s.keys,track);
    if(match==='different_source'){
      viewport(null);
      windThumbnail(null);
      renderer.clear();status.textContent='已载入结果，但当前角色版本或源动作不同。点击“载入构建时的编辑草稿”后可同帧对照。';
      window.motionEditorResultState={status:match,job_id:job.job_id};return;
    }
    try {
      viewport(renderer.bounds);
      if(time<0||time>link.duration+0.00001)throw Error('时间超出此结果范围');
      const bones=renderer.draw(time,{jointGains:preview?.gains,jointOffsets:windOffsets(preview,time)});
      windThumbnail(canvas,time,preview);
      canvas.setAttribute('aria-label',preview?.changed?'次级运动草稿预览，尚未验证':'实际导出姿态');
      const heading=document.querySelector('#result-viewport h2');
      if(heading)heading.textContent=preview?.changed?(preview.mode==='wind_solver'?'即时受风预览 · 尚未构建验证':'即时幅度预览 · 尚未构建验证'):'构建结果 · 共用动作时间轴';
      window.motionEditorResultState={status:preview?.changed?'joint_preview':match,job_id:job.job_id,artifact:renderer.artifact,time,bones,
        joint_preview:preview?{changed:preview.changed,pending:preview.pending,mode:preview.mode,no_wind:preview.noWind,gains:Object.fromEntries(preview.gains??[]),
          helpers:Object.fromEntries([...(preview.tracks??preview.gains??new Map()).keys()].map(name=>[name,renderer.boneMatrix(name)]))}:null};
      status.textContent=preview?.changed?`${time.toFixed(3)} 秒 · ${jointPreviewText(preview)} 保存与下载仍是原构建结果。${match==='draft_changed'?' 当前视角或图层草稿也尚未进入此结果。':''}`:
        `实际导出姿态 · ${time.toFixed(3)} 秒 · ${match==='draft_changed'?'草稿角度或图层已变化，此处仍为旧构建结果':'与当前角度和图层校正对应'}。修形与遮挡处理以此结果为准；技术异常保留。${preview?.pending?.length?' '+jointPreviewText(preview):''}`;
    }catch(e){renderer.clear();windThumbnail(null);window.motionEditorResultState={status:'unavailable',reason:e.message};status.textContent=e.message;}
  }
  document.getElementById('restore-result').onclick=async()=>{
    if(!job||!link)return;const token=version;
    document.getElementById('restore-result').disabled=true;
    try{await restore(job,link,structuredClone(track),()=>token===version);if(token===version)seek(0);}
    catch(e){if(token===version)status.textContent=e.message;}
    finally{if(token===version)document.getElementById('restore-result').disabled=false;}
  };
  document.getElementById('close-result').onclick=()=>{clear();document.getElementById('result-viewport').hidden=true;};
  return {seek,clear,jointPreview(value){
    const signature=JSON.stringify(value);if(signature===previewSignature)return preview;
    previewSignature=signature;previewDraft=value;refreshPreview();seek(time);return preview;
  },async load(value){
    clear();const token=version;status.textContent='正在读取实际构建结果…';
    document.getElementById('restore-result').disabled=true;
    try{
      const registration=value.joint_registration_sha256;
      const response=await fetch(registration?`/api/motions/${value.job_id}/related-candidates/${registration}/joint-animation`:
        `/api/motions/${value.job_id}/view/source-link.json`,{cache:'no-store'});
      if(!response.ok)throw Error('无法核验结果来源');const metadata=await response.json(),bound=registration?metadata.source_link:metadata,keys=resultTrack(value,bound);
      const next=await createEditorRenderer(canvas,registration?metadata.preview_base:`/api/motions/${value.job_id}/view/player-assets/`,()=>token===version);
      if(!next)return;if(token!==version){next.dispose();return;}
      renderer=next;
      if(next.artifact!==value.result.artifact_sha256)throw Error('结果资源版本不一致');
      const animation=next.document.animations?.['external-motion'];if(!animation)throw Error('结果缺少导出动作');
      renderer.animation(animation);job=value;link=bound;track=keys;
      if(value.result?.joint_animation_profile){
        try{
          const response=await fetch(`/api/motions/${value.job_id}/view/joint-animation.json`,{cache:'no-store'});
          if(token!==version)return;
          if(!response.ok)throw Error(`联合动画报告读取失败（${response.status}）。`);
          const report=await response.json();if(token!==version)return;jointReport=report;
          const template=await readWindTemplate(value.job_id,report,renderer.document);
          if(token!==version)return;windTemplate=template;refreshPreview();
        }catch(e){if(token!==version)return;jointResourceError=e.message;refreshPreview();}
      }
      document.getElementById('restore-result').disabled=false;seek(time);
    }catch(e){if(token===version){clear();status.textContent=e.message;}}
  }};
}
