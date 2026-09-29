import {normalizeLayerEdits} from './motion-layer-transform.js';
export function editCheckSignature(draft){const {time,...identity}=draft;return JSON.stringify(identity);}
export async function checkLayerDraft(draft,request){
  const value=normalizeLayerEdits(draft.layer_edits);
  const result=await request(`/api/motions/${encodeURIComponent(draft.source_id)}/layer-edit-check`,{
    project_id:draft.project_id,character_job_id:draft.character_job_id,
    baseline:null,operations:[{op:'replace',value}],
  });
  if(!result.ok){const row=result.diagnostics?.[0];throw Error(row?`${row.slot||''} ${row.path} · ${row.code} · ${row.hint}`:'图层预检查失败');}
  if(!/^[a-f0-9]{64}$/.test(result.receipt_sha256)||JSON.stringify(normalizeLayerEdits(result.value))!==JSON.stringify(value))
    throw Error('预检查结果与当前修改不一致，未提交构建');
  return result;
}
