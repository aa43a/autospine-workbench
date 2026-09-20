export function appendViewComparison(item, job, request, refresh) {
  const compare = document.createElement('button'); compare.textContent = '自动比较投影视角';
  const panel = document.createElement('section'); panel.setAttribute('aria-live', 'polite');
  const names = {front: '正面', side: '侧面'};
  compare.onclick = async () => {
    compare.disabled = true; panel.textContent = '正在检查完整源动作的两个视角…';
    try {
      const result = await request(`/api/motions/${job.job_id}/compare-views`);
      panel.replaceChildren();
      for (const row of result.records) {
        const p = document.createElement('p');
        p.textContent = `${names[row.view]}：${row.passed ? '源投影检查通过' : '源投影不合格'}；`
          + `最低可见长度 ${(row.minimum_visibility * 100).toFixed(1)}%，异常骨段 ${row.failed_roles.length} 个。`;
        panel.append(p);
      }
      const note = document.createElement('p');
      note.textContent = result.recommended_view === job.view ? '当前视角已通过源投影检查，保留当前选择。'
        : !result.recommended_view ? '两个完整视角都不合格；请查看投影异常或选择其他动作，不自动采用较差结果。'
          : '建议使用' + names[result.recommended_view] + '投影。';
      panel.append(note);
      if (result.recommended_view && result.recommended_view !== job.view) {
        const create = document.createElement('button'); create.textContent = '生成建议视角版本';
        create.onclick = async () => {
          create.disabled = true; compare.disabled = true;
          try {
            await request(`/api/motions/${job.job_id}/reproject`, {method: 'POST',
              headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
              body: JSON.stringify({view: result.recommended_view, comparison_sha256: result.comparison_sha256})});
            note.textContent = '新视角已排队；完成后选择新版本应用到角色，原动作保留。';
            await refresh();
          } catch (error) { note.textContent = error.message; create.disabled = false; }
          finally { compare.disabled = false; }
        };
        panel.append(create);
      }
      const scope = document.createElement('p');
      scope.textContent = '这里只比较源骨段投影；不生成侧面或背面贴图。新角色候选仍需检查变形、接触和遮挡。';
      panel.append(scope);
    } catch (error) { panel.textContent = error.message; }
    finally { compare.disabled = false; }
  };
  item.append(compare, panel);
}
