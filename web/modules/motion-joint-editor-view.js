import {appendCandidateDownload} from './motion-candidate-download.js';
import {appendReadiness} from './motion-readiness.js';
import {createJointTimeline} from './motion-joint-editor-timeline.js';
import {createJointLocalOptions} from './motion-joint-editor-local.js';
import {createJointMouthAsset} from './motion-joint-editor-mouth.js';
import {isJointActive,canRetryJoint,jointValue,JOINT_CHANNELS} from './motion-joint-editor-state.js';

const groupNames={face:'脸部与表情',hair:'发束摆动',cloth:'裙袖响应'};
const channelNames={blink:'眨眼',gaze:'视线',brows:'眉毛',mouth:'口型',turn:'小幅五官转向'};
const reasons={head_missing:'缺少头骨',attachment_variants:'包含多个附件，需明确对应关系',existing_hair_deform:'已有发束变形，保留现有结果',
  source_image_missing:'缺少来源图片',no_semantic_hair_layers:'未发现可用发层',no_existing_clothing_helpers:'未发现已绑定裙袖辅助骨',
  camera_inertia_requires_unprojected_body_driver:'此身体动作含视角旋转，尚无法区分相机转动与身体惯性；本次未加入发束和裙袖响应',
  new_response_suppressed_for_geometry:'为保留网格形状，本区域新增摆动已关闭；身体动作和原有修形保留',
  joint_secondary_channel_incomplete:'部分发束或裙袖通道未加入候选',joint_face_material_incomplete:'部分面部通道缺少兼容素材',
  joint_animation_loop_needs_changes:'循环首尾仍有位置或速度差异',joint_animation_deformation_needs_changes:'联合动画存在网格变形异常',
  motion_visible_depth_needs_changes:'身体动作仍有前后遮挡异常',
  joint_animation_single_skin_required:'当前候选包含多个皮肤，需先明确联合动画使用的皮肤',
  joint_animation_attachment_switch_not_supported:'身体动作包含附件切换，当前联合合成尚不支持该结构',
  independent_white_iris_lash_required:'需要独立眼白、虹膜和睫毛图层',
  blink_uses_source_lash_squash_not_drawn_closed_eye_variant:'眨眼使用现有睫毛压缩；尚无独立闭眼素材',
  mouth_is_source_art_parameterization_not_phoneme_or_new_open_mouth_art:'口型调整使用原有嘴部素材，尚无新增音素或张口素材',
  turn_is_limited_feature_shift_not_side_view_reconstruction:'小幅转向调整五官位置；尚无真实侧脸重建'};
