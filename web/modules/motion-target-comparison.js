export function appendTargetComparison(item, job, request, {onOpen}={}) {
  const button = document.createElement('button'); button.textContent = '比较该角色的已有视角候选';
  const panel = document.createElement('section'); panel.setAttribute('aria-live', 'polite');
  button.onclick = async () => {
    button.disabled = true; panel.textContent = '正在核对同源动作、角色版本和检查结果…';
    try {
      const report = await request(`/api/motions/${job.job_id}/compare-targets`);
      if(report.source_job_id!==job.job_id)throw Error('比较对象已变化，请重新读取');
      panel.replaceChildren();
      const note = document.createElement('p');
      note.textContent = !report.complete ? '候选超过本次检查上限，未给出推荐。' : report.recommended_job_id
        ? '已有候选通过当前技术检查，可打开进行阶段视觉验收。' : '当前没有完整通过技术检查的视角；保留异常，不自动选取较少失败的一项。';
      panel.append(note);
      for (const row of report.rows) {
        const p = document.createElement('p');
        const view = row.view === 'side' ? '侧面' : '正面';
        p.textContent = `${row.job_id === report.recommended_job_id ? '推荐 · ' : ''}${view}`
          + `${row.projection ? ` 偏转 ${row.projection.yaw_degrees}°` : ''} · `
          + (row.stages ? row.stages.map(s => `${s.stage}：${s.status === 'sampled_pass' ? '采样通过' : s.status === 'needs_changes' ? '需处理' : '未验证'}`).join('；') : row.status);
        if (row.visual_decision === 'rejected') p.append(' · 人工已拒绝');
        if (row.visual_decision === 'evidence_changed') p.append(' · 原验收证据已变化');
        if (row.status === 'succeeded') {
          const link = document.createElement('a'); link.textContent = ' 打开时间轴';
          link.href = `/api/motions/${row.job_id}/view/player.html`; link.target = '_blank'; link.rel = 'noopener'; p.append(link);
          if(onOpen){link.textContent=' 在当前页比较';link.onclick=e=>{e.preventDefault();onOpen(row);};}
        }
        panel.append(p);
      }
    } catch (error) { panel.textContent = '无法比较：' + error.message; }
    finally { button.disabled = false; }
  };
  item.append(button, panel);
  return ()=>{button.click();panel.scrollIntoView({block:'nearest'});};
}
