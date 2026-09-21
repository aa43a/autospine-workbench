// Exact-candidate evidence, not an editor or an acceptance action.
const labels={torso_side_view_degenerate:'侧面投影接近退化',
  torso_back_view_requires_artwork:'背面朝向，需要对应素材',
  torso_width_outside_candidate_range:'宽度变化超出范围',
  torso_height_outside_candidate_range:'高度变化超出范围',
  torso_shear_outside_candidate_range:'剪切幅度超出范围'};
const element=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};

export function appendTorsoDetails(item,job){
  const button=element('button','在此检查躯干偏斜');
  const panel=element('section','');panel.hidden=true;panel.setAttribute('aria-label','躯干偏斜诊断');
  const base=`/api/motions/${job.job_id}/view/`;
  button.onclick=async()=>{
    button.disabled=true;panel.hidden=false;panel.textContent='正在核对当前候选的投影与检查结果…';
    try{
      const read=async name=>{const r=await fetch(base+name,{cache:'no-store'});const value=await r.json();
        if(!r.ok)throw Error(value.reason_code||'读取失败');return value;};
      const [report,ready]=await Promise.all([read('motion-torso-projection.json'),read('readiness.json')]);
      if(ready.artifact_sha256!==job.result.artifact_sha256 || !report.skeleton_sha256 ||
          report.skeleton_sha256!==ready.skeleton_sha256 || report.profile!==job.result.torso_projection_profile)
        throw Error('候选版本已变化，请刷新任务');
      const rows=report.source?.records;
      if(typeof report.applied!=='boolean' || !rows?.length || rows.some((r,i)=>!['time','longitudinal','transverse','shear','visibility']
          .every(k=>Number.isFinite(r[k])) || !Array.isArray(r.reasons) || (i&&r.time<=rows[i-1].time)))
        throw Error('投影采样证据不完整');
      panel.replaceChildren();
      const failed=rows.filter(r=>r.reasons.length);
      panel.append(element('h4',report.applied===true?'偏斜已应用到实验候选':'偏斜未应用，保留原动画诊断'),
        element('p',`${rows.length} 个源采样 · ${failed.length} 个超范围采样。应用不等于通过验收。`),
        element('p','仅改变躯干平面形状，并补偿头和手臂。骨骼参考线保持原位置；不生成侧面、背面或手掌翻面素材。'));
      const contact=report.contact_preservation?.status;
      panel.append(element('p',contact==='sampled_paths_preserved'?'采样脚部路径保持不变；不代表鞋底接地通过。':
        '脚部路径尚未证明保持不变，请查看接触检查。'));
      const slider=element('input','');slider.type='range';slider.min='0';slider.max=String(rows.length-1);
      slider.step='1';slider.value='0';slider.setAttribute('aria-label','躯干投影源采样');
      const values=element('output','');const reason=element('p','');
      const link=element('a','打开此时刻的角色动画');link.target='_blank';link.rel='noopener';
      const update=()=>{const r=rows[Number(slider.value)];
        values.textContent=`${r.time.toFixed(3)} 秒 · 宽 ${r.transverse.toFixed(3)} 倍 · 高 ${r.longitudinal.toFixed(3)} 倍 · 剪切 ${r.shear.toFixed(3)} · 可见度 ${r.visibility.toFixed(3)}`;
        reason.textContent=r.reasons.length?r.reasons.map(v=>labels[v]||v).join('；'):'此源采样位于实验范围内；仍需几何、接触与遮挡检查。';
        link.href=base+`player.html?time=${r.time}`;};
      slider.oninput=update;panel.append(slider,values,reason,link);
      if(failed.length){const jump=element('button','定位下一处超范围采样');
        jump.onclick=()=>{const index=Number(slider.value);let next=rows.findIndex((r,i)=>i>index&&r.reasons.length);
          if(next<0)next=rows.findIndex(r=>r.reasons.length);slider.value=String(next);update();};panel.append(jump);}
      update();
      const raw=element('a','完整躯干投影证据');raw.href=base+'motion-torso-projection.json';raw.target='_blank';raw.rel='noopener';
      panel.append(element('p','该页面只读，不改变候选、默认策略或人工验收记录。'),raw);
    }catch(error){panel.textContent='无法检查：'+error.message;}
    finally{button.disabled=false;}
  };
  item.append(button,panel);
}
