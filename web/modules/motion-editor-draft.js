import {validateYawTrack} from './motion-yaw-track.js';
export const DRAFT_SCHEMA='autospine.motion-editor-draft/v1';
export const DRAFT_STORAGE='autospine.motion-editor.draft.v1';
export function validateEditorDraft(value){
  if(!value||value.schema!==DRAFT_SCHEMA)throw Error('不是受支持的动作编辑草稿');
  const fields=['character_job_id','duration','keys','project_id','schema','source_id','time'];
  if(Object.keys(value).sort().join(',')!==fields.sort().join(','))throw Error('草稿字段不完整或不受支持');
  for(const key of ['character_job_id','project_id','source_id'])
    if(typeof value[key]!=='string'||!value[key]||value[key].length>200||!/^[a-zA-Z0-9_-]+$/.test(value[key]))throw Error('草稿来源无效');
  validateYawTrack(value.keys,value.duration);
  if(!Number.isFinite(value.time)||value.time<0||value.time>value.duration)throw Error('草稿播放位置无效');
  return structuredClone(value);
}
export function matchEditorDraft(value,identity){
  const draft=validateEditorDraft(value);
  for(const field of ['project_id','source_id','character_job_id','duration'])
    if(draft[field]!==identity[field])throw Error('角色版本或源动作已变化，请重新选择；未覆盖当前编辑');
  return draft;
}
export function createEditorDraftControls({snapshot,restore,status}){
  const $=id=>document.getElementById(id);
  const report=action=>async()=>{try{await action();}catch(e){status(e.message);}};
  $('save-draft').onclick=report(()=>{
    const draft=validateEditorDraft(snapshot());
    localStorage.setItem(DRAFT_STORAGE,JSON.stringify(draft));status('编辑草稿已保存在当前浏览器；尚未生成角色动画。');
  });
  $('restore-draft').onclick=report(async()=>{
    const text=localStorage.getItem(DRAFT_STORAGE);if(!text)throw Error('当前浏览器没有已保存草稿');
    await restore(validateEditorDraft(JSON.parse(text)));
  });
  $('download-draft').onclick=report(()=>{
    const draft=validateEditorDraft(snapshot());
    const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='motion-editor-draft.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);status('草稿已下载，可在此页面导入继续编辑；这不是 Spine 动画包。');
  });
  $('import-draft').onchange=report(async()=>{
    const input=$('import-draft'),file=input.files[0];input.value='';if(!file)return;
    if(file.size>100000)throw Error('草稿文件过大');
    await restore(validateEditorDraft(JSON.parse(await file.text())));
  });
}
