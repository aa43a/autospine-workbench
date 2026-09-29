const names={source:'来源准备',bindings:'默认绑定',character:'整角色',body:'身体动作',joint:'联合动画',review:'阶段验收',delivery:'交付'};
const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
export function createProductionRevision({api,openRun}){
  const panel=document.getElementById('revision-panel');let key=null;
  return run=>{
    const next=run?run.run_id+':'+run.revision:null;if(next===key)return;key=next;panel.replaceChildren();
    panel.hidden=!run||['pending','running'].includes(run.status);if(panel.hidden)return;
    panel.append(el('h2','修正后重建'),el('p','参数先以当前任务为准。预览重建范围后再执行；旧候选与接受记录保留，新候选重新验收。'));
    const body=structuredClone(run.request.body_options),config=structuredClone(run.request.joint_config);
    const yaw=el('input','');yaw.type='number';yaw.min='-360';yaw.max='360';yaw.step='1';
    const staticCamera=body?.projection?.keys?.length===1;
    yaw.value=String(staticCamera?body.projection.keys[0].yaw:0);yaw.disabled=!staticCamera;
    const label=el('label','固定观察角 / °');label.append(yaw);panel.append(label);
    if(!staticCamera)panel.append(el('p','本任务不是单点观察角，现有相机轨道会完整保留；复杂动作请在动作编辑页调整。'));
    const checks={};for(const [group,text] of [['face','基础表情'],['hair','发束响应'],['cloth','裙袖响应']]){const l=el('label',text),input=el('input','');input.type='checkbox';input.checked=Boolean(config?.[group]?.enabled);l.prepend(input);panel.append(l);checks[group]=input;}
    const preview=el('button','预览受影响步骤'),output=el('div','');panel.append(preview,output);
    let pending=null,generation=0;
    const invalidate=()=>{generation++;pending=null;output.replaceChildren(el('p','参数已变化，请重新预览重建范围。'));};yaw.oninput=invalidate;for(const input of Object.values(checks))input.onchange=invalidate;
    preview.onclick=async()=>{preview.disabled=true;try{
      if(staticCamera){const value=Number(yaw.value);if(!Number.isFinite(value)||value<-360||value>360)throw Error('观察角应在 -360 到 360 度之间');body.projection.keys[0].yaw=value;}
      for(const [group,input] of Object.entries(checks)){config[group]??={};config[group].enabled=input.checked;}
      const request=structuredClone({expected_revision:run.revision,body_options:body,joint_config:config}),version=generation;
      const value=await api(`/api/production/${run.run_id}/revision-plan`,request);if(key!==next||generation!==version)return;pending=value;
      output.replaceChildren(el('p',`沿用：${value.reuse_stages.map(s=>names[s]).join('、')||'无'}。${value.refresh_stages?.length?`更新为当前已验证角色：${value.refresh_stages.map(s=>names[s]).join('、')}。`:''}重建：${value.rebuild_stages.map(s=>names[s]).join('、')}。阶段验收和交付将重新生成。`));
      const execute=el('button','按此范围创建修正任务');execute.onclick=async()=>{if(pending!==value)return;execute.disabled=true;try{const result=await api(`/api/production/${run.run_id}/revise`,{...request,expected_plan_sha256:value.plan_sha256});await openRun(result.run_id);}catch(e){output.append(el('p',`未执行：${e.message}，请刷新后重新预览。`));}finally{execute.disabled=false;}};output.append(execute);
    }catch(e){output.textContent=e.message;}finally{preview.disabled=false;}};
  };
}