export function jointResultSummary(job){
  const result=job.result??{},summary=result.joint_summary??{},lines=[],issues=[];
  const names={disabled:'未启用',blocked:'无法应用',partial:'部分应用',sampled_candidate_requires_visual_review:'已生成，待视觉检查',
    candidate:'已生成，待视觉检查',applied:'已加入候选，待视觉检查',passed:'检查通过',needs_changes:'需处理异常',not_requested:'未要求循环',unavailable:'验证环境不可用'};
  for(const [key,label]of [['face','脸部'],['secondary','发束与裙袖'],['loop','循环']]){
    const row=summary[key];if(!row)continue;
    lines.push(`${label}：${names[row.status]||row.status||'尚无状态'}`);
    if(['blocked','partial','needs_changes'].includes(row.status))issues.push(`${label}${names[row.status]}`);
    if(row.missing?.length)issues.push(`${label}缺少支持：${row.missing.map(k=>channelNames[k]||k).join('、')}`);
    for(const skipped of row.skipped??[])issues.push(`${skipped.slot||label}：${reasons[skipped.reason]||skipped.reason||'未应用'}`);
    for(const region of row.regions??[]){
      const requested=region.requested_config?.strength,effective=region.effective_config?.strength;
      if(Number.isFinite(requested)&&Number.isFinite(effective)&&effective<requested-1e-9)
        lines.push(`${region.slot}：为保护网格，响应强度从 ${Number(requested.toFixed(4))} 降为 ${Number(effective.toFixed(4))}（保留 ${Math.round(100*region.post_solve_gain)}%）。`);
    }
  }
  if(summary.loop?.requested&&summary.loop?.source_body?.loop_ready===false)issues.push('原身体动作尚未首尾闭合；联合效果不会自动修复身体循环。');
  if(summary.loop?.requested&&typeof summary.loop?.added_effects?.passed==='boolean')
    lines.push(`新增表情与次级运动循环：${summary.loop.added_effects.passed?'检查通过':'仍有首尾异常'}`);
  if(result.geometry_passed===false)issues.push('网格变形检查未通过');
  if(result.runtime?.status==='unavailable')issues.push('官方 Runtime 尚未验证');
  if(result.runtime?.geometry_status==='needs_changes')issues.push('Runtime 网格检查有异常');
  if(result.contact_status&&/fail|drift|needs_changes|unmeasured|not_evaluated/.test(result.contact_status))issues.push('接触检查尚有异常或缺测');
  for(const item of result.issues??[]){const reason=item.reason_code||item.reason;if(reason)issues.push(reasons[reason]||reason);}
  return {lines,issues:[...new Set(issues)]};
}
function element(tag,text,attributes={}){
  const node=document.createElement(tag);if(text)node.textContent=text;
  for(const [key,value]of Object.entries(attributes))node.setAttribute(key,value);return node;
}
export function inventoryLines(inventory,config){
  const features=Array.isArray(inventory)?inventory:inventory?.features;
  if(Array.isArray(features))return features.map(f=>typeof f==='string'?f:
    `${f.label||f.name||f.key||'动画能力'}：${f.reason||f.message||(f.available===false?'当前素材缺少支持':'可用')}`);
  if(!inventory||typeof inventory!=='object')return ['载入后显示当前角色可用的通道。'];
  if(inventory.face?.capabilities){
    const rows=Object.entries(inventory.face.capabilities).map(([key,available])=>`${channelNames[key]||key}：${available?'可用':'缺少独立素材或兼容绑定'}`);
    for(const group of ['hair','cloth'])for(const row of inventory[group]??[])
      rows.push(`${groupNames[group]} · ${row.name||row.slot}：${row.state==='available'?'可用':reasons[row.reason]||row.reason||'暂不可用'}`);
    for(const reason of [...(inventory.face.limitations??[]),...(inventory.limitations??[])]){
      if(reason==='mouth_is_source_art_parameterization_not_phoneme_or_new_open_mouth_art'&&config?.face?.mouth?.template_enabled){
        rows.push(inventory.face.mouth_template_available===false?'基础开口模板：当前嘴部素材不支持，请查看素材缺项。':
          config.face.mouth.template_image?'已选择上传的嘴部 PNG 替换图；需构建并检查外观，不代表音素同步。':'已选择程序绘制的基础开口模板；需构建并检查外观，不是原画差分或音素同步。');
      }else rows.push(reasons[reason]||reason);
    }
    return rows;
  }
  return Object.entries(inventory).map(([key,value])=>{
    const name=groupNames[key]||key;
    if(Array.isArray(value))return `${name}：${value.length} 项`;
    if(value&&typeof value==='object')return `${name}：${value.reason||value.message||value.status||
      (value.available===false?'当前素材缺少支持':Array.isArray(value.targets)?`${value.targets.length} 个目标`:'已读取')}`;
    return `${name}：${value===false?'当前素材缺少支持':value===true?'可用':String(value)}`;
  });
}
export function createJointView(container,actions){
  let time=0,currentState=null,anchorForm=null,anchorCanvas=null,viewEpoch=0;
  container.classList.add('joint-editor');container.setAttribute('aria-label','脸部、头发与服装联合动画');
  const title=element('h2','联合动画 · 叠加脸部、头发与裙袖');
  const intro=element('p','载入已有身体动作候选，调整表情和次级运动后构建同一个 Spine 包。已接受的历史动作也可直接作为来源。');
  const source=element('p','尚未载入身体动作候选。',{'data-joint':'source'});
  const timeline=element('p','使用上方共用时间轴。',{'data-joint':'time'});
  const status=element('p','从构建结果载入身体候选后开始。',{role:'status','aria-live':'polite','data-joint':'status'});
  const grid=element('div','',{class:'joint-groups'}),common=element('div','',{class:'joint-common'});
  const tracks=element('div','',{class:'joint-tracks'}),eligibility=element('p','',{class:'joint-eligibility',role:'status'});eligibility.hidden=true;
  const trackView=createJointTimeline(tracks,{...actions,focus:group=>{
    const field=grid.querySelector(`[data-joint-group="${group}"]`);field?.scrollIntoView({block:'center'});field?.querySelector('input')?.focus({preventScroll:true});
  }});
  const inventory=element('ul','',{class:'joint-inventory'});
  const details=element('details'),summary=element('summary','当前角色的能力与缺项');details.append(summary,inventory);
  const toolbar=element('div','',{class:'joint-toolbar'}),result=element('div','',{class:'joint-result'});
  const buttons={};
  for(const [key,label]of [['undo','撤销参数'],['redo','重做'],['defaults','恢复默认'],['save','保存草稿'],
    ['restore','恢复草稿'],['build','构建联合动画'],['refresh','刷新任务'],['cancel','取消构建'],['retry','重试失败任务']]){
    const button=element('button',label,{type:'button','data-joint':key});button.onclick=()=>actions[key]();toolbar.append(button);buttons[key]=button;
  }
  const note=element('p','参数修改将在重新构建后进入实际结果。右侧旧结果保留用于对照；同包下载包含身体动作及本次联合动画。',{class:'joint-note'});
  container.replaceChildren(title,intro,source,timeline,eligibility,details,tracks,grid,common,toolbar,status,note,result);
  const inputs=new Map(),keyPanels=new Map(),targets=new Map(),locals=[];let mouthAsset=null;
  function control(parent,c,value){
    const label=element('label'),input=element(c.options?'select':'input','',{'data-joint-control':`${c.group||'common'}.${c.key}`});
    if(c.options)for(const value of c.options)input.append(element('option',String(value),{value}));
    label.append(element('span',c.label),input);if(!c.options)input.type=c.type==='boolean'?'checkbox':'number';
    if(c.type==='boolean')input.checked=value;else{input.value=value;for(const key of ['min','max','step'])if(c[key]!==undefined)input[key]=c[key];}
    input.onchange=()=>actions.change(c.group,c.key,c.type==='boolean'?input.checked:input.value===''?NaN:Number(input.value));
    inputs.set(`${c.group||'common'}.${c.key}`,{input,c});parent.append(label);
  }
  function controls(meta,config){
    viewEpoch++;anchorCanvas?.dispose();anchorCanvas=null;mouthAsset?.dispose();mouthAsset=null;
    grid.replaceChildren();common.replaceChildren();inputs.clear();keyPanels.clear();targets.clear();locals.length=0;anchorForm=null;trackView.load(meta);
    for(const [group,label]of Object.entries(groupNames)){
      const set=element('fieldset','',{'data-joint-group':group}),legend=element('legend',label);set.append(legend);
      const definitions=meta.controls.filter(c=>c.group===group);
      const channelPanels=new Map();
      if(group==='face')for(const channel of Object.keys(JOINT_CHANNELS)){
        if(!definitions.some(c=>c.key.startsWith(channel+'.')))continue;
        const details=element('details','',{class:'joint-channel'});details.append(element('summary',channelNames[channel]));
        if(channel==='blink')details.open=true;channelPanels.set(channel,details);
      }
      if(!definitions.length)set.append(element('p','此角色暂未提供可调整通道。'));
      for(const c of definitions)control(channelPanels.get(c.key.split('.')[0])||set,c,jointValue(config[group],c.key));
      if(['hair','cloth'].includes(group)){
        const available=(meta.inventory?.[group]??[]).filter(row=>row.state==='available');
        if(available.length){const panel=element('details','',{class:'joint-targets'});panel.append(element('summary','选择响应区域（默认全部）'));
          for(const region of available){const label=element('label',region.name||region.slot),input=element('input','',{type:'checkbox'});
            input.onchange=()=>{const chosen=available.filter(row=>targets.get(`${group}.${row.slot}`).checked).map(row=>row.slot);actions.targets(group,chosen);};
            label.append(input);panel.append(label);targets.set(`${group}.${region.slot}`,input);}
          set.append(panel);
        }
        locals.push(createJointLocalOptions({container:set,group,meta,change:actions.local}));
      }
      if(group==='face'){
        if(channelPanels.has('mouth'))mouthAsset=createJointMouthAsset({container:channelPanels.get('mouth'),change:actions.mouthAsset});
        const channels=[...new Set(definitions.filter(c=>c.animatable).map(c=>c.channel||c.key.split('.')[0]))];
        for(const channel of channels){
          if(!JOINT_CHANNELS[channel]||!config.face[channel])continue;
          const panel=element('div','',{class:'joint-keys'});
          panel.append(element('strong',`${channelNames[channel]}关键帧`));let blinkInput=null;
          if(channel==='blink'){
            const label=element('label','闭眼程度');blinkInput=element('input','',{type:'number',min:0,max:1,step:0.05,value:1,'aria-label':'眨眼关键帧闭眼程度'});
            label.append(blinkInput);panel.append(label);
          }
          const row=element('div','',{class:'joint-key-actions'});
          for(const [kind,label]of [['record','记录当前时间'],['delete','删除当前时间'],['clear','清空此通道']]){
            const button=element('button',label,{type:'button'});button.onclick=()=>{
              if(kind==='record'){
                const values=channel==='blink'?{value:Number(blinkInput.value)}:currentState.config.face[channel];actions.key(channel,time,values);
              }else if(kind==='delete')actions.deleteKey(channel,time);else actions.clearKeys(channel);
            };row.append(button);
          }
          const list=element('div','',{class:'joint-key-list'});panel.append(row,list);(channelPanels.get(channel)||set).append(panel);keyPanels.set(channel,{panel,list});
        }
      }
      for(const panel of channelPanels.values())set.append(panel);
      if(group==='face'&&meta.inventory?.face?.parts?.some(part=>part.available)){
        const panel=element('details','',{class:'joint-anchors'});panel.append(element('summary','调整面部锚点（可选）'));
        panel.append(element('p','默认锚点可直接使用；仅在局部变形异常时调整。X / Y 为父骨骼局部坐标，重新构建后在动画中查看。'));
        const label=element('label','面部图层'),select=element('select','',{'aria-label':'面部锚点图层'});
        for(const part of meta.inventory.face.parts.filter(p=>p.available))select.append(element('option',part.name||part.slot,{value:part.slot}));
        label.append(select);panel.append(label);const fields=[];
        for(const axis of ['X','Y']){const label=element('label',`${axis} / 父骨局部坐标`),input=element('input','',{type:'number',min:-8192,max:8192,step:'any','aria-label':`面部锚点 ${axis}`});
          label.append(input);panel.append(label);fields.push(input);}
        const hint=element('p','',{class:'joint-note'}),apply=element('button','应用所选锚点',{type:'button'}),reset=element('button','恢复所选默认锚点',{type:'button'});
        apply.onclick=()=>actions.anchor(select.value,fields.map(input=>input.value===''?NaN:Number(input.value)));
        reset.onclick=()=>actions.anchor(select.value,null);select.onchange=()=>{updateAnchor();anchorCanvas?.select(select.value);};
        const canvas=element('div','',{class:'joint-anchor-canvas'});let opening=false;const epoch=viewEpoch;
        panel.ontoggle=async()=>{
          if(!panel.open||anchorCanvas||opening)return;opening=true;canvas.textContent='正在载入原始头部与可拖动锚点…';
          try{const {createJointAnchorCanvas}=await import('./motion-joint-anchor-canvas.js');
            if(epoch!==viewEpoch)return;
            canvas.replaceChildren();anchorCanvas=createJointAnchorCanvas({container:canvas,meta,change:(slot,point)=>{select.value=slot;actions.anchor(slot,point);}});
            anchorCanvas.update(currentState.config);anchorCanvas.select(select.value);
          }catch(error){if(epoch===viewEpoch)canvas.textContent=`画布尚未就绪：${error.message}。可继续使用上方坐标调整。`;}
          finally{opening=false;}
        };
        panel.append(hint,apply,reset,canvas);set.append(panel);anchorForm={panel,select,fields,hint,canvas};
      }
      grid.append(set);
    }
    control(common,{key:'loop',label:'循环动作',type:'boolean'},config.loop);
    common.append(element('p','表情与响应以约 60 Hz 烘焙，必要转折保留 120 Hz；原身体动作时序保留。',{class:'joint-note'}));
    inventory.replaceChildren(...inventoryLines(meta.inventory).map(line=>element('li',line)));
  }
  function updateAnchor(){
    if(!anchorForm||!currentState?.meta)return;const {select,fields,hint}=anchorForm;
    const part=currentState.meta.inventory.face.parts.find(part=>part.slot===select.value),override=currentState.config.face.anchors?.[select.value];
    const point=override||part.anchor;fields.forEach((input,index)=>{if(document.activeElement!==input)input.value=point?.[index]??0;});
    hint.textContent=`${part.slot} · 父骨 ${part.parent||'未知'} · 默认 (${part.anchor?.map(v=>Number(v).toFixed(2)).join(', ')||'未提供'})${override?' · 已自定义':' · 使用默认'}`;
  }
  function update(state,{busy=false,job=null,message=''}){
    currentState=state;
    const loaded=Boolean(state.meta),active=isJointActive(job);
    source.textContent=loaded?`来源：${state.meta.parent_job_id} · ${state.meta.animation||'身体动作'} · ${state.meta.duration.toFixed(2)} 秒`:'尚未载入身体动作候选。';
    const unsupported=state.meta?.eligibility?.supported===false;
    eligibility.hidden=!unsupported;eligibility.textContent=unsupported?`当前身体候选暂不支持联合叠加：${state.meta.eligibility.message||
      (state.meta.eligibility.reasons??[state.meta.eligibility.reason]).filter(Boolean).map(reason=>reasons[reason]||reason).join('；')||'需要兼容的身体动画结构。'}`:'';
    if(loaded){trackView.update(state.config,busy);trackView.seek(time);anchorCanvas?.update(state.config);
      for(const local of locals)local.update(state.config,busy);
      mouthAsset?.update(state.config,busy);
      inventory.replaceChildren(...inventoryLines(state.meta.inventory,state.config).map(line=>element('li',line)));}
    for(const {input,c}of inputs.values()){
      const value=jointValue(c.group?state.config?.[c.group]:state.config,c.key);
      if(c.type==='boolean')input.checked=Boolean(value);else if(value!==undefined&&document.activeElement!==input)input.value=value;
      input.disabled=!loaded||busy;
    }
    for(const b of Object.values(buttons))b.disabled=!loaded||busy;
    updateAnchor();if(anchorForm){for(const input of anchorForm.panel.querySelectorAll('input,select,button'))input.disabled=!loaded||busy;
      anchorForm.canvas.style.pointerEvents=busy?'none':'';}
    for(const [key,input]of targets){const [group,...parts]=key.split('.'),slot=parts.join('.'),selected=state.config?.[group]?.slots;
      input.checked=!selected?.length||selected.includes(slot);input.disabled=!loaded||busy;}
    for(const [channel,{panel,list}]of keyPanels){
      for(const button of panel.querySelectorAll('button'))button.disabled=!loaded||busy;
      const keys=state.config?.face?.[channel]?.keys??[];list.replaceChildren();
      if(!keys.length)list.append(element('span',channel==='blink'?'无关键帧，使用自动眨眼。':'无关键帧，使用当前固定参数。'));
      for(const key of keys){const button=element('button',`${key.time.toFixed(3)} 秒`,{type:'button',title:JOINT_CHANNELS[channel].map(field=>`${field}: ${key[field]}`).join(' · ')});
        button.onclick=()=>actions.seek(key.time);button.disabled=busy;list.append(button);}
    }
    buttons.undo.disabled=!loaded||busy||!state.canUndo;buttons.redo.disabled=!loaded||busy||!state.canRedo;
    buttons.build.disabled=!loaded||busy||active||unsupported;buttons.cancel.disabled=busy||!active||Boolean(job?.cancel_requested);
    buttons.retry.disabled=busy||!canRetryJoint(job)||unsupported;buttons.refresh.disabled=busy||!job;
    if(message)status.textContent=message;
    result.replaceChildren();
    if(!job)return;
    const history=element('a','查看本次任务记录',{href:`/motions.html#${job.job_id}`,target:'_blank',rel:'noopener'});result.append(history);
    if(job.status==='succeeded'){
      const qa=jointResultSummary(job),notice=element('aside','',{class:'joint-qa',role:'status'});
      notice.append(element('strong',qa.issues.length?'候选已生成，但仍有待处理项':'候选已生成，尚需联合动画阶段验收'));
      notice.append(element('p','构建成功只表示已生成文件。身体动作的接受记录不会自动接受新增表情、发束和裙袖运动。'));
      for(const line of qa.lines)notice.append(element('p',line));
      if(qa.issues.length){const list=element('ul');for(const issue of qa.issues.slice(0,12))list.append(element('li',issue));notice.append(list);
        if(qa.issues.length>12)notice.append(element('p',`另有 ${qa.issues.length-12} 项，详见候选证据。`));}
      result.append(notice);
      result.append(element('p',state.changed?'参数已变化：当前显示和下载仍是上次构建结果。请重新构建以应用修改。':'本次联合结果与当前参数一致。',{class:state.changed?'joint-stale':'joint-current'}));
      const compare=element('button','在当前画布查看联合结果',{type:'button'});compare.onclick=()=>actions.inspect(job);result.append(compare);
      appendCandidateDownload(result,job);appendReadiness(result,job,undefined,{onSeek:actions.seek,allowRepairs:false,
        onJointEdit:()=>{grid.scrollIntoView({block:'start'});grid.querySelector('input')?.focus({preventScroll:true});}});
    }
  }
  return {controls,update,clear(){viewEpoch++;anchorCanvas?.dispose();anchorCanvas=null;mouthAsset?.dispose();mouthAsset=null;grid.replaceChildren();common.replaceChildren();inventory.replaceChildren();inputs.clear();keyPanels.clear();targets.clear();locals.length=0;anchorForm=null;trackView.clear();},
    time(value){time=Number.isFinite(value)?Math.max(0,value):0;timeline.textContent=`共用时间轴：${time.toFixed(3)} 秒`;trackView.seek(time);},
  };
}
