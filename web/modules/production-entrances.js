const $=id=>document.getElementById(id);
const states={pending:'等待处理',running:'等待来源完成',linked:'已衔接制作',blocked:'需要干预',canceled:'已取消衔接'};
const sourceStates={pending:'等待',running:'处理中',succeeded:'已完成',failed:'失败',canceled:'已取消'};
function el(tag,text){const e=document.createElement(tag);e.textContent=text;return e;}
export function createProductionEntrances({api,settings,openRun}){
  let busy=false;const names=new Map();
  async function choices(){
    const value=await api('/api/production-entrances/options');
    const old=$('entrance-character').value,motion=$('entrance-motion').value;
    $('entrance-character').replaceChildren(new Option('使用下方选择的已有角色','selected'));
    for(const job of value.imports){names.set(job.job_id,job.name);$('entrance-character').add(new Option(`${job.name} · ${sourceStates[job.status]||job.status}`,job.job_id));}
    if([...$('entrance-character').options].some(o=>o.value===old))$('entrance-character').value=old;
    $('entrance-motion').replaceChildren(new Option('选择已上传或正在生成的动作',''));
    for(const job of value.motions){names.set(job.job_id,job.name);$('entrance-motion').add(new Option(`${job.name} · ${sourceStates[job.status]||job.status}`,job.job_id));}
    $('entrance-motion').value=motion;
  }
  async function refresh(){
    const {entrances}=await api('/api/production-entrances');const panel=$('entrance-list');panel.replaceChildren();
    for(const item of entrances){const row=el('article','');row.append(el('strong',states[item.status]||item.status),el('p',`创建于 ${new Date(item.created_at).toLocaleString()}${item.reason_code?' · '+item.reason_code:''}`));
      const character=item.request.character,project=[...$('project').options].find(o=>o.value===character.project_id)?.textContent;
      row.append(el('p',`${project||names.get(character.import_job_id)||character.project_id||character.import_job_id} · ${names.get(item.request.source_job_id)||item.request.source_job_id}`));
      if(item.status==='linked'){const open=el('button','在本页查看制作进度');open.onclick=()=>openRun(item.run_id).catch(fail);row.append(open);}
      else if(item.status!=='canceled'){for(const [action,text] of [['resume','继续衔接'],['cancel','取消衔接']]){const button=el('button',text);button.onclick=async()=>{try{await api(`/api/production-entrances/${item.job_id}/${action}`,{expected_revision:item.revision});await refresh();}catch(e){fail(e);}};row.append(button);}}
      panel.append(row);
    }
  }
  function fail(e){$('entrance-status').textContent=`未完成：${e.message}。已保存的来源与任务保留。`;}
  $('entrance-refresh').onclick=()=>Promise.all([choices(),refresh()]).catch(fail);
  $('entrance-start').onclick=async()=>{if(busy)return;busy=true;try{
    const selection=$('entrance-character').value,source_job_id=$('entrance-motion').value;
    const character=selection==='selected'?{project_id:$('project').value}:{import_job_id:selection};
    if(!source_job_id||character.project_id==='')throw Error('请选择角色来源和动作');
    await api('/api/production-entrances',{character,source_job_id,...settings()});
    $('entrance-status').textContent='来源到交付的衔接任务已保存。来源完成后会自动开始制作；服务重启后可继续衔接。';await refresh();
  }catch(e){fail(e);}finally{busy=false;}};
  Promise.all([choices(),refresh()]).catch(fail);
  setInterval(()=>{if(!busy&&!document.hidden)refresh().catch(fail);},5000);
}
