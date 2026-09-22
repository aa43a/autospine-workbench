import {appendNextActions} from './motion-next-actions.js';
import {appendDepthTimeline} from './motion-depth-timeline.js';
import {appendGeometryDetails} from './motion-geometry-details.js';
export function appendReadiness(item, job, compare, {onSeek} = {}) {
  const button = document.createElement('button');
  button.textContent = '检查可用范围与待处理项';
  const panel = document.createElement('section');
  panel.setAttribute('aria-live', 'polite');
  panel.hidden = true;
  const labels = {needs_changes: '需处理异常', evidence_incomplete: '检查证据尚不完整', stage_review: '可进行阶段视觉复核'};
  const states = {sampled_pass: '限定采样通过', needs_changes: '需处理', unmeasured: '尚未验证'};
  button.onclick = async () => {
    button.disabled = true; panel.hidden = false; panel.textContent = '正在核对当前候选证据…';
    const base = `/api/motions/${job.job_id}/view/`;
    try {
      const response = await fetch(base + 'readiness.json', {cache: 'no-store'});
      const report = await response.json();
      if (!response.ok) throw Error(report.reason_code || '检查失败');
      if(report.artifact_sha256!==job.result.artifact_sha256)throw Error('候选版本已变化，请刷新任务');
      panel.replaceChildren();
      const title = document.createElement('h4'); title.textContent = labels[report.status]; panel.append(title);
      for (const row of report.stages) {
        const p = document.createElement('p');
        p.textContent = `${row.stage}：${states[row.status]}。${row.explanation} `;
        const link = document.createElement('a'); link.textContent = '查看 / 处理';
        link.href = row.href.startsWith('/') ? row.href : base + row.href;
        link.target = '_blank'; link.rel = 'noopener'; p.append(link);
        const failures = row.failures || [];
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = `异常定位（报告返回 ${failures.length} 条采样记录）`;
        details.append(summary);
        for (const failure of failures) {
          const entry = document.createElement('p');
          const reason = document.createElement('span');
          reason.textContent = ({source_projection_unreliable:'源投影方向不可靠',
            post_contact_constraint_failed:'接触后局部变形约束未满足'})[failure.reason] || failure.reason || '检查异常';
          entry.append(reason);
          if (!Number.isFinite(failure.time) || failure.time < 0) {
            entry.append(' · 未提供有效时间'); details.append(entry); continue;
          }
          const point = document.createElement('a');
          point.textContent = ` ${failure.slot || failure.bone || '异常'} · ${failure.time.toFixed(3)} 秒 `;
          point.href = base + `player.html?time=${failure.time}`;
          if (onSeek) point.onclick = event => {event.preventDefault(); onSeek(failure.time);};
          else {point.target = '_blank'; point.rel = 'noopener';}
          entry.append(point); details.append(entry);
        }
        panel.append(p);
        if (failures.length) panel.append(details);
      }
      appendNextActions(panel,report,compare);
      if(report.stages.some(row=>row.stage==='几何'&&row.status==='needs_changes'))
        appendGeometryDetails(panel,job,onSeek);
      if(report.stages.some(row=>row.stage==='遮挡'&&row.status!=='sampled_pass'))
        appendDepthTimeline(panel,job,report,onSeek);
      const note = document.createElement('p');
      note.textContent = '执行完成不等于动作通过；已有文件可下载为诊断候选。这里不记录人工验收或发布许可。';
      panel.append(note);
      button.textContent = '重新检查候选证据';
    } catch (error) { panel.textContent = '无法核对：' + error.message; }
    finally { button.disabled = false; }
  };
  item.append(button, panel);
}
