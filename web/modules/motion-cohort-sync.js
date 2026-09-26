// Same-origin, exact-candidate control. No review or persistence side effects.
export function createCohortSync(status) {
  let frame = null, artifact = null, time = 0, duration = null, timer = null, range = null;
  const disabledControls=new Map();
  function release(){for(const [input,disabled] of disabledControls)input.disabled=disabled;disabledControls.clear();}
  function push() {
    if (!frame || duration === null) return;
    try {
      if(!Number.isFinite(time)||!Number.isFinite(duration)||duration<0||time<0||time>duration)
        throw Error('源时间无效，不能直接同步');
      const start=range?.start??0,end=range?.end??duration;
      if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start
          ||Math.abs(end-duration)>1e-6||time<start||time>end)throw Error('源片段时间不匹配');
      const win = frame.contentWindow, control = win?.characterPlayerControl;
      if (!control) { status.textContent = '等待角色播放器加载后同步…'; return; }
      if (control.artifact !== artifact) throw Error('候选身份不一致');
      const target = win.characterPlayerState;
      if (!target || !Number.isFinite(target.duration) || Math.abs(target.duration - (end-start)) > 0.002) throw Error('源与目标时长不同，不能直接同步');
      if (!control.seek(Math.min(time-start,target.duration))) throw Error('目标不支持此时间');
      for (const id of ['motion','play','reset','time']) {
        const input = win.document?.getElementById(id);
        if (input) { if(!disabledControls.has(input))disabledControls.set(input,input.disabled);input.disabled = true; }
      }
      status.textContent = `共用时间轴 · 源 ${start.toFixed(3)}–${end.toFixed(3)} 秒 ↔ 角色 0–${(end-start).toFixed(3)} 秒；源为采样骨架，目标为实时 Runtime`;
      if (timer !== null) { clearInterval(timer); timer = null; }
    } catch (error) {
      status.textContent = '同步未启用：' + error.message;
      if (timer !== null) clearInterval(timer);
      release();timer = null; frame = null;
    }
  }
  return {
    regions(pair,mode='isolate'){
      const control=frame?.contentWindow?.characterPlayerControl;
      if(!control||control.artifact!==artifact||!control.inspectRegions?.(pair,mode)){
        status.textContent='部件隔离未启用：请等待匹配候选加载并检查区域';return false;
      }
      status.textContent=mode==='full'?'已恢复完整角色，保持当前时间':`当前隔离：${pair.join(' ↔ ')}，使用“显示完整角色”恢复`;
      return true;
    },
    inspect(slot,triangle,animation){
      const control=frame?.contentWindow?.characterPlayerControl;
      if(!control||control.artifact!==artifact||!control.inspectTriangle?.(slot,triangle,animation)){
        status.textContent='区域高亮未启用：请等待匹配候选及动作加载';return false;
      }
      return true;
    },
    clear() { if (timer !== null) clearInterval(timer);release(); timer = null; frame = null; duration = null; range=null; status.textContent = '正在切换对照…'; },
    attach(value, identity, sourceRange=null) { if(timer!==null)clearInterval(timer);release();frame = value; artifact = identity;range=sourceRange;timer = setInterval(push, 100); push(); },
    seek(value, end) { time = value; duration = end; push(); },
  };
}
