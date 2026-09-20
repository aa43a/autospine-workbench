// A target is an exact existing character job; no SHA/path fields for operators.
export function createTargetControls(request, refresh) {
  const $ = id => document.getElementById(id);
  let source = null, character = null, token = 0, busy = false;
  function enabled() { $('adapt').disabled = busy || !source || !character; }
  async function selectProject() {
    const current = ++token, id = $('target-project').value;
    character = null; enabled();
    if (!id) { $('target-status').textContent = '选择已有整角色候选。'; return; }
    $('target-status').textContent = '正在检查角色来源…';
    try {
      const value = await request(`/api/projects/${encodeURIComponent(id)}/automation/character`);
      if (current !== token) return;
      if (value.job?.status === 'needs_review') {
        character = value.job;
        $('target-status').textContent = '使用当前完整角色候选；保留已确认的绑定、网格和纹理。';
      } else {
        $('target-status').textContent = '该角色还没有可用的整角色候选，请先在角色工作台完成构建。';
      }
    } catch (error) { if (current === token) $('target-status').textContent = error.message; }
    enabled();
  }
  async function loadProjects() {
    try {
      const value = await request('/api/projects');
      for (const project of value.projects) {
        const option = document.createElement('option');
        option.value = project.id; option.textContent = project.name;
        $('target-project').append(option);
      }
    } catch (error) { $('target-status').textContent = error.message; }
  }
  $('target-project').onchange = () => void selectProject();
  $('adapt').onclick = async () => {
    if (!source || !character || busy) return;
    busy = true; enabled();
    try {
      await request(`/api/motions/${source.job_id}/adapt`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Autospine-Intent': 'pipeline-preview'},
        body: JSON.stringify({project_id: character.project_id, character_job_id: character.job_id}),
      });
      $('target-status').textContent = '角色动作已排队，将进行局部修正、几何检查与官方 Runtime 捕获。';
      await refresh();
    } catch (error) { $('target-status').textContent = error.message; }
    finally { busy = false; enabled(); }
  };
  void loadProjects();
  return {select(job) {
    source = job?.result?.motion_status === 'compiled' ? job : null;
    $('target-source').textContent = source ? `动作：${source.name}` : '先选择已生成 MotionIR 的源动作。';
    enabled();
  }};
}
