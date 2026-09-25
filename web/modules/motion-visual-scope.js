import {appendRepairDraft} from './motion-repair-draft.js';
const node=(tag,text)=>{const value=document.createElement(tag);if(text)value.textContent=text;return value;};

export function appendVisualScope(parent,job,onSeek){
  const button=node('button','编辑衣料覆盖与前后关系'),panel=node('section');panel.hidden=true;
  parent.append(button,panel);let generation=0;
  button.onclick=async()=>{
    const ticket=++generation;button.disabled=true;panel.hidden=false;panel.textContent='正在读取当前候选附件…';
    try{
      const base=`/api/motions/${encodeURIComponent(job.job_id)}/view/`;
      const response=await fetch(base+'partition-mesh.json',{cache:'no-store'}),report=await response.json();
      if(!response.ok)throw Error(report.reason_code||'无法读取附件');
      if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选已变化，请刷新任务');
      if(!report.animations?.length)throw Error('服务尚未提供视觉编辑入口所需的动画信息，请更新服务后重试');
      if(ticket!==generation)return;
      panel.replaceChildren(node('p','无须先有几何失败。选择附件和检查时间，再在原纹理上标注覆盖区或提出前后顺序方案。这里记录人工检查意图，不自动判定遮挡错误。'));
      const slot=node('select'),animation=node('select'),time=node('input'),open=node('button','打开所选附件的处理画布'),editor=node('div');
      slot.setAttribute('aria-label','视觉检查附件');animation.setAttribute('aria-label','视觉检查动作');
      time.type='number';time.min=0;time.step='any';time.value=0;time.setAttribute('aria-label','视觉检查时间（秒）');
      for(const row of report.rows){const option=node('option',row.slot);option.value=row.slot;slot.append(option);}
      for(const row of report.animations){const option=node('option',row.name);option.value=row.name;animation.append(option);}
      const reset=()=>{editor.replaceChildren();time.max=report.animations.find(r=>r.name===animation.value).duration;};
      slot.onchange=reset;animation.onchange=()=>{time.value=0;reset();};time.oninput=()=>editor.replaceChildren();
      const status=node('p');status.setAttribute('role','status');
      open.onclick=()=>{
        const t=Number(time.value),max=Number(time.max),selected=report.rows.find(r=>r.slot===slot.value);
        if(!selected||time.value.trim()===''||!Number.isFinite(t)||t<0||t>max){status.textContent='请选择有效附件和动作范围内的时间。';return;}
        editor.replaceChildren();status.textContent='当前选择已固定；更换附件或时间后请重新载入，未保存笔刷会清除。';
        appendRepairDraft(editor,job,{slot:selected.slot,animation:animation.value,
          texture:base+selected.texture_path.split('/').map(encodeURIComponent).join('/')},
          ()=>({triangle:-1,time:t}),{visualInspection:true});
        if(onSeek)onSeek(t);
      };
      panel.append(slot,animation,time,open,status,editor);reset();
    }catch(error){if(ticket===generation)panel.textContent='无法打开：'+error.message;}
    finally{if(ticket===generation)button.disabled=false;}
  };
}
