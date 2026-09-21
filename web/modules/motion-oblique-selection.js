// Propose a whole-clip angle; submission still produces a separately checked candidate.
export function createObliqueSelection(request, yaw, anchor, onBusy = () => {}) {
  const button = document.createElement('button'); button.type = 'button';
  button.textContent = '自动选择投影角度'; button.disabled = true;
  const status = document.createElement('p'); status.className = 'hint'; status.role = 'status';
  const mode=document.createElement('input');mode.type='checkbox';mode.checked=true;mode.disabled=true;
  mode.setAttribute('aria-label','新动作默认自动选择合格投影');
  const label=document.createElement('label');label.append(mode,' 新动作默认自动选择合格投影');
  anchor.after(label, button, status);
  let source = null, available = false, generation = 0, selection = null, busy = false, attempted=null;
  const enable = () => { button.disabled = !available || !source || busy; onBusy(busy); };
  const startDefault=()=>{if(mode.checked&&available&&source&&attempted!==source.job_id)void compare();};
  yaw.addEventListener('change', () => {
    mode.checked=false;
    generation++; selection = null; busy = false; status.textContent = '已切换为手动角度。'; enable();
  });
  async function compare() {
    if (!source || busy || !available) return;
    const current = ++generation, id = source.job_id;
    attempted=id;
    busy = true; enable(); status.textContent = '正在比较整段动作的 13 个投影角度…';
    try {
      const result = await request(`/api/motions/${id}/compare-oblique`);
      if (generation !== current) return;
      if (result.source_job_id !== id) throw new Error('动作来源已变化，请重新比较。');
      if (result.recommended_yaw_degrees === null) {
        selection = null;
        status.textContent = '当前角度均未通过源投影检查；保留当前选择，请缩小动作范围或处理投影异常。';
      } else {
        if(!Number.isFinite(result.recommended_yaw_degrees)||![...yaw.options].some(o=>o.value===String(result.recommended_yaw_degrees)))throw Error('建议角度不在支持范围内。');
        yaw.value = String(result.recommended_yaw_degrees);
        selection = {comparison_sha256: result.comparison_sha256};
        status.textContent = `已选择 ${yaw.value}°。这是源投影建议，构建后仍检查角色变形、接触与遮挡；不会生成侧背贴图。`;
      }
    } catch (error) { if (generation === current) {selection = null; status.textContent = error.message;} }
    finally { if (generation === current) {busy = false; enable();} }
  }
  button.onclick=()=>{mode.checked=true;return compare();};
  mode.onchange=()=>{
    if(mode.checked){attempted=null;startDefault();}
    else{generation++;selection=null;busy=false;status.textContent='已关闭自动选择，保留当前手动角度。';enable();}
  };
  return {
    available(value) {
      available = Boolean(value); mode.disabled=!available;
      if(!available){generation++;selection=null;busy=false;attempted=null;}
      enable(); startDefault();
    },
    source(job) {
      if (source?.job_id !== job?.job_id) { generation++; selection = null; busy = false; attempted=null; status.textContent = ''; }
      source = job; enable(); startDefault();
    },
    selection() { return selection ? {projection_selection: {...selection}} : {}; },
  };
}
