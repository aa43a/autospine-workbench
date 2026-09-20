// Source contact evidence shares the existing source player; no adoption side effects.
export function createContactControls(container, slider) {
  let generation = 0;
  function text(tag, value) {
    const node = document.createElement(tag); node.textContent = value; return node;
  }
  function clear() { generation++; container.replaceChildren(); }
  async function load(job) {
    const token = ++generation;
    container.replaceChildren(text('p', '正在读取支撑区间…'));
    try {
      const response = await fetch(`/api/motions/${job.job_id}/contacts`, {cache: 'no-store'});
      const report = await response.json();
      if (token !== generation) return;
      if (!response.ok) throw Error(report.reason_code || '读取失败');
      container.replaceChildren(text('h3', '支撑区间与接触证据'));
      const labels = report.status === 'source_markers';
      container.append(text('p', labels ? '来自已编译源动作的接触标记；不代表目标角色脚底已经接地。'
        : '自动推断低位且近静止的踝部区间。当前仅作诊断，不会直接锁脚或修改动作。'));
      if (!report.markers.length) container.append(text('p', '未获得支撑区间；不将证据不足视为接触检查通过。'));
      const track = document.createElement('div');
      track.style.cssText = 'position:relative;height:54px;background:#182735;margin:12px 0';
      track.setAttribute('aria-label', '支撑区间时间带，点击定位源动作');
      const list = document.createElement('div');
      for (const marker of report.markers) {
        const start = marker.start_tick / report.ticks_per_second;
        const end = marker.end_tick / report.ticks_per_second;
        const phase = report.phase_support?.records.find(row => row.limb === marker.limb
          && row.start_tick === marker.start_tick && row.end_tick === marker.end_tick);
        const detail = !phase ? '' : Number.isFinite(phase.maximum_drift_ratio)
          ? `；源累计位移 ${(100*phase.maximum_drift_ratio).toFixed(2)}% 腿长，${phase.eligible ? '近静止' : '不宜锁脚'}`
          : '；区间样本不足';
        const label = `${marker.limb === 'leg.left' ? '左脚' : '右脚'} ${start.toFixed(3)}–${end.toFixed(3)} 秒（不含结束点）${detail}`;
        const seek = () => { slider.value = start; slider.dispatchEvent(new Event('input')); };
        const bar = text('button', ''); bar.title = label; bar.setAttribute('aria-label', label);
        bar.style.cssText = `position:absolute;top:${marker.limb === 'leg.left' ? 2 : 28}px;`
          + `left:${100*start/report.duration_seconds}%;width:${100*(end-start)/report.duration_seconds}%;height:22px;padding:0;min-width:2px;background:${phase && !phase.eligible ? '#966523' : '#387f96'}`;
        bar.onclick = seek; track.append(bar);
        const button = text('button', label); button.onclick = seek; list.append(button);
      }
      container.append(track, list);
      if (report.phase_support) container.append(text('p',
        `区间稳定性：${report.phase_support.eligible_intervals}/${report.markers.length} 段的源踝累计位移 ≤ 1% 腿长。`
        + '橙色区间不宜直接锁脚；近静止仍需目标可达性、变形和 Runtime 检查。'));
      if (report.derived_contact) {
        const policy = report.derived_contact;
        container.append(text('p', `推断依据：高度带 ${policy.height_threshold_source_units.toFixed(3)} 源单位；`
          + `三维速度 ≤ ${policy.speed_threshold_source_units_per_second.toFixed(3)} 源单位/秒；至少 ${policy.minimum_frames} 帧。`
          + '低位代理不是地面测量，无法区分静止悬空姿势；移动平台和跑步机需另行处理。'));
      }
      const link = text('a', '查看完整接触证据');
      link.href = `/api/motions/${job.job_id}/contacts`; link.target = '_blank'; link.rel = 'noopener';
      container.append(link);
    } catch (error) {
      if (token === generation) container.replaceChildren(text('p', `接触证据读取失败：${error.message}`));
    }
  }
  return {clear, load};
}
