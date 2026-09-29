const states={pending:'等待处理',running:'正在合包验证',blocked:'需要干预',needs_review:'待阶段验收',stage_accepted:'阶段已接受'};
const steps={queued:'已保存',merging:'合并动画',runtime_prepare:'准备 Runtime',runtime_geometry:'检查几何',runtime_reference:'生成采样参考',runtime:'官方 Runtime 播放',runtime_setup:'检查初始外观',review:'可播放并下载',blocked:'查看原因后重试'};
function el(tag,text){const e=document.createElement(tag);e.textContent=text;return e;}

export function deliveries({api}){
  const panel=document.getElementById('deliveries');let busy=false;
  async function refresh(){
    if(busy)return;busy=true;
    try{const {deliveries:items}=await api('/api/production-deliveries');panel.replaceChildren(el('h2','多动作交付包'));
      panel.append(el('p','在批次兼容性检查中创建合包。保留各动作原有异常，合包会重新运行验证；新包需要阶段验收。'));
      for(const item of items){
        const card=el('article','');card.append(el('h3',`${item.request.sources.length} 份动作 · ${states[item.status]||item.status}`),el('p',`${steps[item.step]||item.step}${item.reason_code?' · '+item.reason_code:''}`));
        if(item.runtime)card.append(el('p',`Runtime ${item.runtime.frames} 帧；几何${item.runtime.geometry_status==='passed'?'通过':'存在异常'}；${item.visual_status==='stage_accepted'?'已保存阶段接受':item.visual_status==='needs_changes'?'已记录需修改':'整包视觉尚未验收'}。原动作的接触、遮挡限制见包内来源记录。`));
        const base=`/api/production-deliveries/${item.job_id}`;
        if(['needs_review','stage_accepted'].includes(item.status)){
          const show=el('button','在本页播放多动作');show.onclick=()=>{const player=document.getElementById('delivery-player');player.hidden=false;player.src=base+'/view/player.html';player.scrollIntoView({block:'center'});};
          const link=el('a','下载 Spine 多动作候选');link.href=base+'/download';card.append(show,document.createTextNode(' '),link);
          const review=el('details',''),summary=el('summary','记录整包验收'),label=el('label','动作、时间与异常（可选）'),notes=el('textarea','');notes.value=item.review?.notes||'';notes.maxLength=4000;label.append(notes);review.append(summary,label);
          for(const [verdict,text] of [['stage_accepted','阶段可接受，保留限制'],['needs_changes','记录需要修改']]){const save=el('button',text);save.onclick=async()=>{save.disabled=true;try{await api(base+'/review',{expected_revision:item.revision,verdict,notes:notes.value});await refresh();}catch(e){review.append(el('p',e.message));}finally{save.disabled=false;}};review.append(save);}card.append(review);
        }else{const resume=el('button','继续 / 重试合包');resume.disabled=item.status==='running';resume.onclick=async()=>{try{await api(base+'/resume',{expected_revision:item.revision});await refresh();}catch(e){card.append(el('p',e.message));}};card.append(resume);}
        panel.append(card);
      }
    }catch(e){panel.append(el('p',`读取交付状态失败：${e.message}`));}finally{busy=false;}
  }
  refresh();setInterval(()=>{if(!document.hidden&&!panel.contains(document.activeElement)&&!panel.querySelector('details[open]'))refresh();},5000);
  return {async create(run_ids){await api('/api/production-deliveries',{run_ids});await refresh();panel.scrollIntoView({block:'start'});}};
}
