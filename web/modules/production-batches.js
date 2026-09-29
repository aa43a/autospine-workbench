const $=id=>document.getElementById(id);
const states={pending:'准备中',running:'处理中',needs_review:'待阶段验收',stage_accepted:'阶段已接受',needs_intervention:'部分需要干预',blocked:'需要干预',canceled:'已停止调度'};
const sectionNames={bones:'骨架姿态',slots:'部件顺序',skins:'网格、权重或 UV',skeleton:'骨架设置',constraints:'约束',texture_assets:'贴图资源'};
function element(tag,text){const e=document.createElement(tag);e.textContent=text;return e;}
function checked(id){return [...$(id).querySelectorAll('input:checked')].map(e=>e.value);}

export function createProductionBatches({api,settings,openRun}){
  let selected=new URL(location.href).searchParams.get('batch'),current=null,busy=false;
  const labels=new Map();
  function choices(){
    for(const [target,source] of [['batch-projects','project'],['batch-sources','source']]){
      const keep=new Set(checked(target));$(target).replaceChildren();
      for(const option of $(source).options){if(!option.value)continue;labels.set(option.value,option.textContent);
        const label=element('label',''),input=document.createElement('input');input.type='checkbox';input.value=option.value;input.checked=keep.has(option.value);input.onchange=count;
        label.append(input,document.createTextNode(option.textContent));$(target).append(label);
      }
    }count();
  }
  function count(){const n=checked('batch-projects').length*checked('batch-sources').length;$('batch-count').textContent=n?`${n} 个角色 × 动作组合（单批最多 32 个）`:'请勾选角色和动作';$('batch-create').disabled=busy||n<1||n>32;}
  async function refresh(){
    const result=await api('/api/production-batches');$('batch-list').replaceChildren();
    selected??=result.batches[0]?.batch_id;
    for(const b of result.batches){const button=element('button',`${new Date(b.created_at).toLocaleString()} · ${b.cells.length} 项 · ${states[b.status]||b.status}`);button.onclick=()=>{selected=b.batch_id;refresh().catch(fail);};$('batch-list').append(button);}
    current=result.batches.find(b=>b.batch_id===selected);render();
  }
  function fail(error){$('batch-message').textContent=`未完成：${error.message}。已保存的任务保留。`;}
  async function action(name){if(busy||!current)return;busy=true;count();try{await api(`/api/production-batches/${current.batch_id}/${name}`,{expected_revision:current.revision});await refresh();}catch(e){fail(e);}finally{busy=false;count();}}
  function render(){
    const panel=$('batch-detail');panel.replaceChildren();if(!current)return;
    const ready=current.cells.filter(c=>['needs_review','stage_accepted'].includes(c.status)).length;
    panel.append(element('h2',`批次进度 · ${ready} / ${current.cells.length} 已生成候选`));
    const actions=element('div','');
    for(const [key,label] of [['resume','同步 / 继续批次'],['cancel','停止后续调度']]){if(current.status==='canceled')continue;const b=element('button',label);b.onclick=()=>action(key);actions.append(b);}
    const compatibility=element('button','检查多动作包兼容性');compatibility.onclick=async()=>{
      compatibility.disabled=true;try{const value=await api(`/api/production-batches/${current.batch_id}/compatibility`);const output=element('div','');
        output.append(element('p','这里只检查骨架与贴图兼容性。合并后的 Runtime 和视觉验收仍需单独验证。'));
        for(const group of value.groups)output.append(element('p',`${labels.get(group.project_id)||group.project_id}：${group.run_ids.length} 份结构一致的候选${group.can_merge?'，可进入合包验证':'，暂时单独保留'}`));
        for(const cell of value.cells){if(cell.status!=='checked')output.append(element('p',`尚未检查：${labels.get(cell.project_id)||cell.project_id} · ${cell.reason_code}`));else if(cell.differences_from_first.length)output.append(element('p',`${labels.get(cell.project_id)||cell.project_id} 与首份差异：${cell.differences_from_first.map(k=>sectionNames[k]||k).join('、')}`));}
        panel.append(output);
      }catch(e){fail(e);}finally{compatibility.disabled=false;}
    };actions.append(compatibility);panel.append(actions,element('p','停止调度不会取消其他地方复用的任务；已提交任务可在下方单独取消。需要干预的组合可打开后处理和重试，再同步批次。'));
    const table=document.createElement('table');const head=element('tr','');for(const text of ['角色','动作','进度','操作'])head.append(element('th',text));table.append(head);
    for(const cell of current.cells){const row=element('tr','');row.append(element('td',labels.get(cell.request.project_id)||cell.request.project_id),element('td',labels.get(cell.request.source_job_id)||cell.request.source_job_id),element('td',`${states[cell.status]||cell.status}${cell.reason_code?' · '+cell.reason_code:''}`));const td=element('td',''),button=element('button','在本页查看');button.disabled=cell.status==='pending';button.onclick=()=>Promise.resolve(openRun(cell.run_id)).catch(fail);td.append(button);row.append(td);table.append(row);}panel.append(table);
  }
  $('batch-create').onclick=async()=>{
    if(busy)return;busy=true;count();try{
      const configuration=settings();const characters=[];
      for(const project_id of checked('batch-projects')){const target=await api(`/api/projects/${encodeURIComponent(project_id)}/automation/character/motion-target`);characters.push({project_id,character_job_id:target.job?.status==='needs_review'?target.job.job_id:null});}
      const value=await api('/api/production-batches',{characters,source_job_ids:checked('batch-sources'),...configuration});selected=value.batch_id;
      $('batch-message').textContent='批次已保存。关闭或刷新页面不会丢失任务；服务重启后可继续调度。';await refresh();
    }catch(e){fail(e);}finally{busy=false;count();}
  };
  $('batch-options-refresh').onclick=choices;choices();refresh().catch(fail);
  setInterval(()=>{if(!busy&&!document.hidden&&current&&['pending','running'].includes(current.status))refresh().catch(fail);},5000);
}
