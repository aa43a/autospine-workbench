import {partitionEditor} from './motion-partition-editor.js';
const labels = {local_repair:'局部变形修正', partition:'重新划分区域', pose_attachment:'补充姿态附件', withdraw:'撤销此处处理草稿'};
const node = (tag, text) => {const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};

export function appendRepairDraft(parent, job, row, getDetail) {
  const panel=node('fieldset'), legend=node('legend','当前异常的处理草稿');
  const load=node('button','加载处理草稿'), save=node('button','保存处理草稿');
  const action=node('select');action.setAttribute('aria-label','异常处理路线');
  for(const [value,label] of Object.entries(labels)) {
    const option=node('option',label);option.value=value;action.append(option);
  }
  const notes=node('textarea');notes.maxLength=4000;notes.setAttribute('aria-label','异常处理说明');
  const material=node('a','下载姿态素材任务包');material.hidden=true;material.style.display='none';
  const execute=node('button','构建局部修正候选');execute.hidden=true;
  const status=node('p','先加载当前记录，再选择处理路线。');status.setAttribute('role','status');
  panel.append(legend,load,action,notes,save,status,material,execute,node('p','保存不执行修复。构建会重算此附件整段动作的局部变形，保留骨骼、其他附件及原候选；需要重新验证，不自动采用。'));
  parent.append(panel);let state=null, generation=0;save.disabled=true;
  const region=partitionEditor(panel,job,row);region.show(false);
  action.onchange=()=>region.show(action.value==='partition');
  const matches = r => r.slot===row.slot && r.animation===row.animation &&
    r.event.triangle===getDetail().triangle && r.event.time===getDetail().time;
  const render = () => {
    const records=state.history.filter(matches), latest=records.at(-1);
    const applies=latest && latest.artifact_sha256===state.artifact_sha256 && latest.evidence_sha256===state.evidence_sha256;
    action.value=applies?latest.action:'local_repair';notes.value=applies?latest.notes:'';
    region.restore(applies?latest.partition:null);region.show(action.value==='partition');
    material.hidden=!(applies&&latest.action==='pose_attachment');
    material.style.display=material.hidden?'none':'';
    execute.hidden=!(applies&&latest.action==='local_repair');
    execute.onclick=async()=>{
      panel.disabled=true;status.textContent='正在提交独立修正任务…';
      try {
        const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/repair-execute`,{
          method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},
          body:JSON.stringify({revision:latest.revision,draft_sha256:state.draft_sha256s[latest.revision-1]})});
        const result=await response.json();if(!response.ok)throw Error(result.reason_code||'构建失败');
        const link=node('a','查看修正任务进度与结果');link.href='/motions.html#'+encodeURIComponent(result.job_id);
        status.replaceChildren(node('span','已创建独立候选任务。'),link);
      }catch(error){status.textContent=error.message;}
      finally{panel.disabled=false;}
    };
    if(!material.hidden)material.href=`/api/motions/${encodeURIComponent(job.job_id)}/repair-material/${latest.revision}`;
    status.textContent=latest ? `${applies?'当前':'已过期'}：${labels[latest.action]}；此处 ${records.length} 条历史记录。` : '此处尚无处理草稿。';
    save.disabled=false;
  };
  const request = async body => {
    const response=await fetch(`/api/motions/${encodeURIComponent(job.job_id)}/repair-draft`,{
      cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Autospine-Intent':'pipeline-preview'},body:JSON.stringify(body)}:{})});
    const result=await response.json();if(!response.ok)throw Error(result.reason_code||'处理草稿请求失败');
    if(result.artifact_sha256!==job.result.artifact_sha256)throw Error('候选已变化，请刷新任务');
    return result;
  };
  const run = async body => {
    const ticket=++generation;panel.disabled=true;material.hidden=true;execute.hidden=true;status.textContent=body?'正在保存…':'正在加载…';
    material.style.display='none';
    try {const result=await request(body);if(ticket!==generation)return;state=result;render();}
    catch(error){if(ticket===generation){state=null;save.disabled=true;status.textContent=error.message+'；请重新加载。';}}
    finally {if(ticket===generation)panel.disabled=false;}
  };
  load.onclick=()=>run();
  save.onclick=()=>{
    if(!state)return;
    const detail=getDetail();
    let partition;
    try{if(action.value==='partition')partition=region.value();}
    catch(error){status.textContent=error.message;return;}
    run({artifact_sha256:state.artifact_sha256,evidence_sha256:state.evidence_sha256,
      expected_revision:state.revision,slot:row.slot,animation:row.animation,
      triangle:detail.triangle,time:detail.time,action:action.value,notes:notes.value,...(partition?{partition}:{})});
  };
  return () => {
    generation++;panel.disabled=false;material.hidden=true;execute.hidden=true;
    material.style.display='none';
    if(state)render();else {save.disabled=true;status.textContent='先加载当前记录，再选择处理路线。';}
  };
}
