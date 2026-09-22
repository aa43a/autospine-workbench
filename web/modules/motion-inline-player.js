import {createInlineSource} from './motion-inline-source.js';
// Load only the inspected candidate; pending commands never cross candidate identities.
export function appendInlinePlayer(parent, job) {
  const node = (tag, text) => {
    const value = document.createElement(tag);
    if (text) value.textContent = text;
    return value;
  };
  const open = node('button', '在当前页播放与定位');
  const panel = node('section'); panel.hidden = true;
  panel.className = 'motion-inline-player';
  const status = node('p'); status.setAttribute('aria-live', 'polite');
  const close = node('button', '关闭播放器');
  const whole = node('button', '显示完整角色');
  const holder = node('div');
  panel.append(close, whole, status, holder); parent.append(open, panel);
  let frame = null, timer = null, pending = null, attempts = 0, isolated = null;
  let source=null;
  const ensureSource=()=>source??=createInlineSource(panel,job,()=>frame?.contentWindow,time=>{
    if(!parent.isConnected){source.clear();return;}
    pending={time};flush();
  });
  function stop() { clearTimeout(timer); timer = null; }
  function flush() {
    stop();
    if (!parent.isConnected || !frame) return;
    try {
      const control = frame.contentWindow?.characterPlayerControl;
      if (!control) {
        if (++attempts > 1200) throw Error('播放器加载超时，请关闭后重试');
        status.textContent = '正在加载当前候选，定位请求会在加载完成后执行…';
        timer = setTimeout(flush, 100); return;
      }
      if (control.artifact !== job.result.artifact_sha256) throw Error('候选身份不一致，请刷新任务');
      if (pending) {
        if (!control.seek(pending.time)) throw Error('无法定位此动作时间');
        if (pending.region) {
          control.inspectRegions?.([],'full');isolated=null;
          if(!control.inspectTriangle?.(...pending.region))throw Error('当前动作不支持此区域高亮');
        }
        if (pending.pair && !control.inspectRegions?.(pending.pair,'isolate'))
          throw Error('当前候选不包含此部件组合');
        if(pending.pair)isolated=pending.pair;
        pending = null;
      }
      status.textContent = isolated ? `当前隔离：${isolated.join(' ↔ ')}。可点击“显示完整角色”恢复。`
        : '当前候选已核对；可播放、拖动时间轴或从异常记录定位。';
    } catch (error) { source?.clear(); status.textContent = '定位未完成：' + error.message; }
  }
  function show() {
    panel.hidden = false;
    ensureSource();
    if (!frame) {
      frame = node('iframe'); frame.title = '当前角色候选时间轴';
      frame.style.cssText = 'display:block;width:100%;height:640px;border:0';
      frame.src = `/api/motions/${encodeURIComponent(job.job_id)}/view/player.html`;
      holder.append(frame); attempts = 0;
    }
    flush(); panel.scrollIntoView({block:'nearest'});
  }
  open.onclick = show;
  whole.onclick=()=>{
    const control=frame?.contentWindow?.characterPlayerControl;
    if(control?.artifact!==job.result.artifact_sha256)return;
    control.inspectRegions?.([],'full');
    isolated=null;flush();
  };
  close.onclick = () => { stop(); source?.clear(); frame = null; pending = null; isolated=null; holder.replaceChildren(); panel.hidden = true; };
  let lastTime = 0;
  return {
    onSeek(time) {
      if (!Number.isFinite(time) || time < 0) throw Error('动作时间无效');
      lastTime = time; pending = {time}; show(); source.seek(time);
    },
    onInspect(slot, triangle, animation) {
      pending = {time:lastTime, region:[slot, triangle, animation]}; show();
      return true; // Accepted for delivery; loading/errors remain visible in this panel.
    },
    onRegions(pair){pending={time:lastTime,pair};show();},
  };
}
