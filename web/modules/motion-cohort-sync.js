// Same-origin, exact-candidate control. No review or persistence side effects.
export function createCohortSync(status) {
  let frame = null, artifact = null, time = 0, duration = null, timer = null;
  function push() {
    if (!frame || duration === null) return;
    try {
      const win = frame.contentWindow, control = win?.characterPlayerControl;
      if (!control) { status.textContent = '等待角色播放器加载后同步…'; return; }
      if (control.artifact !== artifact) throw Error('候选身份不一致');
      const target = win.characterPlayerState;
      if (!target || Math.abs(target.duration - duration) > 0.002) throw Error('源与目标时长不同，不能直接同步');
      if (!control.seek(time)) throw Error('目标不支持此时间');
      for (const id of ['motion','play','reset','time']) {
        const input = win.document?.getElementById(id);
        if (input) { input.disabled = true; input.title = '使用左侧共用时间轴'; }
      }
      status.textContent = '共用时间轴 · 源为采样骨架，目标为实时 Runtime';
      if (timer !== null) { clearInterval(timer); timer = null; }
    } catch (error) {
      status.textContent = '同步未启用：' + error.message;
      if (timer !== null) clearInterval(timer);
      timer = null; frame = null;
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
    clear() { if (timer !== null) clearInterval(timer); timer = null; frame = null; duration = null; status.textContent = '正在切换对照…'; },
    attach(value, identity) { frame = value; artifact = identity; timer = setInterval(push, 100); push(); },
    seek(value, end) { time = value; duration = end; push(); },
  };
}
