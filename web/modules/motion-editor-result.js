import {createEditorRenderer} from './motion-editor-renderer.js';
import {validateYawTrack} from './motion-yaw-track.js';
import {normalizeLayerEdits} from './motion-layer-transform.js';

export function resultTrack(job,link){
  if(job.kind!=='adapt'||job.status!=='succeeded'||link.target_job_id!==job.job_id||link.artifact_sha256!==job.result?.artifact_sha256)
    throw Error('构建结果身份不一致');
  if(link.clip!==null)throw Error('此结果使用裁剪片段，请在独立验收窗口查看');
  const p=job.result.projection;
  const keys=p?.profile==='continuous-yaw-source-camera-v1'?p.keys:
    p?.profile==='constant-yaw-source-motion-v1'?[{time:0,yaw:p.yaw_degrees}]:null;
  if(!keys)throw Error('此候选没有编辑页支持的角度轨道');
  // Source metadata uses rational frame duration; editor keys use MotionIR microseconds.
  return validateYawTrack(keys,Math.round(link.duration*1e6)/1e6);
}
export function resultMatch(job,link,source,identity,keys,track){
  if(identity.project_id!==job.project_id||identity.character_job_id!==job.character_job_id||identity.source_id!==link.source_job_id
    ||source?.source_sha256!==link.source_sha256||source?.motion_identity?.clip_sha256!==link.motion_identity?.clip_sha256
    ||source?.motion_identity?.bundle_sha256!==link.motion_identity?.bundle_sha256)return 'different_source';
  const editsMatch=JSON.stringify(normalizeLayerEdits(identity.layer_edits))===JSON.stringify(normalizeLayerEdits(job.result.layer_edits));
  return editsMatch&&JSON.stringify(keys)===JSON.stringify(track)&&(identity.sampling_profile??null)===(job.result.projection.sampling_profile??null)?'matching':'draft_changed';
}
export function createEditorResult({canvas,status,restore,selection,viewport=()=>{}}){
  let renderer=null,job=null,link=null,track=null,version=0,time=0;
  function clear(){version++;renderer?.dispose();renderer=null;job=null;link=null;track=null;viewport(null);window.motionEditorResultState=null;document.getElementById('restore-result').disabled=true;}
  function seek(value){
    time=value;if(!renderer)return;
    const s=selection(),match=resultMatch(job,link,s.source,s.identity,s.keys,track);
    if(match==='different_source'){
      viewport(null);
      renderer.clear();status.textContent='已载入结果，但当前角色版本或源动作不同。点击“载入构建时的编辑草稿”后可同帧对照。';
      window.motionEditorResultState={status:match,job_id:job.job_id};return;
    }
    try {
      viewport(renderer.bounds);
      if(time<0||time>link.duration+0.00001)throw Error('时间超出此结果范围');
      const bones=renderer.draw(time);
      window.motionEditorResultState={status:match,job_id:job.job_id,artifact:renderer.artifact,time,bones};
      status.textContent=`实际导出姿态 · ${time.toFixed(3)} 秒 · ${match==='draft_changed'?'草稿角度或图层已变化，此处仍为旧构建结果':'与当前角度和图层校正对应'}。修形与遮挡处理以此结果为准；技术异常保留。`;
    }catch(e){renderer.clear();window.motionEditorResultState={status:'unavailable',reason:e.message};status.textContent=e.message;}
  }
  document.getElementById('restore-result').onclick=async()=>{
    if(!job||!link)return;const token=version;
    document.getElementById('restore-result').disabled=true;
    try{await restore(job,link,structuredClone(track),()=>token===version);if(token===version)seek(0);}
    catch(e){if(token===version)status.textContent=e.message;}
    finally{if(token===version)document.getElementById('restore-result').disabled=false;}
  };
  document.getElementById('close-result').onclick=()=>{clear();document.getElementById('result-viewport').hidden=true;};
  return {seek,clear,async load(value){
    clear();const token=version;status.textContent='正在读取实际构建结果…';
    document.getElementById('restore-result').disabled=true;
    try{
      const response=await fetch(`/api/motions/${value.job_id}/view/source-link.json`,{cache:'no-store'});
      if(!response.ok)throw Error('无法核验结果来源');const bound=await response.json(),keys=resultTrack(value,bound);
      const next=await createEditorRenderer(canvas,`/api/motions/${value.job_id}/view/player-assets/`,()=>token===version);
      if(!next)return;if(token!==version){next.dispose();return;}
      renderer=next;
      if(next.artifact!==value.result.artifact_sha256)throw Error('结果资源版本不一致');
      const animation=next.document.animations?.['external-motion'];if(!animation)throw Error('结果缺少导出动作');
      renderer.animation(animation);job=value;link=bound;track=keys;
      document.getElementById('restore-result').disabled=false;seek(time);
    }catch(e){if(token===version){clear();status.textContent=e.message;}}
  }};
}
